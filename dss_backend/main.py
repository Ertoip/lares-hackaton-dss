import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from dss_backend.core.llm_report_builder import initialize_report_builder
from dss_backend.core.processing_pipeline import run_processing_pipeline
from dss_backend.link_status import LINK_RECALCULATION_SECONDS, recalculate_all_link_statuses
from dss_backend.routers import router as rest_router
from dss_backend.sim_bridge import poll_simulation
from dss_backend.state import state_lock
from dss_backend.websocket import router as websocket_router


logging.basicConfig(level=logging.WARNING)
logging.getLogger("dss_backend").setLevel(logging.INFO)
logger = logging.getLogger(__name__)


async def dss_background_task() -> None:
    while True:
        await recalculate_all_link_statuses()
        async with state_lock:
            run_processing_pipeline()
        await asyncio.sleep(LINK_RECALCULATION_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    report_builder = initialize_report_builder()
    logger.info("DSS LLM enabled: %s", report_builder.enabled)
    task     = asyncio.create_task(dss_background_task())
    sim_task = asyncio.create_task(poll_simulation())
    try:
        yield
    finally:
        task.cancel()
        sim_task.cancel()
        for t in (task, sim_task):
            try:
                await t
            except asyncio.CancelledError:
                pass


app = FastAPI(
    title="Maritime Multi-Domain DSS Backend",
    description="DSS socket input layer for external unmanned vehicle messages.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(rest_router)
app.include_router(websocket_router)
