from datetime import datetime, timezone
from typing import Any


def _sort_newest(items: list[dict[str, Any]], time_field: str) -> list[dict[str, Any]]:
    def sort_value(item: dict[str, Any]) -> datetime:
        value = item.get(time_field)
        if isinstance(value, datetime):
            return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return datetime.min.replace(tzinfo=timezone.utc)

    return sorted(items, key=sort_value, reverse=True)


def build_operator_state(
    normalized_vehicles: dict[str, dict[str, Any]],
    active_events: list[dict[str, Any]],
    current_severity_state: dict[str, Any],
    current_reports: dict[str, dict[str, Any]],
    current_chat_messages: dict[str, dict[str, Any]],
    current_map_state: dict[str, Any],
    now: datetime,
    llm_enabled: bool,
) -> dict[str, Any]:
    chat_list = _sort_newest(list(current_chat_messages.values()), "timestamp")[:100]
    report_list = _sort_newest(list(current_reports.values()), "created_at")
    return {
        "timestamp": now,
        "system_status": {
            "vehicle_count": len(normalized_vehicles),
            "active_event_count": len(active_events),
            "report_count": len(current_reports),
            "chat_message_count": len(current_chat_messages),
            "unacknowledged_chat_count": sum(
                1 for message in current_chat_messages.values() if not message.get("acknowledged")
            ),
            "llm_enabled": llm_enabled,
        },
        "map": current_map_state,
        "vehicles": normalized_vehicles,
        "active_events": active_events,
        "severity_state": current_severity_state,
        "reports": report_list,
        "chat_messages": chat_list,
    }
