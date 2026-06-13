from copy import deepcopy

from fastapi import APIRouter, HTTPException

from dss_backend.state import ALLOWED_VEHICLES, events, serializable_snapshot, state_lock, vehicles


router = APIRouter(prefix="/dss")


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
