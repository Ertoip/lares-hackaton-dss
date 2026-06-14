"""
Tests for the D3 triage scoring engine.
Run with:  python -m pytest dss_backend/tests/test_triage_engine.py -v
"""
import pytest
from datetime import datetime, timezone, timedelta

from dss_backend.core.triage_engine import (
    CRITICALITY_WEIGHTS,
    score_events,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_event(
    event_id: str,
    severity: str,
    event_kind: str,
    age_seconds: float = 60,
    vehicle_id: str = "surface_1",
) -> dict:
    ts = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    return {
        "event_id":   event_id,
        "severity":   severity,
        "event_kind": event_kind,
        "vehicle_id": vehicle_id,
        "domain":     "surface",
        "position":   {"lat": 51.0, "lon": 1.5},
        "description": f"Test event: {event_kind}",
        "timestamp":  ts,
    }


NOW = datetime.now(timezone.utc)


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_empty_list_returns_empty():
    assert score_events([], NOW) == []


def test_critical_ranks_above_low():
    events = [
        make_event("low",  "low",      "routine_check"),
        make_event("crit", "critical", "unknown_contact"),
    ]
    ranked = score_events(events, NOW)
    assert ranked[0]["event_id"] == "crit"
    assert ranked[1]["event_id"] == "low"


def test_ranks_are_sequential_from_one():
    events = [
        make_event("e1", "low",    "routine"),
        make_event("e2", "medium", "sensor_failure"),
        make_event("e3", "high",   "unknown_contact"),
    ]
    ranked = score_events(events, NOW)
    assert [r["rank"] for r in ranked] == [1, 2, 3]


def test_score_decreases_with_event_age():
    fresh = make_event("fresh", "high", "sensor_failure", age_seconds=5)
    stale = make_event("stale", "high", "sensor_failure", age_seconds=1800)
    ranked = score_events([stale, fresh], NOW)
    assert ranked[0]["event_id"] == "fresh"
    assert ranked[0]["score"] > ranked[1]["score"]


def test_threat_outranks_same_severity_routine():
    threat  = make_event("threat",  "high", "unknown_contact")
    routine = make_event("routine", "high", "routine_check")
    ranked  = score_events([routine, threat], NOW)
    assert ranked[0]["event_id"] == "threat"


def test_score_breakdown_keys_present():
    ranked = score_events([make_event("e1", "medium", "sensor_failure")], NOW)
    bd = ranked[0]["score_breakdown"]
    assert "criticality"       in bd
    assert "mission_relevance" in bd
    assert "time_urgency"      in bd


def test_criticality_weight_matches_constant():
    ranked = score_events([make_event("e1", "medium", "sensor_failure")], NOW)
    assert ranked[0]["score_breakdown"]["criticality"] == CRITICALITY_WEIGHTS["medium"]


def test_rationale_is_non_empty_string():
    ranked = score_events([make_event("e1", "critical", "hostile_contact")], NOW)
    r = ranked[0]["rationale"]
    assert isinstance(r, str) and len(r) > 30


def test_rationale_contains_severity_and_vehicle():
    ranked = score_events([make_event("e1", "high", "sensor_failure", vehicle_id="air_1")], NOW)
    rationale = ranked[0]["rationale"].lower()
    assert "high" in rationale
    assert "air_1" in rationale


def test_score_formula_critical_threat_fresh():
    """critical (4.0) × unknown_contact relevance (1.5) × very fresh (1.5) = 9.0"""
    event  = make_event("e1", "critical", "unknown_contact", age_seconds=5)
    ranked = score_events([event], NOW)
    assert ranked[0]["score"] == pytest.approx(4.0 * 1.5 * 1.5, rel=0.01)


def test_score_formula_low_routine_stale():
    """low (1.0) × routine relevance (1.0) × stale (0.6) = 0.6"""
    event  = make_event("e1", "low", "routine_check", age_seconds=2000)
    ranked = score_events([event], NOW)
    assert ranked[0]["score"] == pytest.approx(1.0 * 1.0 * 0.6, rel=0.01)


def test_event_without_timestamp_still_scores():
    event = {
        "event_id": "no_ts",
        "severity": "high",
        "event_kind": "sensor_failure",
        "vehicle_id": "sub_1",
    }
    ranked = score_events([event], NOW)
    assert len(ranked) == 1
    assert ranked[0]["score"] > 0


def test_multiple_events_ordered_by_score():
    events = [
        make_event("low_stale",   "low",      "routine",         age_seconds=1000),
        make_event("crit_fresh",  "critical", "unknown_contact", age_seconds=10),
        make_event("med_medium",  "medium",   "sensor_failure",  age_seconds=90),
    ]
    ranked = score_events(events, NOW)
    scores = [r["score"] for r in ranked]
    assert scores == sorted(scores, reverse=True)
