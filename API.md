# DSS Backend API Documentation

## Overview

This backend is the baseline DSS input layer for a maritime multi-domain drone mission project.

The DSS receives messages from six external vehicles over a single WebSocket:

- `air_1`
- `air_2`
- `surface_1`
- `surface_2`
- `sub_1`
- `sub_2`

Vehicles are not modeled as an internal simulation. From the DSS perspective, they are external systems sending direct messages.

## Base URL

```text
http://localhost:8001
```

## Allowed Vehicles

| Vehicle ID | Domain |
| --- | --- |
| `air_1` | `air` |
| `air_2` | `air` |
| `surface_1` | `surface` |
| `surface_2` | `surface` |
| `sub_1` | `subsurface` |
| `sub_2` | `subsurface` |

Every incoming message must contain a valid `vehicle_id` and matching `domain`.

## WebSocket Endpoint

```http
WS /dss/ws/vehicles
```

All vehicles send messages to this single WebSocket. Message routing is based on the `message_type` field.

Supported message types:

- `heartbeat`
- `telemetry`
- `event`
- `link_state`

The old wrapper format is not used. Send direct vehicle messages only.

## Acknowledgements

Successful message acknowledgement:

```json
{
  "ok": true,
  "received_message_type": "heartbeat",
  "vehicle_id": "air_1"
}
```

Invalid message acknowledgement:

```json
{
  "ok": false,
  "error": "Invalid vehicle_id"
}
```

Validation failure acknowledgement:

```json
{
  "ok": false,
  "error": "Validation failed",
  "details": []
}
```

## Heartbeat Message

Heartbeat means the vehicle is currently reachable.

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

Required fields:

| Field | Type | Notes |
| --- | --- | --- |
| `message_type` | string | Must be `heartbeat` |
| `vehicle_id` | string | One of the six allowed vehicles |
| `timestamp` | ISO datetime | Vehicle-provided timestamp |
| `sequence` | integer | Non-negative sequence number |
| `domain` | string | Must match vehicle ID |
| `communication_mode` | string | `radio`, `acoustic`, `satellite`, or `cellular` |
| `expected_interval_ms` | integer | Positive heartbeat interval |

Expected heartbeat intervals:

| Domain | Expected Interval |
| --- | --- |
| `air` | `1000 ms` |
| `surface` | `3000 ms` |
| `subsurface` | `30000 ms` when connected |

## Telemetry Message

Telemetry describes vehicle physical state, battery, sensors, capabilities, and current task.

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

Position rules:

| Field | Notes |
| --- | --- |
| `lat` | Required, `-90` to `90` |
| `lon` | Required, `-180` to `180` |
| `alt` | Optional, useful for air vehicles |
| `depth` | Optional, useful for subsurface vehicles |

Sensor states:

```text
ok, degraded, fault, unavailable
```

Vehicle statuses:

```text
active, idle, standby, fault, returning, offline
```

## Event Message

Events describe notable detections or vehicle-reported occurrences.

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

Severity values:

```text
low, medium, high, critical
```

Events are stored in the in-memory `events` map by `event_id`.

## Link State Message

Link state describes communication context. It is especially useful for subsurface drones that may intentionally go silent.

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

Link statuses:

```text
online, degraded, unstable, lost_link, expected_blackout, late_contact
```

Communication modes:

```text
radio, acoustic, satellite, cellular
```

If `status` is `expected_blackout`, `expected_next_contact_window` is required.

## Derived Link Status

A background task recalculates link status for every vehicle once per second. This allows link status to degrade even when no new messages arrive.

Air drones:

| Time Since Last Heartbeat | Status |
| --- | --- |
| `0-2s` | `online` |
| `2-5s` | `degraded` |
| `5-10s` | `unstable` |
| `>10s` | `lost_link` |

Surface drones:

| Time Since Last Heartbeat | Status |
| --- | --- |
| `0-6s` | `online` |
| `6-12s` | `degraded` |
| `12-20s` | `unstable` |
| `>20s` | `lost_link` |

Subsurface drones:

| Condition | Status |
| --- | --- |
| Reported `expected_blackout` and still before contact window end | `expected_blackout` |
| Past expected contact window end | `late_contact` |
| More than 5 minutes past expected contact window end | `lost_link` |
| Connected with heartbeat age `0-60s` | `online` |
| Connected with heartbeat age `60-120s` | `degraded` |
| Connected with heartbeat age `120-180s` | `unstable` |
| Connected with heartbeat age `>180s` | `lost_link` |

## REST Debug Endpoints

### Health

```http
GET /dss/health
```

Response:

```json
{
  "status": "ok"
}
```

### Full State

```http
GET /dss/state
```

Response:

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

### Vehicles

```http
GET /dss/vehicles
```

Returns the full `vehicles` map.

### Single Vehicle

```http
GET /dss/vehicles/{vehicle_id}
```

Example:

```http
GET /dss/vehicles/air_1
```

Returns `404` if the vehicle ID is not one of the allowed vehicles.

### Events

```http
GET /dss/events
```

Returns the full `events` map.

## Local Development

Create a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r dss_backend/requirements.txt
```

Run the backend:

```bash
uvicorn dss_backend.main:app --reload --port 8001
```

Run the sample WebSocket client:

```bash
python dss_backend/test_client.py
```

## Notes

State is in memory only. Restarting the backend clears all vehicle and event state.

This baseline intentionally does not include a frontend, simulation, command output APIs, persistence, authentication, or mission planning logic.
