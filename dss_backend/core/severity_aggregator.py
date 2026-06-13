from datetime import datetime
from typing import Any

from dss_backend.core.state_manager import seconds_since


SEVERITY_POINTS = {
    "low": 1,
    "medium": 3,
    "high": 6,
    "critical": 10,
}
SEVERITY_WINDOW_SECONDS = 120
SEVERITY_THRESHOLD_SCORE = 9
CRITICAL_EVENT_ALWAYS_TRIGGERS = True
MEDIUM_HIGH_COUNT_THRESHOLD = 3


def _event_time(event: dict[str, Any]) -> datetime | None:
    value = event.get("updated_at") or event.get("received_at") or event.get("timestamp")
    return value if isinstance(value, datetime) else None


def merge_active_events(
    external_events: list[dict[str, Any]], dss_events: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    merged = [event for event in external_events if event.get("status", "active") == "active"]
    merged.extend(event for event in dss_events.values() if event.get("status") == "active")
    return merged


def aggregate_severity(active_events: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    recent_events = []
    for event in active_events:
        event_time = _event_time(event)
        if event_time is None or seconds_since(event_time, now) is None:
            continue
        if seconds_since(event_time, now) <= SEVERITY_WINDOW_SECONDS:
            recent_events.append(event)

    current_score = sum(SEVERITY_POINTS.get(event.get("severity"), 0) for event in recent_events)
    medium_high_count = sum(
        1 for event in recent_events if event.get("severity") in {"medium", "high", "critical"}
    )
    critical_present = any(event.get("severity") == "critical" for event in recent_events)

    triggered = False
    trigger_reason = None
    if CRITICAL_EVENT_ALWAYS_TRIGGERS and critical_present:
        triggered = True
        trigger_reason = "critical_event"
    elif current_score >= SEVERITY_THRESHOLD_SCORE:
        triggered = True
        trigger_reason = "severity_threshold_reached"
    elif medium_high_count >= MEDIUM_HIGH_COUNT_THRESHOLD:
        triggered = True
        trigger_reason = "medium_high_count_threshold_reached"

    return {
        "window_seconds": SEVERITY_WINDOW_SECONDS,
        "threshold_score": SEVERITY_THRESHOLD_SCORE,
        "current_score": current_score,
        "triggered": triggered,
        "trigger_reason": trigger_reason,
        "event_count": len(recent_events),
        "medium_high_count": medium_high_count,
        "triggering_event_ids": [event.get("event_id") for event in recent_events],
        "updated_at": now,
    }
