import logging
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.database import Base, engine
from backend.services.scheduler_service import SchedulerService
from backend.routers import meetings, decisions, conflicts, outbox, tasks, people, analytics, integrations

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("ActionLoop")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    Base.metadata.create_all(bind=engine)
    logger.info("ActionLoop database initialized.")
    SchedulerService.start()
    logger.info("APScheduler background engine started.")
    yield
    # Shutdown
    SchedulerService.shutdown()
    logger.info("Scheduler shut down.")


app = FastAPI(
    title="ActionLoop — Meeting-to-Execution Agent",
    description=(
        "Turns meeting transcripts into tracked, human-confirmed execution. "
        "Cross-meeting memory + conflict detection + confirmation airlock."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register all routers
app.include_router(meetings.router)
app.include_router(decisions.router)
app.include_router(conflicts.router)
app.include_router(outbox.router)
app.include_router(tasks.router)
app.include_router(people.router)
app.include_router(analytics.router)
app.include_router(integrations.router)


@app.get("/", tags=["health"])
def root():
    return {
        "app": "ActionLoop",
        "status": "running",
        "docs": "/docs",
        "redoc": "/redoc",
    }


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok", "version": "1.0.0"}
