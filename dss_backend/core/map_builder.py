from datetime import datetime
from typing import Any

from dss_backend.core.state_manager import seconds_since


MARKERS_BY_DOMAIN = {
    "air": "uav",
    "surface": "usv",
    "subsurface": "uuv",
}


def _vehicle_label(vehicle_id: str) -> str:
    return vehicle_id.replace("_", " ").upper()


def _color_status(vehicle: dict[str, Any]) -> str:
    link_status = (vehicle.get("link") or {}).get("status")
    battery = vehicle.get("battery") or {}
    battery_percentage = battery.get("percentage")
    bingo_threshold = battery.get("bingo_threshold")

    if vehicle.get("status") == "fault":
        return "red"
    if battery_percentage is not None and bingo_threshold is not None:
        if battery_percentage <= bingo_threshold:
            return "low_battery"
    if link_status == "lost_link":
        return "red"
    if link_status == "unstable":
        return "orange"
    if link_status == "degraded":
        return "yellow"
    if link_status == "expected_blackout":
        return "blue"
    if link_status == "late_contact":
        return "orange"
    return "green" if link_status == "online" else "gray"


def _vehicle_marker(vehicle: dict[str, Any]) -> dict[str, Any] | None:
    position = vehicle.get("position")
    if not position:
        return None

    velocity = vehicle.get("velocity") or {}
    battery = vehicle.get("battery") or {}
    link = vehicle.get("link") or {}
    domain = vehicle.get("domain")
    vehicle_id = vehicle["vehicle_id"]

    return {
        "id": vehicle_id,
        "type": "vehicle",
        "domain": domain,
        "marker": MARKERS_BY_DOMAIN.get(domain, "vehicle"),
        "position": position,
        "heading_deg": velocity.get("heading_deg"),
        "status": vehicle.get("status"),
        "link_status": link.get("status"),
        "battery_percentage": battery.get("percentage"),
        "current_task_id": vehicle.get("current_task_id"),
        "display": {
            "label": _vehicle_label(vehicle_id),
            "color_status": _color_status(vehicle),
        },
    }


def _event_marker(event: dict[str, Any]) -> dict[str, Any] | None:
    position = event.get("position")
    if not position:
        return None

    return {
        "id": event.get("event_id"),
        "type": "event",
        "event_kind": event.get("event_kind"),
        "severity": event.get("severity"),
        "vehicle_id": event.get("vehicle_id"),
        "domain": event.get("domain"),
        "position": position,
        "description": event.get("description"),
        "created_by": event.get("created_by", "vehicle"),
    }


def _uncertainty_region(vehicle: dict[str, Any], now: datetime) -> dict[str, Any] | None:
    position = vehicle.get("position")
    if not position:
        return None

    link_status = (vehicle.get("link") or {}).get("status")
    freshness = vehicle.get("telemetry_freshness") or {}
    if link_status not in {"lost_link", "late_contact", "expected_blackout"}:
        if freshness.get("status") != "very_stale":
            return None

    domain = vehicle.get("domain")
    velocity = vehicle.get("velocity") or {}
    speed = velocity.get("speed_mps")
    age = freshness.get("seconds_since_last_telemetry")
    if age is None:
        age = seconds_since(freshness.get("last_telemetry_received_at"), now) or 0

    if speed is None:
        radius = 500 if domain == "subsurface" else 100
    else:
        radius = speed * age
        if domain == "subsurface":
            radius = max(100, radius)

    return {
        "id": f"uncertainty_{vehicle['vehicle_id']}",
        "type": "uncertainty",
        "vehicle_id": vehicle["vehicle_id"],
        "domain": domain,
        "center": position,
        "radius_m": min(5000, round(radius, 1)),
        "reason": link_status if link_status in {"lost_link", "late_contact", "expected_blackout"} else "very_stale_telemetry",
    }


def build_map_state(
    normalized_vehicles: dict[str, dict[str, Any]],
    active_events: list[dict[str, Any]],
    now: datetime,
) -> dict[str, Any]:
    vehicle_markers = [
        marker
        for marker in (_vehicle_marker(vehicle) for vehicle in normalized_vehicles.values())
        if marker is not None
    ]
    event_markers = [
        marker for marker in (_event_marker(event) for event in active_events) if marker is not None
    ]
    uncertainty_regions = [
        region
        for region in (_uncertainty_region(vehicle, now) for vehicle in normalized_vehicles.values())
        if region is not None
    ]

    return {
        "vehicles": vehicle_markers,
        "events": event_markers,
        "contacts": [],
        "zones": [],
        "uncertainty_regions": uncertainty_regions,
    }
