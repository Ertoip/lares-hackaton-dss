import asyncio
import json
import math
import os
import signal
from datetime import datetime, timezone

import websockets


WS_URL = os.getenv("DSS_WS_URL", "ws://localhost:8001/dss/ws/vehicles")

TICK_SECONDS = 1.0

# Circle centres
_air1_lat     = 41.9028
_air1_lon     = 12.4964
_surface1_lat = 41.9051
_surface1_lon = 12.4984

# Angular speed: radians per tick. 0.05 ≈ full circle in ~125 s
_AIR_OMEGA     = 0.05
_SURFACE_OMEGA = 0.035

# Orbit radii in degrees
_AIR_RLAT, _AIR_RLON         = 0.006, 0.009
_SURFACE_RLAT, _SURFACE_RLON = 0.004, 0.006


def _heading(prev_lat, prev_lon, cur_lat, cur_lon) -> float:
    d_north = (cur_lat - prev_lat) * 111320
    d_east  = (cur_lon - prev_lon) * 111320 * math.cos(math.radians(cur_lat))
    return round(math.degrees(math.atan2(d_east, d_north)) % 360, 1)


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _air1_heartbeat(seq: int) -> dict:
    return {
        "message_type": "heartbeat",
        "vehicle_id": "air_1",
        "timestamp": _ts(),
        "sequence": seq,
        "domain": "air",
        "communication_mode": "radio",
        "expected_interval_ms": 1000,
    }


def _air1_telemetry(lat: float, lon: float, battery: int, heading: float = 0) -> dict:
    return {
        "message_type": "telemetry",
        "vehicle_id": "air_1",
        "timestamp": _ts(),
        "domain": "air",
        "status": "active",
        "position": {"lat": lat, "lon": lon, "alt": 120},
        "velocity": {"speed_mps": 14.2, "heading_deg": heading},
        "battery": {"percentage": battery, "bingo_threshold": 20},
        "sensors": {"camera": "ok", "radar": "ok", "sonar": "unavailable"},
        "capabilities": {"visual_isr": True, "radar_scan": True, "sonar_scan": False, "relay_comms": False},
        "current_task_id": "task_scan_sector_a",
    }


def _surface1_heartbeat(seq: int) -> dict:
    return {
        "message_type": "heartbeat",
        "vehicle_id": "surface_1",
        "timestamp": _ts(),
        "sequence": seq,
        "domain": "surface",
        "communication_mode": "radio",
        "expected_interval_ms": 3000,
    }


def _surface1_telemetry(lat: float, lon: float, heading: float = 0) -> dict:
    return {
        "message_type": "telemetry",
        "vehicle_id": "surface_1",
        "timestamp": _ts(),
        "domain": "surface",
        "status": "active",
        "position": {"lat": lat, "lon": lon},
        "velocity": {"speed_mps": 6.1, "heading_deg": heading},
        "battery": {"percentage": 82, "bingo_threshold": 25},
        "sensors": {"camera": "ok", "radar": "ok", "sonar": "ok"},
        "capabilities": {"visual_isr": True, "radar_scan": True, "sonar_scan": True, "relay_comms": True},
        "current_task_id": "task_patrol_sector_b",
    }


def _surface1_event(lat: float, lon: float) -> dict:
    return {
        "message_type": "event",
        "event_id": "evt_001",
        "timestamp": _ts(),
        "vehicle_id": "surface_1",
        "domain": "surface",
        "event_kind": "unknown_contact",
        "severity": "medium",
        "position": {"lat": lat + 0.005, "lon": lon + 0.003},
        "description": "Fast unknown contact detected near sector B",
        "metadata": {"ais": "off", "speed_knots": 35, "behavior": "suspicious"},
    }


async def main() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, stop.set)
    loop.add_signal_handler(signal.SIGTERM, stop.set)

    seq = 0
    battery = 18  # start low to keep anomaly active

    print(f"Connecting to {WS_URL} — Ctrl-C to stop")

    async with websockets.connect(WS_URL) as ws:
        print("Connected. Sending ticks every 1 s...\n")
        air_lat, air_lon = _air1_lat, _air1_lon
        sur_lat, sur_lon = _surface1_lat, _surface1_lon
        while not stop.is_set():
            seq += 1
            angle_air = seq * _AIR_OMEGA
            angle_sur = seq * _SURFACE_OMEGA + 1.0

            prev_air_lat, prev_air_lon = air_lat, air_lon
            prev_sur_lat, prev_sur_lon = sur_lat, sur_lon

            air_lat = _air1_lat    + _AIR_RLAT     * math.sin(angle_air)
            air_lon = _air1_lon    + _AIR_RLON     * math.cos(angle_air)
            sur_lat = _surface1_lat + _SURFACE_RLAT * math.sin(angle_sur)
            sur_lon = _surface1_lon + _SURFACE_RLON * math.cos(angle_sur)

            air_hdg = _heading(prev_air_lat, prev_air_lon, air_lat, air_lon)
            sur_hdg = _heading(prev_sur_lat, prev_sur_lon, sur_lat, sur_lon)

            messages = [
                _air1_heartbeat(seq),
                _air1_telemetry(air_lat, air_lon, battery, air_hdg),
                _surface1_heartbeat(seq),
                _surface1_telemetry(sur_lat, sur_lon, sur_hdg),
            ]
            # Send the event every 5 ticks so it stays active
            if seq % 5 == 0:
                messages.append(_surface1_event(sur_lat, sur_lon))

            for msg in messages:
                await ws.send(json.dumps(msg))
                await ws.recv()  # consume ack

            print(f"\r[tick {seq:>4}]  air ({air_lat:.5f}, {air_lon:.5f})  "
                  f"surface ({sur_lat:.5f}, {sur_lon:.5f})", end="", flush=True)

            await asyncio.sleep(TICK_SECONDS)

    print("\nStopped.")


if __name__ == "__main__":
    asyncio.run(main())
