import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager

from app.core.db import init_db
from app.api.routes import router

init_db()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB schema & baseline seed memory on startup
    init_db()
    yield

app = FastAPI(
    title="Cadence – Meeting-to-Execution Agent Server",
    description="Enterprise server with speaker-attributed transcript ingestion, cross-meeting memory, conflict detection, tracker sync, reminders, digests, and mandatory confirmation gate.",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

# Mount static files and SPA root
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/", include_in_schema=False)
def serve_index():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "Cadence API Server is online. Visit /docs for Swagger interactive endpoints."}

@app.get("/health", tags=["System"])
def health_check():
    return {"status": "healthy", "service": "Cadence Agent", "version": "2.0.0"}
