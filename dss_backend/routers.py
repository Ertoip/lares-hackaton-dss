import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from dss_backend.core.llm_report_builder import get_report_builder
from dss_backend.state import (
    ALLOWED_VEHICLES,
    chat_messages,
    dss_events,
    events,
    map_state,
    operator_state,
    reports,
    serializable_snapshot,
    severity_state,
    state_lock,
    utc_now,
    vehicles,
)


router = APIRouter(prefix="/dss")


class ChatSendRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


def _sort_newest(items: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    def sort_value(item: dict[str, Any]) -> datetime:
        value = item.get(field)
        if isinstance(value, datetime):
            return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return datetime.min.replace(tzinfo=timezone.utc)

    return sorted(items, key=sort_value, reverse=True)


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/state")
async def get_state() -> dict[str, object]:
    async with state_lock:
        return serializable_snapshot()


@router.get("/vehicles")
async def get_vehicles() -> dict[str, object]:
    async with state_lock:
        return deepcopy(vehicles)


@router.get("/vehicles/{vehicle_id}")
async def get_vehicle(vehicle_id: str) -> dict[str, object]:
    if vehicle_id not in ALLOWED_VEHICLES:
        raise HTTPException(status_code=404, detail="Vehicle not found")

    async with state_lock:
        return deepcopy(vehicles[vehicle_id])


@router.get("/events")
async def get_events() -> dict[str, object]:
    async with state_lock:
        return deepcopy(events)


@router.get("/events/{event_id}")
async def get_event(event_id: str) -> dict[str, object]:
    async with state_lock:
        event = events.get(event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="Event not found")
        return deepcopy(event)


@router.get("/map")
async def get_map() -> dict[str, object]:
    async with state_lock:
        return deepcopy(map_state)


@router.get("/dss-events")
async def get_dss_events() -> dict[str, object]:
    async with state_lock:
        return deepcopy(dss_events)


@router.get("/severity")
async def get_severity() -> dict[str, object]:
    async with state_lock:
        return deepcopy(severity_state)


@router.get("/reports")
async def get_reports() -> list[dict[str, object]]:
    async with state_lock:
        return deepcopy(_sort_newest(list(reports.values()), "created_at"))


@router.get("/reports/{report_id}")
async def get_report(report_id: str) -> dict[str, object]:
    async with state_lock:
        report = reports.get(report_id)
        if report is None:
            raise HTTPException(status_code=404, detail="Report not found")
        return deepcopy(report)


@router.get("/chat")
async def get_chat(limit: int | None = Query(default=None, ge=1)) -> list[dict[str, object]]:
    async with state_lock:
        messages = _sort_newest(list(chat_messages.values()), "timestamp")
        if limit is not None:
            messages = messages[:limit]
        return deepcopy(messages)


def _slim_vehicle(v: dict[str, Any]) -> dict[str, Any]:
    return {k: v[k] for k in ("id", "domain", "link_status", "battery_percentage", "position", "status") if k in v}


def _slim_event(e: dict[str, Any]) -> dict[str, Any]:
    return {k: e[k] for k in ("event_id", "event_kind", "severity", "vehicle_id", "description", "position") if k in e}


def _slim_report(r: dict[str, Any]) -> dict[str, Any]:
    return {k: r[k] for k in ("report_id", "title", "summary", "urgency", "created_at") if k in r}


def _chat_context_snapshot() -> dict[str, Any]:
    raw_vehicles = operator_state.get("vehicles") or {}
    active_events = operator_state.get("active_events") or []
    raw_reports = (operator_state.get("reports") or [])[:3]
    return {
        "vehicles": [_slim_vehicle(v) for v in raw_vehicles.values()] if isinstance(raw_vehicles, dict) else [],
        "active_events": [_slim_event(e) for e in active_events],
        "severity_state": operator_state.get("severity_state", {}),
        "recent_reports": [_slim_report(r) for r in raw_reports],
    }


@router.post("/chat/send")
async def send_chat_message(request: ChatSendRequest) -> dict[str, object]:
    created_at = utc_now()
    stamp = created_at.strftime("%Y%m%dT%H%M%S%f")
    user_message = {
        "message_id": f"chat_user_{stamp}",
        "timestamp": created_at,
        "sender": "operator",
        "message_type": "operator_message",
        "severity": "none",
        "title": "Operator",
        "body": request.message,
        "linked_event_ids": [],
        "linked_report_id": None,
        "map_focus": {"type": "none", "ids": []},
        "details": {},
        "acknowledged": True,
    }

    async with state_lock:
        chat_messages[user_message["message_id"]] = user_message
        context = _chat_context_snapshot()

    builder = get_report_builder()
    response = await asyncio.to_thread(builder.build_chat_response, request.message, context)

    answered_at = utc_now()
    assistant_message = {
        "message_id": f"chat_llm_{answered_at.strftime('%Y%m%dT%H%M%S%f')}",
        "timestamp": answered_at,
        "sender": "dss",
        "message_type": "llm_chat",
        "severity": "none",
        "title": "LLM",
        "body": response.get("body"),
        "linked_event_ids": response.get("referenced_event_ids") or [],
        "linked_report_id": None,
        "map_focus": {
            "type": "mixed" if response.get("referenced_event_ids") and response.get("referenced_vehicle_ids") else "events" if response.get("referenced_event_ids") else "vehicles" if response.get("referenced_vehicle_ids") else "none",
            "ids": {
                "events": response.get("referenced_event_ids") or [],
                "vehicles": response.get("referenced_vehicle_ids") or [],
            },
        },
        "details": {
            "referenced_vehicle_ids": response.get("referenced_vehicle_ids") or [],
        },
        "acknowledged": True,
    }

    async with state_lock:
        chat_messages[assistant_message["message_id"]] = assistant_message

    return {"ok": True, "user_message": user_message, "assistant_message": assistant_message}


@router.get("/chat/{message_id}")
async def get_chat_message(message_id: str) -> dict[str, object]:
    async with state_lock:
        message = chat_messages.get(message_id)
        if message is None:
            raise HTTPException(status_code=404, detail="Chat message not found")
        return deepcopy(message)


@router.post("/chat/{message_id}/ack")
async def acknowledge_chat_message(message_id: str) -> dict[str, object]:
    async with state_lock:
        message = chat_messages.get(message_id)
        if message is None:
            raise HTTPException(status_code=404, detail="Chat message not found")
        message["acknowledged"] = True
        message["acknowledged_at"] = utc_now()
        return {"ok": True, "message_id": message_id, "acknowledged": True}


@router.get("/operator-state")
async def get_operator_state() -> dict[str, object]:
    async with state_lock:
        return deepcopy(operator_state)
