from typing import Any


def _derive_severity(report: dict[str, Any]) -> str:
    urgency = report.get("urgency")
    if urgency in {"critical", "high", "medium", "low"}:
        return urgency

    score = report.get("severity_score") or 0
    if score >= 18:
        return "critical"
    if score >= 9:
        return "high"
    if score >= 6:
        return "medium"
    return "low"


def build_chat_message_from_report(report: dict[str, Any]) -> dict[str, Any]:
    severity = _derive_severity(report)
    related_event_ids = report.get("related_event_ids") or []
    return {
        "message_id": f"chat_{report['report_id']}",
        "timestamp": report.get("created_at"),
        "sender": "dss",
        "message_type": "anomaly_report",
        "severity": severity,
        "title": report.get("title"),
        "body": report.get("summary"),
        "linked_event_ids": related_event_ids,
        "linked_report_id": report.get("report_id"),
        "map_focus": {
            "type": "events" if related_event_ids else "none",
            "ids": related_event_ids,
        },
        "details": {
            "situation": report.get("situation") or [],
            "why_it_matters": report.get("why_it_matters") or [],
            "operator_focus": report.get("operator_focus") or [],
            "assumptions": report.get("assumptions") or [],
        },
        "severity_score": report.get("severity_score"),
        "requires_operator_attention": severity in {"high", "critical"},
        "acknowledged": False,
    }
