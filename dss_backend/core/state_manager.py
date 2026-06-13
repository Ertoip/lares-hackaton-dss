from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from dss_backend.state import ALLOWED_VEHICLES


def ensure_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def seconds_since(value: datetime | None, now: datetime) -> float | None:
    value = ensure_aware(value)
    if value is None:
        return None
    return max(0.0, (now - value).total_seconds())


def _freshness_status(domain: str, age_seconds: float | None) -> str:
    if age_seconds is None:
        return "unknown"

    thresholds = {
        "air": (5, 15),
        "surface": (10, 30),
        "subsurface": (60, 180),
    }
    fresh_until, stale_until = thresholds[domain]
    if age_seconds <= fresh_until:
        return "fresh"
    if age_seconds <= stale_until:
        return "stale"
    return "very_stale"


def normalize_vehicles(
    raw_vehicles: dict[str, dict[str, Any]], now: datetime
) -> dict[str, dict[str, Any]]:
    normalized: dict[str, dict[str, Any]] = {}

    for vehicle_id, expected_domain in ALLOWED_VEHICLES.items():
        raw = raw_vehicles.get(vehicle_id, {}) or {}
        telemetry = raw.get("telemetry", {}) or {}
        telemetry_received_at = raw.get("telemetry_received_at")
        last_telemetry_at = telemetry.get("timestamp")
        telemetry_age = seconds_since(telemetry_received_at, now)

        normalized[vehicle_id] = {
            "vehicle_id": vehicle_id,
            "domain": raw.get("domain") or expected_domain,
            "status": raw.get("status") or "unknown",
            "position": deepcopy(raw.get("position")),
            "velocity": deepcopy(raw.get("velocity")),
            "battery": deepcopy(raw.get("battery")),
            "link": deepcopy(raw.get("link", {})),
            "sensors": deepcopy(raw.get("sensors")),
            "capabilities": deepcopy(raw.get("capabilities")),
            "current_task_id": raw.get("current_task_id"),
            "telemetry_freshness": {
                "last_telemetry_at": last_telemetry_at,
                "last_telemetry_received_at": telemetry_received_at,
                "seconds_since_last_telemetry": telemetry_age,
                "status": _freshness_status(expected_domain, telemetry_age),
            },
            "raw": deepcopy(raw),
        }

    return normalized


def normalize_external_events(raw_events: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for event_id, event in raw_events.items():
        item = deepcopy(event)
        item.setdefault("event_id", event_id)
        item.setdefault("status", "active")
        item.setdefault("created_by", "vehicle")
        item.setdefault("updated_at", item.get("received_at") or item.get("timestamp"))
        normalized.append(item)
    return normalized


def active_events_only(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [event for event in events if event.get("status", "active") == "active"]
