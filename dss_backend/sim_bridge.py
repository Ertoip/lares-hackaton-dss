"""
Simulation bridge — subscribes to ws://SIM_BASE_URL/ws (full snapshot every 1 s)
and merges all simulation state into the local dss_backend:
  - vehicles     → vehicles dict (with sigma/uncertainty pass-through)
  - contacts     → sim_raw["contacts"]
  - alerts       → sim_raw["alerts"]
  - weather      → sim_raw["weather"]
  - ais          → sim_raw["ais"]
  - mothership   → sim_raw["mothership"]
"""
import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Any

from dss_backend.link_status import apply_link_status
from dss_backend.state import sim_raw, state_lock, utc_now, vehicles

logger = logging.getLogger(__name__)

SIM_BASE_URL = os.getenv("SIM_BASE_URL", "http://10.22.68.54:8000")
_WS_URL = SIM_BASE_URL.replace("http://", "ws://").replace("https://", "wss://") + "/ws"

_SIM_ID_MAP: dict[str, str] = {
    "UAV-1": "air_1",
    "UAV-2": "air_2",
    "USV-1": "surface_1",
    "USV-2": "surface_2",
    "UUV-1": "sub_1",
    "UUV-2": "sub_2",
}
_TYPE_DOMAIN: dict[str, str] = {
    "UAV": "air",
    "USV": "surface",
    "UUV": "subsurface",
}


def _translate_vehicle(
    sim_v: dict[str, Any], received_at: datetime
) -> tuple[str, dict[str, Any]] | None:
    """Return (local_id, state_dict) or None if the vehicle ID is unknown."""
    sim_id = sim_v.get("id", "")
    local_id = _SIM_ID_MAP.get(sim_id)
    if local_id is None:
        return None

    domain = _TYPE_DOMAIN.get(sim_v.get("type", ""), "air")
    stale = bool(sim_v.get("stale", False))
    in_blackout = bool(sim_v.get("in_blackout", False))

    lat = sim_v.get("lat") or sim_v.get("fix_lat")
    lon = sim_v.get("lon") or sim_v.get("fix_lon")
    alt = sim_v.get("z_m") or sim_v.get("fix_z_m", 0.0)
    heading = sim_v.get("heading") or sim_v.get("fix_heading", 0)
    speed_knots = float(sim_v.get("speed_knots") or 0.0)

    link: dict[str, Any] = {
        "communication_mode": sim_v.get("link_type", "rf"),
        "in_blackout": in_blackout,
        "link_quality": sim_v.get("link_quality", 1.0),
    }
    if not stale:
        link["last_heartbeat_received_at"] = received_at
    if in_blackout:
        link["reported_status"] = "expected_blackout"

    state: dict[str, Any] = {
        "vehicle_id": local_id,
        "domain": domain,
        "status": sim_v.get("status", "nominal"),
        "position": {"lat": lat, "lon": lon, "alt_m": alt},
        "velocity": {"speed_mps": speed_knots * 0.5144, "heading_deg": heading},
        "battery": {"percentage": sim_v.get("battery_pct", 100), "bingo_threshold": 15},
        "sensors": sim_v.get("sensor_health") or {},
        "capabilities": sim_v.get("capabilities") or [],
        "current_task_id": sim_v.get("current_task"),
        "telemetry_received_at": received_at,
        "link": link,
        # Simulation uncertainty cone fields (passed through for map rendering)
        "sigma_m": sim_v.get("sigma_m"),
        "sigma_along_m": sim_v.get("sigma_along_m"),
        "sigma_cross_m": sim_v.get("sigma_cross_m"),
        "uncertainty_heading_deg": sim_v.get("uncertainty_heading_deg"),
        "age_sec": sim_v.get("age_sec"),
        "waypoint": sim_v.get("waypoint"),
        "rtb": sim_v.get("rtb", False),
        "submerged": sim_v.get("submerged", False),
    }
    return local_id, state


async def _apply_snapshot(snapshot: dict[str, Any], received_at: datetime) -> None:
    async with state_lock:
        for sim_v in snapshot.get("vehicles", []):
            result = _translate_vehicle(sim_v, received_at)
            if result is None:
                continue
            local_id, state = result
            if local_id not in vehicles:
                continue
            vehicles[local_id].update(state)
            apply_link_status(local_id, received_at)

        sim_raw["mothership"] = snapshot.get("mothership")
        sim_raw["contacts"] = snapshot.get("contacts", [])
        sim_raw["alerts"] = snapshot.get("alerts", [])
        sim_raw["weather"] = snapshot.get("weather")
        sim_raw["ais"] = snapshot.get("ais", [])
        sim_raw["sim_time_sec"] = snapshot.get("sim_time_sec")


async def poll_simulation() -> None:
    """Long-running background task: subscribe to simulation WS and sync state."""
    from websockets.asyncio.client import connect

    backoff = 2.0
    while True:
        try:
            async with connect(_WS_URL, ping_interval=None) as ws:
                logger.info("Sim bridge: connected to %s", _WS_URL)
                backoff = 2.0
                async for raw in ws:
                    try:
                        snapshot = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    await _apply_snapshot(snapshot, utc_now())
        except Exception as exc:
            logger.warning("Sim bridge: disconnected — %s. Retry in %.0fs", exc, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 1.5, 30.0)
