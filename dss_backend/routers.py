import asyncio
import json
import logging
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from dss_backend.sim_bridge import SIM_BASE_URL

logger = logging.getLogger(__name__)

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


@router.post("/chat/stream")
async def stream_chat_message(request: ChatSendRequest) -> StreamingResponse:
    created_at = utc_now()
    stamp = created_at.strftime("%Y%m%dT%H%M%S%f")
    user_msg: dict[str, Any] = {
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
        chat_messages[user_msg["message_id"]] = user_msg
        context = _chat_context_snapshot()

    builder = get_report_builder()

    async def generate():
        full_text = ""
        try:
            async for chunk in builder.stream_chat_response(request.message, context):
                full_text += chunk
                yield f"data: {json.dumps({'text': chunk})}\n\n"
        except Exception as exc:
            logger.warning("DSS LLM stream error: %s", exc)
            full_text = "The DSS LLM could not process this request."
            yield f"data: {json.dumps({'text': full_text})}\n\n"

        answered_at = utc_now()
        assistant_msg: dict[str, Any] = {
            "message_id": f"chat_llm_{answered_at.strftime('%Y%m%dT%H%M%S%f')}",
            "timestamp": answered_at,
            "sender": "dss",
            "message_type": "llm_chat",
            "severity": "none",
            "title": "DSS",
            "body": full_text,
            "linked_event_ids": [],
            "linked_report_id": None,
            "map_focus": {"type": "none", "ids": []},
            "details": {},
            "acknowledged": True,
        }
        async with state_lock:
            chat_messages[assistant_msg["message_id"]] = assistant_msg

        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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


@router.get("/terrain")
async def check_terrain(lat: float, lon: float) -> dict[str, object]:
    try:
        from global_land_mask import globe  # noqa: PLC0415
        is_land = bool(globe.is_land(lat, lon))
    except Exception:
        is_land = False  # permissive fallback if package not installed
    return {"is_land": is_land, "lat": lat, "lon": lon}


def _astar(
    start_lat: float, start_lon: float,
    end_lat: float, end_lon: float,
    padding: float,
    max_cells: int,
    min_res: float,
) -> list[dict[str, float]] | None:
    """A* over a precomputed land grid. Returns smoothed path or None if unreachable."""
    import heapq
    import math
    import numpy as np
    from global_land_mask import globe  # noqa: PLC0415

    min_lat = min(start_lat, end_lat) - padding
    max_lat = max(start_lat, end_lat) + padding
    min_lon = min(start_lon, end_lon) - padding
    max_lon = max(start_lon, end_lon) + padding

    bbox       = max(max_lat - min_lat, max_lon - min_lon)
    resolution = max(min_res, bbox / max_cells)

    lats  = np.arange(min_lat, max_lat + resolution * 0.5, resolution)
    lons  = np.arange(min_lon, max_lon + resolution * 0.5, resolution)
    n_lat, n_lon = len(lats), len(lons)

    lat_g, lon_g = np.meshgrid(lats, lons, indexing="ij")
    land = globe.is_land(lat_g.ravel(), lon_g.ravel()).reshape(n_lat, n_lon)

    def to_cell(lat: float, lon: float) -> tuple[int, int]:
        r = int(round((lat - min_lat) / resolution))
        c = int(round((lon - min_lon) / resolution))
        return max(0, min(r, n_lat - 1)), max(0, min(c, n_lon - 1))

    start_cell = to_cell(start_lat, start_lon)
    end_cell   = to_cell(end_lat,   end_lon)

    DIRS  = [(-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)]
    COSTS = [math.sqrt(2), 1, math.sqrt(2), 1, 1, math.sqrt(2), 1, math.sqrt(2)]

    def h(a: tuple, b: tuple) -> float:
        return math.hypot(a[0] - b[0], a[1] - b[1])

    open_set: list = [(0.0, start_cell)]
    came_from: dict = {}
    g: dict = {start_cell: 0.0}

    while open_set:
        _, cur = heapq.heappop(open_set)
        if cur == end_cell:
            path: list[tuple[int, int]] = []
            step = end_cell
            while step in came_from:
                path.append(step)
                step = came_from[step]
            path.append(start_cell)
            path.reverse()

            # Line-of-sight smoothing (string pulling via Bresenham)
            def los(a: tuple, b: tuple) -> bool:
                r0, c0 = a; r1, c1 = b
                dr, dc = abs(r1 - r0), abs(c1 - c0)
                sr = 1 if r0 < r1 else -1
                sc = 1 if c0 < c1 else -1
                err = dr - dc
                r, c = r0, c0
                while True:
                    if (r, c) not in (start_cell, end_cell) and land[r, c]:
                        return False
                    if r == r1 and c == c1:
                        return True
                    e2 = 2 * err
                    if e2 > -dc: err -= dc; r += sr
                    if e2 <  dr: err += dr; c += sc

            smooth: list[tuple[int, int]] = [path[0]]
            i = 0
            while i < len(path) - 1:
                j = len(path) - 1
                while j > i + 1 and not los(path[i], path[j]):
                    j -= 1
                smooth.append(path[j])
                i = j

            result: list[dict[str, float]] = [{"lat": start_lat, "lon": start_lon}]
            for r, c in smooth[1:-1]:
                result.append({"lat": float(lats[r]), "lon": float(lons[c])})
            result.append({"lat": end_lat, "lon": end_lon})
            return result

        for (dr, dc), cost in zip(DIRS, COSTS):
            nr, nc = cur[0] + dr, cur[1] + dc
            if not (0 <= nr < n_lat and 0 <= nc < n_lon):
                continue
            if (nr, nc) not in (start_cell, end_cell) and land[nr, nc]:
                continue
            ng  = g[cur] + cost
            nb  = (nr, nc)
            if ng < g.get(nb, float("inf")):
                came_from[nb] = cur
                g[nb] = ng
                heapq.heappush(open_set, (ng + h(nb, end_cell), nb))

    return None  # no path found


def _compute_maritime_route(
    start_lat: float, start_lon: float,
    end_lat: float, end_lon: float,
) -> list[dict[str, float]]:
    import math

    fallback = [
        {"lat": start_lat, "lon": start_lon},
        {"lat": end_lat,   "lon": end_lon},
    ]

    try:
        dist = math.hypot(end_lat - start_lat, end_lon - start_lon)

        # Pass 1 — wide coverage so maritime chokepoints (e.g. Gibraltar) are
        # always inside the search area even when far from the direct line.
        # min_res=0.04° gives ~3 cells across the Strait of Gibraltar (14 km).
        padding_1 = min(10.0, max(6.0, dist * 0.5))
        result = _astar(start_lat, start_lon, end_lat, end_lon,
                        padding=padding_1, max_cells=1000, min_res=0.04)
        if result:
            return result

        # Pass 2 — fine resolution, tight corridor along the direct line.
        # Catches narrow straits that happen to lie roughly on the direct path.
        padding_2 = max(0.5, dist * 0.1)
        result = _astar(start_lat, start_lon, end_lat, end_lon,
                        padding=padding_2, max_cells=700, min_res=0.008)
        if result:
            return result

        return fallback

    except Exception as exc:
        logger.warning("Maritime route computation failed: %s", exc)
        return fallback


@router.get("/maritime-route")
async def maritime_route(
    start_lat: float = Query(...),
    start_lon: float = Query(...),
    end_lat: float   = Query(...),
    end_lon: float   = Query(...),
) -> dict[str, object]:
    waypoints = await asyncio.to_thread(
        _compute_maritime_route, start_lat, start_lon, end_lat, end_lon
    )
    return {"waypoints": waypoints}


# ── Simulation proxy endpoints ─────────────────────────────────────────────────

class SimAssignRequest(BaseModel):
    vehicle_id: str
    task: str
    lat: float | None = None
    lon: float | None = None


# DSS vehicle_id → simulation vehicle_id
_DSS_TO_SIM: dict[str, str] = {
    "air_1":     "UAV-1",
    "air_2":     "UAV-2",
    "surface_1": "USV-1",
    "surface_2": "USV-2",
    "sub_1":     "UUV-1",
    "sub_2":     "UUV-2",
}


class SimCommandRequest(BaseModel):
    vehicle_id: str
    action: str
    params: dict[str, Any] = {}
    command_id: str | None = None


async def _sim_post(path: str, body: dict | None = None) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.post(f"{SIM_BASE_URL}{path}", json=body)
            r.raise_for_status()
            return r.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Sim unreachable: {exc}") from exc


@router.post("/sim/command")
async def sim_command(request: SimCommandRequest) -> dict[str, Any]:
    sim_id = _DSS_TO_SIM.get(request.vehicle_id)
    if sim_id is None:
        raise HTTPException(status_code=400, detail=f"Unknown vehicle_id: {request.vehicle_id}")
    payload = {
        "command_id": request.command_id or f"cmd_{utc_now().strftime('%H%M%S%f')}",
        "vehicle_id": sim_id,
        "action": request.action,
        "params": request.params,
        "issued_by": "dss",
    }
    return await _sim_post("/command", payload)


@router.post("/sim/assign")
async def sim_assign(request: SimAssignRequest) -> dict[str, Any]:
    return await _sim_post("/assign", request.model_dump(exclude_none=True))


@router.post("/sim/inject/{event_type}")
async def sim_inject(event_type: str) -> dict[str, Any]:
    return await _sim_post(f"/inject/{event_type}")


@router.post("/sim/scenario/{name}")
async def sim_scenario(name: str) -> dict[str, Any]:
    return await _sim_post(f"/scenario/{name}")


@router.post("/sim/fast_forward/{seconds}")
async def sim_fast_forward(seconds: int) -> dict[str, Any]:
    return await _sim_post(f"/fast_forward/{seconds}")


@router.post("/sim/skip_to_next_event")
async def sim_skip_to_next_event() -> dict[str, Any]:
    return await _sim_post("/skip_to_next_event")
