from datetime import datetime
from typing import Any

from dss_backend.core.state_manager import seconds_since


REPORT_COOLDOWN_SECONDS = 60


def _event_summary(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": event.get("event_id"),
        "event_kind": event.get("event_kind"),
        "severity": event.get("severity"),
        "vehicle_id": event.get("vehicle_id"),
        "description": event.get("description"),
    }


def _cluster_fingerprint(active_events: list[dict[str, Any]]) -> str:
    event_ids = sorted(str(event.get("event_id")) for event in active_events if event.get("event_id"))
    return "|".join(event_ids)


def should_generate_report(
    severity_state: dict[str, Any],
    active_events: list[dict[str, Any]],
    existing_reports: dict[str, dict[str, Any]],
    now: datetime,
) -> tuple[bool, dict[str, Any] | None]:
    if not severity_state.get("triggered"):
        return False, None

    triggering_ids = set(severity_state.get("triggering_event_ids") or [])
    triggering_events = [event for event in active_events if event.get("event_id") in triggering_ids]
    if not triggering_events:
        return False, None

    for report in existing_reports.values():
        created_at = report.get("created_at")
        if isinstance(created_at, datetime):
            age = seconds_since(created_at, now)
            if age is not None and age < REPORT_COOLDOWN_SECONDS:
                return False, None

    fingerprint = _cluster_fingerprint(triggering_events)
    if any(report.get("cluster_fingerprint") == fingerprint for report in existing_reports.values()):
        return False, None

    timestamp = now.strftime("%Y%m%dT%H%M%S")
    return True, {
        "report_trigger_id": f"trigger_{timestamp}",
        "trigger_reason": severity_state.get("trigger_reason"),
        "window_seconds": severity_state.get("window_seconds"),
        "severity_score": severity_state.get("current_score"),
        "event_count": len(triggering_events),
        "cluster_fingerprint": fingerprint,
        "events": [_event_summary(event) for event in triggering_events],
    }
