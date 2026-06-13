# Maritime Multi-Domain DSS Backend

FastAPI backend input layer for a Decision Support System, DSS, managing six external unmanned vehicles:

- `air_1`, `air_2`
- `surface_1`, `surface_2`
- `sub_1`, `sub_2`

The DSS treats these vehicles as external entities. It does not simulate them internally. Vehicles send direct JSON messages to one DSS WebSocket, and the backend validates those messages, updates in-memory state, derives communication/link status, and exposes debug REST endpoints.

## What This Backend Does

- Receives vehicle messages over one WebSocket: `WS /dss/ws/vehicles`
- Supports `heartbeat`, `telemetry`, `event`, and `link_state` messages
- Validates `vehicle_id`, `domain`, message shape, and heartbeat interval
- Maintains in-memory `vehicles` and `events` maps
- Derives link status from heartbeat age and subsurface blackout windows
- Recalculates link status in the background even when no new message arrives
- Exposes REST endpoints for health checks and state inspection

## What This Backend Does Not Do

- It does not include a frontend
- It does not simulate drones
- It does not persist state to a database
- It does not provide command output APIs yet
- It does not perform mission planning or autonomy decisions yet

## Project Structure

```text
dss_backend/
  __init__.py
  main.py          # FastAPI app setup and background task lifecycle
  models.py        # Pydantic validation models for incoming messages
  state.py         # In-memory vehicles/events maps and vehicle validation
  websocket.py     # WebSocket endpoint and message routing
  link_status.py   # Derived link-status logic
  routers.py       # REST debug endpoints
  requirements.txt # Runtime dependencies
  test_client.py   # Small WebSocket client for local testing
API.md             # Detailed API reference
README.md          # Developer guide
```

## Run Locally

Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r dss_backend/requirements.txt
```

Run the API:

```bash
uvicorn dss_backend.main:app --reload
```

The backend will be available at:

```text
http://localhost:8000
```

Open generated FastAPI docs:

```text
http://localhost:8000/docs
```

Run the sample WebSocket client in another terminal:

```bash
python dss_backend/test_client.py
```

## Allowed Vehicles

Only these six vehicles are accepted:

| Vehicle ID | Required Domain |
| --- | --- |
| `air_1` | `air` |
| `air_2` | `air` |
| `surface_1` | `surface` |
| `surface_2` | `surface` |
| `sub_1` | `subsurface` |
| `sub_2` | `subsurface` |

Every incoming vehicle message must include both `vehicle_id` and `domain`. The backend rejects messages where the domain does not match the vehicle ID.

Example invalid message:

```json
{
  "message_type": "heartbeat",
  "vehicle_id": "air_1",
  "domain": "surface"
}
```

The backend returns:

```json
{
  "ok": false,
  "error": "Domain does not match vehicle_id"
}
```

## WebSocket Endpoint

```http
WS /dss/ws/vehicles
```

This is the only vehicle input socket. All six vehicles send messages to this endpoint. The backend decides how to process the message using the `message_type` field.

Supported `message_type` values:

| Message Type | Purpose |
| --- | --- |
| `heartbeat` | Confirms that a vehicle is reachable right now |
| `telemetry` | Updates position, velocity, battery, sensors, capabilities, and current task |
| `event` | Stores a vehicle-reported event, detection, or alert |
| `link_state` | Updates communication context, especially planned subsurface blackout windows |

The backend does not use the old wrapper format with `type`, `source`, and `payload`. Send direct vehicle messages only.

## WebSocket Acknowledgements

Every valid message receives an acknowledgement:

```json
{
  "ok": true,
  "received_message_type": "heartbeat",
  "vehicle_id": "air_1"
}
```

Invalid messages receive an error response on the same WebSocket connection:

```json
{
  "ok": false,
  "error": "Invalid vehicle_id"
}
```

Validation errors include details from Pydantic:

```json
{
  "ok": false,
  "error": "Validation failed",
  "details": []
}
```

## Message Flow

For every incoming WebSocket message, the backend performs this flow:

1. Parse JSON
2. Validate `message_type`
3. Validate the Pydantic schema for that message type
4. Check that `vehicle_id` is one of the six allowed vehicles
5. Check that `domain` matches the vehicle ID
6. Route the message by `message_type`
7. Update vehicle state or event state
8. Recalculate link status when relevant
9. Send an acknowledgement back through the WebSocket

## Heartbeat Messages

Heartbeat messages are used to derive whether the vehicle link is `online`, `degraded`, `unstable`, or `lost_link`.

Example:

```json
{
  "message_type": "heartbeat",
  "vehicle_id": "air_1",
  "timestamp": "2026-01-01T12:00:00Z",
  "sequence": 184,
  "domain": "air",
  "communication_mode": "radio",
  "expected_interval_ms": 1000
}
```

Required heartbeat intervals:

| Domain | Required `expected_interval_ms` |
| --- | --- |
| `air` | `1000` |
| `surface` | `3000` |
| `subsurface` | `30000` |

If an air drone sends `expected_interval_ms = 3000`, the message is rejected because air drones are expected every 1 second.

## Telemetry Messages

Telemetry messages update the vehicle's physical and mission state.

Example:

```json
{
  "message_type": "telemetry",
  "vehicle_id": "air_1",
  "timestamp": "2026-01-01T12:00:01Z",
  "domain": "air",
  "status": "active",
  "position": {
    "lat": 41.9028,
    "lon": 12.4964,
    "alt": 120
  },
  "velocity": {
    "speed_mps": 14.2,
    "heading_deg": 82
  },
  "battery": {
    "percentage": 76,
    "bingo_threshold": 20
  },
  "sensors": {
    "camera": "ok",
    "radar": "ok",
    "sonar": "unavailable"
  },
  "capabilities": {
    "visual_isr": true,
    "radar_scan": true,
    "sonar_scan": false,
    "relay_comms": false
  },
  "current_task_id": "task_scan_sector_a"
}
```

Telemetry updates these fields in the vehicle state:

| State Field | Meaning |
| --- | --- |
| `telemetry` | Full last telemetry message |
| `status` | Vehicle-reported operating status |
| `position` | Last reported latitude, longitude, altitude, or depth |
| `velocity` | Last reported speed and heading |
| `battery` | Battery percentage and bingo threshold |
| `sensors` | Sensor health states |
| `capabilities` | Vehicle capabilities |
| `current_task_id` | Current task identifier, if any |

Telemetry does not by itself prove the link is currently healthy. Link status is primarily based on heartbeat timing and explicit `link_state` messages.

## Event Messages

Event messages represent notable vehicle-reported observations or alerts.

Example:

```json
{
  "message_type": "event",
  "event_id": "evt_001",
  "timestamp": "2026-01-01T12:22:00Z",
  "vehicle_id": "surface_1",
  "domain": "surface",
  "event_kind": "unknown_contact",
  "severity": "high",
  "position": {
    "lat": 41.9101,
    "lon": 12.5012
  },
  "description": "Fast unknown contact detected near sector B",
  "metadata": {
    "ais": "off",
    "speed_knots": 35,
    "behavior": "suspicious"
  }
}
```

Events are stored in the global `events` map by `event_id`.

If another event arrives with the same `event_id`, it overwrites the previous event for now. This is acceptable for the current in-memory debug baseline.

## Link State Messages

Link state messages describe communication context. They are especially important for subsurface vehicles.

Example expected blackout:

```json
{
  "message_type": "link_state",
  "vehicle_id": "sub_1",
  "timestamp": "2026-01-01T12:05:00Z",
  "domain": "subsurface",
  "communication_mode": "acoustic",
  "status": "expected_blackout",
  "last_contact_at": "2026-01-01T12:00:00Z",
  "expected_next_contact_window": {
    "start": "2026-01-01T12:25:00Z",
    "end": "2026-01-01T12:30:00Z"
  }
}
```

This tells the DSS that `sub_1` is expected to be silent until its next contact window. Missing heartbeats during that period should not immediately become `lost_link`.

If `status` is `expected_blackout`, `expected_next_contact_window` is required.

## Derived Link Status

The backend recalculates link status for vehicles with link information once per second.

Air drones:

| Time Since Last Heartbeat | Link Status |
| --- | --- |
| `0-2s` | `online` |
| `2-5s` | `degraded` |
| `5-10s` | `unstable` |
| `>10s` | `lost_link` |

Surface drones:

| Time Since Last Heartbeat | Link Status |
| --- | --- |
| `0-6s` | `online` |
| `6-12s` | `degraded` |
| `12-20s` | `unstable` |
| `>20s` | `lost_link` |

Subsurface drones:

| Condition | Link Status |
| --- | --- |
| In expected blackout and before contact window end | `expected_blackout` |
| Past expected contact window end | `late_contact` |
| More than 5 minutes past contact window end | `lost_link` |
| Connected with heartbeat age `0-60s` | `online` |
| Connected with heartbeat age `60-120s` | `degraded` |
| Connected with heartbeat age `120-180s` | `unstable` |
| Connected with heartbeat age `>180s` | `lost_link` |

Vehicles that have never sent heartbeat or link-state information remain as empty dictionaries in the initial in-memory state.

## REST Debug Endpoints

These endpoints are intended for development and debugging. They expose the current in-memory DSS state.

## `GET /dss/health`

Basic health check endpoint.

Use this to confirm the FastAPI process is running.

Example request:

```bash
curl http://localhost:8000/dss/health
```

Example response:

```json
{
  "status": "ok"
}
```

## `GET /dss/state`

Returns the complete in-memory DSS debug state.

This includes both vehicle state and event state:

```json
{
  "vehicles": {},
  "events": {}
}
```

Example request:

```bash
curl http://localhost:8000/dss/state
```

Example initial response:

```json
{
  "vehicles": {
    "air_1": {},
    "air_2": {},
    "surface_1": {},
    "surface_2": {},
    "sub_1": {},
    "sub_2": {}
  },
  "events": {}
}
```

Use this endpoint when you want a full snapshot of what the DSS currently knows.

## `GET /dss/vehicles`

Returns only the vehicle state map.

Example request:

```bash
curl http://localhost:8000/dss/vehicles
```

Example response after `air_1` sends heartbeat and telemetry:

```json
{
  "air_1": {
    "vehicle_id": "air_1",
    "domain": "air",
    "status": "active",
    "position": {
      "lat": 41.9028,
      "lon": 12.4964,
      "alt": 120,
      "depth": null
    },
    "link": {
      "status": "online",
      "communication_mode": "radio",
      "expected_interval_ms": 1000
    }
  },
  "air_2": {},
  "surface_1": {},
  "surface_2": {},
  "sub_1": {},
  "sub_2": {}
}
```

Actual responses may include additional fields such as `last_heartbeat`, `telemetry`, `status_updated_at`, and timestamp values.

## `GET /dss/vehicles/{vehicle_id}`

Returns the current state for one vehicle.

Example request:

```bash
curl http://localhost:8000/dss/vehicles/air_1
```

Example response for a known vehicle that has not sent any messages yet:

```json
{}
```

Example response for an invalid vehicle ID:

```json
{
  "detail": "Vehicle not found"
}
```

Invalid vehicle IDs return HTTP `404`.

Valid vehicle IDs are always present in the vehicle map, even if their current state is still empty.

## `GET /dss/events`

Returns all stored events keyed by `event_id`.

Example request:

```bash
curl http://localhost:8000/dss/events
```

Example initial response:

```json
{}
```

Example response after an event:

```json
{
  "evt_001": {
    "message_type": "event",
    "event_id": "evt_001",
    "timestamp": "2026-01-01T12:22:00Z",
    "vehicle_id": "surface_1",
    "domain": "surface",
    "event_kind": "unknown_contact",
    "severity": "high",
    "position": {
      "lat": 41.9101,
      "lon": 12.5012,
      "alt": null,
      "depth": null
    },
    "description": "Fast unknown contact detected near sector B",
    "metadata": {
      "ais": "off",
      "speed_knots": 35,
      "behavior": "suspicious"
    }
  }
}
```

## Local WebSocket Test Client

The included client connects to:

```text
ws://localhost:8000/dss/ws/vehicles
```

It sends:

- one `heartbeat` message for `air_1`
- one `telemetry` message for `air_1`

Run it after starting the API:

```bash
python dss_backend/test_client.py
```

Expected output:

```json
{"ok":true,"received_message_type":"heartbeat","vehicle_id":"air_1"}
{"ok":true,"received_message_type":"telemetry","vehicle_id":"air_1"}
```

Then inspect state:

```bash
curl http://localhost:8000/dss/vehicles/air_1
```

## API Reference

This README is the developer quick-start guide. See `API.md` for the fuller API contract and additional examples.
