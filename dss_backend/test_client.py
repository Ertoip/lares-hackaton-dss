import asyncio
import json
import os
import urllib.request
from datetime import datetime, timezone

import websockets


WS_URL = os.getenv("DSS_WS_URL", "ws://localhost:8001/dss/ws/vehicles")
HTTP_URL = os.getenv("DSS_HTTP_URL", "http://localhost:8001")


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def get_json(path: str) -> object:
    with urllib.request.urlopen(f"{HTTP_URL}{path}", timeout=5) as response:
        return json.loads(response.read().decode())


async def main() -> None:
    air_heartbeat = {
        "message_type": "heartbeat",
        "vehicle_id": "air_1",
        "timestamp": timestamp(),
        "sequence": 184,
        "domain": "air",
        "communication_mode": "radio",
        "expected_interval_ms": 1000,
    }

    air_low_battery_telemetry = {
        "message_type": "telemetry",
        "vehicle_id": "air_1",
        "timestamp": timestamp(),
        "domain": "air",
        "status": "active",
        "position": {"lat": 41.9028, "lon": 12.4964, "alt": 120},
        "velocity": {"speed_mps": 14.2, "heading_deg": 82},
        "battery": {"percentage": 18, "bingo_threshold": 20},
        "sensors": {"camera": "ok", "radar": "ok", "sonar": "unavailable"},
        "capabilities": {
            "visual_isr": True,
            "radar_scan": True,
            "sonar_scan": False,
            "relay_comms": False,
        },
        "current_task_id": "task_scan_sector_a",
    }

    surface_heartbeat = {
        "message_type": "heartbeat",
        "vehicle_id": "surface_1",
        "timestamp": timestamp(),
        "sequence": 1,
        "domain": "surface",
        "communication_mode": "radio",
        "expected_interval_ms": 3000,
    }

    surface_telemetry = {
        "message_type": "telemetry",
        "vehicle_id": "surface_1",
        "timestamp": timestamp(),
        "domain": "surface",
        "status": "active",
        "position": {"lat": 41.9051, "lon": 12.4984},
        "velocity": {"speed_mps": 6.1, "heading_deg": 115},
        "battery": {"percentage": 82, "bingo_threshold": 25},
        "sensors": {"camera": "ok", "radar": "ok", "sonar": "ok"},
        "capabilities": {
            "visual_isr": True,
            "radar_scan": True,
            "sonar_scan": True,
            "relay_comms": True,
        },
        "current_task_id": "task_patrol_sector_b",
    }

    surface_event = {
        "message_type": "event",
        "event_id": "evt_001",
        "timestamp": timestamp(),
        "vehicle_id": "surface_1",
        "domain": "surface",
        "event_kind": "unknown_contact",
        "severity": "medium",
        "position": {"lat": 41.9101, "lon": 12.5012},
        "description": "Fast unknown contact detected near sector B",
        "metadata": {"ais": "off", "speed_knots": 35, "behavior": "suspicious"},
    }

    messages = (
        air_heartbeat,
        air_low_battery_telemetry,
        surface_heartbeat,
        surface_telemetry,
        surface_event,
    )

    async with websockets.connect(WS_URL) as websocket:
        for message in messages:
            await websocket.send(json.dumps(message))
            print(await websocket.recv())

    print(json.dumps(get_json("/dss/severity"), indent=2))
    print(json.dumps(get_json("/dss/chat?limit=5"), indent=2))


if __name__ == "__main__":
    asyncio.run(main())
