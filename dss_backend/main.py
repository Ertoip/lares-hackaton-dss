import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from dss_backend.link_status import link_status_background_task
from dss_backend.routers import router as rest_router
from dss_backend.websocket import router as websocket_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    task = asyncio.create_task(link_status_background_task())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="Maritime Multi-Domain DSS Backend",
    description="DSS socket input layer for external unmanned vehicle messages.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(rest_router)
app.include_router(websocket_router)
