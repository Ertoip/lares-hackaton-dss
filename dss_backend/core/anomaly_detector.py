from copy import deepcopy
from datetime import datetime
from typing import Any

from dss_backend.core.state_manager import seconds_since


GENERATED_PREFIXES = (
    "dss_low_battery_",
    "dss_lost_link_",
    "dss_degraded_link_",
    "dss_sensor_failure_",
    "dss_stale_telemetry_",
    "dss_vehicle_fault_",
)


def _round_seconds(value: float | None) -> int:
    if value is None:
        return -1
    return int(round(value))


def _upsert_event(
    existing: dict[str, dict[str, Any]],
    active_ids: set[str],
    event_id: str,
    event_kind: str,
    vehicle: dict[str, Any],
    severity: str,
    description: str,
    metadata: dict[str, Any],
    now: datetime,
) -> None:
    previous = existing.get(event_id, {})
    existing[event_id] = {
        "event_id": event_id,
        "event_kind": event_kind,
        "vehicle_id": vehicle["vehicle_id"],
        "domain": vehicle["domain"],
        "severity": severity,
        "status": "active",
        "created_by": "dss",
        "description": description,
        "position": deepcopy(vehicle.get("position")),
        "metadata": metadata,
        "created_at": previous.get("created_at") or now,
        "updated_at": now,
    }
    active_ids.add(event_id)


def detect_anomalies(
    normalized_vehicles: dict[str, dict[str, Any]],
    existing_dss_events: dict[str, dict[str, Any]],
    now: datetime,
) -> dict[str, dict[str, Any]]:
    updated = deepcopy(existing_dss_events)
    active_ids: set[str] = set()

    for vehicle in normalized_vehicles.values():
        vehicle_id = vehicle["vehicle_id"]
        battery = vehicle.get("battery") or {}
        percentage = battery.get("percentage")
        bingo_threshold = battery.get("bingo_threshold")
        if percentage is not None and bingo_threshold is not None and percentage <= bingo_threshold:
            _upsert_event(
                updated,
                active_ids,
                f"dss_low_battery_{vehicle_id}",
                "low_battery",
                vehicle,
                "high",
                f"{vehicle_id} battery is {percentage:g}%, below bingo threshold of {bingo_threshold:g}%",
                {"battery_percentage": percentage, "bingo_threshold": bingo_threshold},
                now,
            )

        link = vehicle.get("link") or {}
        link_status = link.get("status")
        heartbeat_age = seconds_since(link.get("last_heartbeat_received_at"), now)
        if link_status == "lost_link":
            _upsert_event(
                updated,
                active_ids,
                f"dss_lost_link_{vehicle_id}",
                "lost_link",
                vehicle,
                "critical",
                f"{vehicle_id} link lost; last heartbeat received {_round_seconds(heartbeat_age)}s ago",
                {"seconds_since_last_heartbeat": heartbeat_age, "link_status": link_status},
                now,
            )
        elif link_status in {"degraded", "unstable"}:
            _upsert_event(
                updated,
                active_ids,
                f"dss_degraded_link_{vehicle_id}",
                "degraded_link",
                vehicle,
                "high" if link_status == "unstable" else "medium",
                f"{vehicle_id} link is {link_status}; heartbeat timing exceeds expected interval",
                {"seconds_since_last_heartbeat": heartbeat_age, "link_status": link_status},
                now,
            )

        sensors = vehicle.get("sensors") or {}
        for sensor_name, sensor_status in sensors.items():
            if sensor_status == "fault":
                _upsert_event(
                    updated,
                    active_ids,
                    f"dss_sensor_failure_{vehicle_id}_{sensor_name}",
                    "sensor_failure",
                    vehicle,
                    "high",
                    f"{vehicle_id} {sensor_name} is {sensor_status}",
                    {"sensor_name": sensor_name, "sensor_status": sensor_status},
                    now,
                )
            elif sensor_status == "degraded":
                _upsert_event(
                    updated,
                    active_ids,
                    f"dss_sensor_failure_{vehicle_id}_{sensor_name}",
                    "sensor_failure",
                    vehicle,
                    "medium",
                    f"{vehicle_id} {sensor_name} is {sensor_status}",
                    {"sensor_name": sensor_name, "sensor_status": sensor_status},
                    now,
                )

        freshness = vehicle.get("telemetry_freshness") or {}
        freshness_status = freshness.get("status")
        telemetry_age = freshness.get("seconds_since_last_telemetry")
        if freshness_status == "very_stale" and link_status != "expected_blackout":
            _upsert_event(
                updated,
                active_ids,
                f"dss_stale_telemetry_{vehicle_id}",
                "stale_telemetry",
                vehicle,
                "medium",
                f"{vehicle_id} telemetry is {freshness_status}; last telemetry received {_round_seconds(telemetry_age)}s ago",
                {"seconds_since_last_telemetry": telemetry_age, "freshness_status": freshness_status},
                now,
            )

        if vehicle.get("status") == "fault":
            _upsert_event(
                updated,
                active_ids,
                f"dss_vehicle_fault_{vehicle_id}",
                "vehicle_fault",
                vehicle,
                "high",
                f"{vehicle_id} reports vehicle status fault",
                {"vehicle_status": "fault"},
                now,
            )

    for event_id, event in list(updated.items()):
        if event_id.startswith(GENERATED_PREFIXES) and event_id not in active_ids:
            event["status"] = "resolved"
            event["updated_at"] = now

    return updated
