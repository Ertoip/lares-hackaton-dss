"""
Triage Engine — D3 decision class.

Scores and ranks active events by:
    score = criticality_weight × mission_relevance × time_urgency

All weights and thresholds are declared constants so the objective function
is auditable and explainable to the operator.
"""
from datetime import datetime, timezone
from typing import Any


# ── Weights ───────────────────────────────────────────────────────────────────

CRITICALITY_WEIGHTS: dict[str, float] = {
    "critical": 4.0,
    "high":     3.0,
    "medium":   2.0,
    "low":      1.0,
}

# Keywords matched (substring) against event_kind → (weight, operator label)
_RELEVANCE_RULES: list[tuple[str, float, str]] = [
    ("hostile",          1.5, "direct hostile activity"),
    ("threat",           1.5, "direct threat to mission"),
    ("unknown_contact",  1.5, "unidentified contact in sector"),
    ("dark_vessel",      1.4, "vessel running without AIS"),
    ("bingo",            1.3, "vehicle at risk of loss — bingo fuel"),
    ("battery_low",      1.3, "vehicle at risk of loss — low battery"),
    ("sensor_failure",   1.2, "mission capability degraded"),
    ("capability",       1.2, "mission capability degraded"),
    ("gps",              1.2, "navigation integrity compromised"),
    ("position_drift",   1.2, "navigation integrity compromised"),
    ("lost_link",        1.1, "communications affected"),
    ("acoustic",         1.1, "acoustic link affected"),
    ("comms",            1.1, "communications affected"),
]

# Age thresholds (seconds) → (time_urgency weight, operator label)
_TIME_DECAY: list[tuple[float | None, float, str]] = [
    (30,   1.5, "detected moments ago — act now"),
    (120,  1.2, "detected in the last 2 minutes"),
    (300,  1.0, "detected in the last 5 minutes"),
    (900,  0.8, "5–15 minutes ago"),
    (None, 0.6, "older than 15 minutes"),
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _event_time(event: dict[str, Any]) -> datetime | None:
    """Return the best available timestamp for an event."""
    value = event.get("updated_at") or event.get("received_at") or event.get("timestamp")
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _mission_relevance(event_kind: str) -> tuple[float, str]:
    kind = (event_kind or "").lower()
    for keyword, weight, label in _RELEVANCE_RULES:
        if keyword in kind:
            return weight, label
    return 1.0, "routine operational note"


def _time_urgency(event: dict[str, Any], now: datetime) -> tuple[float, str]:
    ts = _event_time(event)
    if ts is None:
        return 1.0, "age unknown"
    age = max(0.0, (now - ts).total_seconds())
    for threshold, weight, label in _TIME_DECAY:
        if threshold is None or age <= threshold:
            return weight, label
    return 0.6, "older than 15 minutes"


def _rationale(
    event: dict[str, Any],
    criticality_w: float,
    relevance_w: float,
    relevance_label: str,
    time_w: float,
    time_label: str,
    score: float,
) -> str:
    severity  = (event.get("severity") or "unknown").upper()
    kind      = (event.get("event_kind") or "event").replace("_", " ").title()
    vehicle   = event.get("vehicle_id") or "unknown vehicle"
    desc      = event.get("description") or ""

    parts = [
        f"{severity} — {kind} on {vehicle}.",
        f"Mission relevance: {relevance_label}.",
        f"Timing: {time_label}.",
    ]
    if desc:
        parts.append(f"Detail: {desc}")
    parts.append(
        f"Score {score:.1f} = criticality {criticality_w:.0f}"
        f" × relevance {relevance_w:.1f}"
        f" × urgency {time_w:.1f}."
    )
    return " ".join(parts)


# ── Public API ────────────────────────────────────────────────────────────────

def score_events(
    active_events: list[dict[str, Any]],
    now: datetime,
) -> list[dict[str, Any]]:
    """
    Score and rank a list of active events.

    Returns a list sorted by descending score, each item containing:
        rank, event_id, event_kind, severity, score, score_breakdown,
        rationale, vehicle_id, domain, position, description.
    """
    results: list[dict[str, Any]] = []

    for event in active_events:
        severity     = event.get("severity") or "low"
        crit_w       = CRITICALITY_WEIGHTS.get(severity, 1.0)
        event_kind   = event.get("event_kind") or ""
        rel_w, rel_label  = _mission_relevance(event_kind)
        time_w, time_label = _time_urgency(event, now)

        score = round(crit_w * rel_w * time_w, 2)

        results.append({
            "event_id":   event.get("event_id"),
            "event_kind": event_kind,
            "severity":   severity,
            "score":      score,
            "score_breakdown": {
                "criticality":      crit_w,
                "mission_relevance": rel_w,
                "time_urgency":     time_w,
            },
            "rationale":  _rationale(event, crit_w, rel_w, rel_label, time_w, time_label, score),
            "vehicle_id": event.get("vehicle_id"),
            "domain":     event.get("domain"),
            "position":   event.get("position"),
            "description": event.get("description"),
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    for i, item in enumerate(results):
        item["rank"] = i + 1

    return results
