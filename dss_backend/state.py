import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any


ALLOWED_VEHICLES: dict[str, str] = {
    "air_1": "air",
    "air_2": "air",
    "surface_1": "surface",
    "surface_2": "surface",
    "sub_1": "subsurface",
    "sub_2": "subsurface",
}


vehicles: dict[str, dict[str, Any]] = {vehicle_id: {} for vehicle_id in ALLOWED_VEHICLES}
events: dict[str, dict[str, Any]] = {}
dss_events: dict[str, dict[str, Any]] = {}
severity_state: dict[str, Any] = {}
reports: dict[str, dict[str, Any]] = {}
chat_messages: dict[str, dict[str, Any]] = {}
map_state: dict[str, Any] = {}
operator_state: dict[str, Any] = {}
state_lock = asyncio.Lock()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def validate_vehicle_and_domain(vehicle_id: str, domain: str) -> str | None:
    expected_domain = ALLOWED_VEHICLES.get(vehicle_id)
    if expected_domain is None:
        return "Invalid vehicle_id"
    if domain != expected_domain:
        return "Domain does not match vehicle_id"
    return None


def serializable_snapshot() -> dict[str, Any]:
    return {
        "vehicles": deepcopy(vehicles),
        "events": deepcopy(events),
        "dss_events": deepcopy(dss_events),
        "severity_state": deepcopy(severity_state),
        "reports": deepcopy(reports),
        "chat_messages": deepcopy(chat_messages),
        "map_state": deepcopy(map_state),
        "operator_state": deepcopy(operator_state),
    }
