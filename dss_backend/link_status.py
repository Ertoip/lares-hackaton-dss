import asyncio
from datetime import datetime, timezone
from typing import Any

from dss_backend.state import ALLOWED_VEHICLES, state_lock, utc_now, vehicles


LINK_RECALCULATION_SECONDS = 1
SUBSURFACE_LOST_LINK_AFTER_WINDOW_SECONDS = 300


def _seconds_since(value: datetime | None, now: datetime) -> float | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return (now - value).total_seconds()


def _status_from_thresholds(
    age_seconds: float | None,
    online_until: float,
    degraded_until: float,
    unstable_until: float,
) -> str:
    if age_seconds is None:
        return "unknown"
    if age_seconds <= online_until:
        return "online"
    if age_seconds <= degraded_until:
        return "degraded"
    if age_seconds <= unstable_until:
        return "unstable"
    return "lost_link"


def derive_link_status(vehicle_id: str, vehicle: dict[str, Any], now: datetime) -> str:
    domain = ALLOWED_VEHICLES[vehicle_id]
    link = vehicle.get("link", {})
    last_heartbeat_received_at = link.get("last_heartbeat_received_at")
    heartbeat_age = _seconds_since(last_heartbeat_received_at, now)

    if domain == "air":
        return _status_from_thresholds(heartbeat_age, 2, 5, 10)

    if domain == "surface":
        return _status_from_thresholds(heartbeat_age, 6, 12, 20)

    explicit_status = link.get("reported_status")
    contact_window = link.get("expected_next_contact_window")
    if explicit_status == "expected_blackout" and contact_window:
        window_end = contact_window.get("end")
        if isinstance(window_end, datetime):
            seconds_past_window = (now - window_end).total_seconds()
            if seconds_past_window <= 0:
                return "expected_blackout"
            if seconds_past_window <= SUBSURFACE_LOST_LINK_AFTER_WINDOW_SECONDS:
                return "late_contact"
            return "lost_link"
        return "expected_blackout"

    return _status_from_thresholds(heartbeat_age, 60, 120, 180)


def apply_link_status(vehicle_id: str, now: datetime | None = None) -> None:
    now = now or utc_now()
    vehicle = vehicles[vehicle_id]
    link = vehicle.setdefault("link", {})
    link["status"] = derive_link_status(vehicle_id, vehicle, now)
    link["status_updated_at"] = now


async def recalculate_all_link_statuses() -> None:
    async with state_lock:
        now = utc_now()
        for vehicle_id, vehicle in vehicles.items():
            if "link" not in vehicle:
                continue
            apply_link_status(vehicle_id, now)


async def link_status_background_task() -> None:
    while True:
        await recalculate_all_link_statuses()
        await asyncio.sleep(LINK_RECALCULATION_SECONDS)
