"""
Tests for the simulation bridge translator.
Run with:  python -m pytest dss_backend/tests/test_sim_bridge.py -v
"""
import pytest
from datetime import datetime, timezone

from dss_backend.sim_bridge import _translate_vehicle

NOW = datetime.now(timezone.utc)


def make_sim_vehicle(**overrides):
    base = {
        "id": "UAV-1",
        "type": "UAV",
        "lat": 36.0,
        "lon": -5.0,
        "fix_z_m": 120.0,
        "heading": 45.0,
        "speed_knots": 10.0,
        "battery_pct": 80,
        "link_type": "rf",
        "stale": False,
        "in_blackout": False,
        "sensor_health": {"camera": "ok", "radar": "ok"},
        "capabilities": {"imaging": True},
        "current_task": "patrol",
    }
    base.update(overrides)
    return base


# ── ID / domain mapping ───────────────────────────────────────────────────────

def test_uav1_maps_to_air1():
    result = _translate_vehicle(make_sim_vehicle(id="UAV-1", type="UAV"), NOW)
    local_id, state = result
    assert local_id == "air_1"
    assert state["domain"] == "air"


def test_uav2_maps_to_air2():
    local_id, _ = _translate_vehicle(make_sim_vehicle(id="UAV-2", type="UAV"), NOW)
    assert local_id == "air_2"


def test_usv1_maps_to_surface1():
    local_id, state = _translate_vehicle(make_sim_vehicle(id="USV-1", type="USV"), NOW)
    assert local_id == "surface_1"
    assert state["domain"] == "surface"


def test_usv2_maps_to_surface2():
    local_id, _ = _translate_vehicle(make_sim_vehicle(id="USV-2", type="USV"), NOW)
    assert local_id == "surface_2"


def test_uuv1_maps_to_sub1():
    local_id, state = _translate_vehicle(make_sim_vehicle(id="UUV-1", type="UUV"), NOW)
    assert local_id == "sub_1"
    assert state["domain"] == "subsurface"


def test_uuv2_maps_to_sub2():
    local_id, _ = _translate_vehicle(make_sim_vehicle(id="UUV-2", type="UUV"), NOW)
    assert local_id == "sub_2"


def test_unknown_id_returns_none():
    assert _translate_vehicle(make_sim_vehicle(id="BOAT-99"), NOW) is None


# ── Field translation ─────────────────────────────────────────────────────────

def test_position_fields():
    _, state = _translate_vehicle(make_sim_vehicle(lat=36.1, lon=-5.2, fix_z_m=50.0), NOW)
    pos = state["position"]
    assert pos["lat"] == 36.1
    assert pos["lon"] == -5.2
    assert pos["alt_m"] == 50.0


def test_speed_knots_converted_to_mps():
    _, state = _translate_vehicle(make_sim_vehicle(speed_knots=10.0), NOW)
    speed_mps = state["velocity"]["speed_mps"]
    assert abs(speed_mps - 10.0 * 0.5144) < 0.01


def test_heading_preserved():
    _, state = _translate_vehicle(make_sim_vehicle(heading=270.0), NOW)
    assert state["velocity"]["heading_deg"] == 270.0


def test_battery_percentage_passed_through():
    _, state = _translate_vehicle(make_sim_vehicle(battery_pct=42), NOW)
    assert state["battery"]["percentage"] == 42


def test_sensor_health_passed_through():
    sensors = {"camera": "degraded", "radar": "ok"}
    _, state = _translate_vehicle(make_sim_vehicle(sensor_health=sensors), NOW)
    assert state["sensors"] == sensors


def test_current_task_passed_through():
    _, state = _translate_vehicle(make_sim_vehicle(current_task="recon"), NOW)
    assert state["current_task_id"] == "recon"


def test_telemetry_received_at_is_set():
    _, state = _translate_vehicle(make_sim_vehicle(), NOW)
    assert state["telemetry_received_at"] == NOW


# ── Status flags ──────────────────────────────────────────────────────────────

def test_active_when_not_stale():
    _, state = _translate_vehicle(make_sim_vehicle(stale=False), NOW)
    assert state["status"] == "active"


def test_stale_when_stale():
    _, state = _translate_vehicle(make_sim_vehicle(stale=True), NOW)
    assert state["status"] == "stale"


def test_stale_vehicle_has_no_heartbeat_timestamp():
    _, state = _translate_vehicle(make_sim_vehicle(stale=True), NOW)
    assert "last_heartbeat_received_at" not in state["link"]


def test_fresh_vehicle_has_heartbeat_timestamp():
    _, state = _translate_vehicle(make_sim_vehicle(stale=False), NOW)
    assert state["link"]["last_heartbeat_received_at"] == NOW


def test_blackout_sets_reported_status():
    _, state = _translate_vehicle(make_sim_vehicle(in_blackout=True), NOW)
    assert state["link"]["reported_status"] == "expected_blackout"
    assert state["link"]["in_blackout"] is True


def test_no_blackout_has_no_reported_status():
    _, state = _translate_vehicle(make_sim_vehicle(in_blackout=False), NOW)
    assert "reported_status" not in state["link"]


# ── Fallback positions ────────────────────────────────────────────────────────

def test_falls_back_to_fix_lat_lon_when_lat_missing():
    _, state = _translate_vehicle(
        make_sim_vehicle(lat=None, lon=None, fix_lat=55.5, fix_lon=1.2), NOW
    )
    assert state["position"]["lat"] == 55.5
    assert state["position"]["lon"] == 1.2
