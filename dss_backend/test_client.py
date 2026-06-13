import asyncio
import json

import websockets


WS_URL = "ws://localhost:8000/dss/ws/vehicles"


async def main() -> None:
    heartbeat = {
        "message_type": "heartbeat",
        "vehicle_id": "air_1",
        "timestamp": "2026-01-01T12:00:00Z",
        "sequence": 184,
        "domain": "air",
        "communication_mode": "radio",
        "expected_interval_ms": 1000,
    }

    telemetry = {
        "message_type": "telemetry",
        "vehicle_id": "air_1",
        "timestamp": "2026-01-01T12:00:01Z",
        "domain": "air",
        "status": "active",
        "position": {
            "lat": 41.9028,
            "lon": 12.4964,
            "alt": 120,
        },
        "velocity": {
            "speed_mps": 14.2,
            "heading_deg": 82,
        },
        "battery": {
            "percentage": 76,
            "bingo_threshold": 20,
        },
        "sensors": {
            "camera": "ok",
            "radar": "ok",
            "sonar": "unavailable",
        },
        "capabilities": {
            "visual_isr": True,
            "radar_scan": True,
            "sonar_scan": False,
            "relay_comms": False,
        },
        "current_task_id": "task_scan_sector_a",
    }

    async with websockets.connect(WS_URL) as websocket:
        for message in (heartbeat, telemetry):
            await websocket.send(json.dumps(message))
            response = await websocket.recv()
            print(response)


if __name__ == "__main__":
    asyncio.run(main())
