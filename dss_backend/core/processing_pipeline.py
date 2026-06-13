import logging
from typing import Any

from dss_backend.core.anomaly_detector import detect_anomalies
from dss_backend.core.chat_message_builder import build_chat_message_from_report
from dss_backend.core.llm_report_builder import get_report_builder
from dss_backend.core.map_builder import build_map_state
from dss_backend.core.operator_state_builder import build_operator_state
from dss_backend.core.report_trigger import should_generate_report
from dss_backend.core.severity_aggregator import aggregate_severity, merge_active_events
from dss_backend.core.state_manager import normalize_external_events, normalize_vehicles
from dss_backend.state import (
    chat_messages,
    dss_events,
    events,
    map_state,
    operator_state,
    reports,
    severity_state,
    utc_now,
    vehicles,
)


logger = logging.getLogger(__name__)


def _store_report(trigger: dict[str, Any], report_content: dict[str, Any], now) -> dict[str, Any]:
    report_id = f"report_{now.strftime('%Y%m%dT%H%M%S')}"
    return {
        "report_id": report_id,
        "created_at": now,
        "trigger_reason": trigger.get("trigger_reason"),
        "severity_score": trigger.get("severity_score"),
        "window_seconds": trigger.get("window_seconds"),
        "related_event_ids": [event.get("event_id") for event in trigger.get("events", [])],
        "cluster_fingerprint": trigger.get("cluster_fingerprint"),
        "title": report_content.get("title"),
        "summary": report_content.get("summary"),
        "situation": report_content.get("situation") or [],
        "why_it_matters": report_content.get("why_it_matters") or [],
        "operator_focus": report_content.get("operator_focus") or [],
        "assumptions": report_content.get("assumptions") or [],
        "urgency": report_content.get("urgency") or "high",
    }


def run_processing_pipeline() -> dict[str, Any]:
    now = utc_now()

    normalized_vehicles = normalize_vehicles(vehicles, now)
    detected_dss_events = detect_anomalies(normalized_vehicles, dss_events, now)
    dss_events.clear()
    dss_events.update(detected_dss_events)

    external_events = normalize_external_events(events)
    active_events = merge_active_events(external_events, dss_events)

    new_map_state = build_map_state(normalized_vehicles, active_events, now)
    new_severity_state = aggregate_severity(active_events, now)

    severity_state.clear()
    severity_state.update(new_severity_state)

    should_report, trigger = should_generate_report(new_severity_state, active_events, reports, now)
    report_builder = get_report_builder()
    if should_report and trigger:
        report_content = report_builder.build_report(trigger)
        report = _store_report(trigger, report_content, now)
        reports[report["report_id"]] = report
        logger.info("Generated DSS report %s for events %s", report["report_id"], report["related_event_ids"])
        try:
            chat_message = build_chat_message_from_report(report)
            chat_messages.setdefault(chat_message["message_id"], chat_message)
        except Exception as exc:
            logger.exception("Failed to create chat message for report %s: %s", report["report_id"], exc)
    elif new_severity_state.get("triggered"):
        logger.debug("DSS report skipped because cooldown or deduplication rules blocked it")

    map_state.clear()
    map_state.update(new_map_state)

    new_operator_state = build_operator_state(
        normalized_vehicles,
        active_events,
        new_severity_state,
        reports,
        chat_messages,
        new_map_state,
        now,
        report_builder.enabled,
    )
    operator_state.clear()
    operator_state.update(new_operator_state)
    return new_operator_state
