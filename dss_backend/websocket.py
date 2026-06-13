from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError

from dss_backend.link_status import apply_link_status
from dss_backend.models import (
    HeartbeatMessage,
    LinkStateMessage,
    TelemetryMessage,
    VehicleEventMessage,
    validate_message,
)
from dss_backend.state import events, state_lock, utc_now, validate_vehicle_and_domain, vehicles


router = APIRouter()


def _dump_message(message: Any) -> dict[str, Any]:
    return message.model_dump(mode="python")


async def _handle_heartbeat(message: HeartbeatMessage) -> None:
    received_at = utc_now()
    vehicle = vehicles[message.vehicle_id]
    vehicle["vehicle_id"] = message.vehicle_id
    vehicle["domain"] = message.domain
    vehicle["last_heartbeat"] = _dump_message(message)
    link = vehicle.setdefault("link", {})
    link["last_heartbeat_at"] = message.timestamp
    link["last_heartbeat_received_at"] = received_at
    link["communication_mode"] = message.communication_mode
    link["expected_interval_ms"] = message.expected_interval_ms
    link.pop("reported_status", None)
    link.pop("expected_next_contact_window", None)
    apply_link_status(message.vehicle_id, received_at)


async def _handle_telemetry(message: TelemetryMessage) -> None:
    vehicle = vehicles[message.vehicle_id]
    vehicle["vehicle_id"] = message.vehicle_id
    vehicle["domain"] = message.domain
    vehicle["telemetry"] = _dump_message(message)
    vehicle["status"] = message.status
    vehicle["position"] = message.position.model_dump(mode="python")
    vehicle["velocity"] = message.velocity.model_dump(mode="python")
    vehicle["battery"] = message.battery.model_dump(mode="python")
    vehicle["sensors"] = message.sensors.model_dump(mode="python")
    vehicle["capabilities"] = message.capabilities.model_dump(mode="python")
    vehicle["current_task_id"] = message.current_task_id


async def _handle_event(message: VehicleEventMessage) -> None:
    events[message.event_id] = _dump_message(message)


async def _handle_link_state(message: LinkStateMessage) -> None:
    vehicle = vehicles[message.vehicle_id]
    vehicle["vehicle_id"] = message.vehicle_id
    vehicle["domain"] = message.domain
    vehicle["last_link_state"] = _dump_message(message)
    link = vehicle.setdefault("link", {})
    link["communication_mode"] = message.communication_mode
    link["reported_status"] = message.status
    link["last_contact_at"] = message.last_contact_at
    link["expected_next_contact_window"] = (
        message.expected_next_contact_window.model_dump(mode="python")
        if message.expected_next_contact_window
        else None
    )
    apply_link_status(message.vehicle_id, utc_now())


async def route_message(message: Any) -> None:
    async with state_lock:
        if isinstance(message, HeartbeatMessage):
            await _handle_heartbeat(message)
        elif isinstance(message, TelemetryMessage):
            await _handle_telemetry(message)
        elif isinstance(message, VehicleEventMessage):
            await _handle_event(message)
        elif isinstance(message, LinkStateMessage):
            await _handle_link_state(message)


@router.websocket("/dss/ws/vehicles")
async def vehicles_websocket(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            try:
                payload = await websocket.receive_json()
                if not isinstance(payload, dict):
                    await websocket.send_json({"ok": False, "error": "Message must be a JSON object"})
                    continue

                message = validate_message(payload)
                domain_error = validate_vehicle_and_domain(message.vehicle_id, message.domain)
                if domain_error:
                    await websocket.send_json({"ok": False, "error": domain_error})
                    continue

                await route_message(message)
                await websocket.send_json(
                    {
                        "ok": True,
                        "received_message_type": message.message_type,
                        "vehicle_id": message.vehicle_id,
                    }
                )
            except ValidationError as exc:
                await websocket.send_json(
                    {
                        "ok": False,
                        "error": "Validation failed",
                        "details": jsonable_encoder(exc.errors()),
                    }
                )
            except ValueError as exc:
                await websocket.send_json({"ok": False, "error": str(exc)})
    except WebSocketDisconnect:
        return
