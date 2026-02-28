from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse

from app.api.routes import router
from app.core.config import get_settings
from app.core.scheduler import start_scheduler, stop_scheduler
from app.db import repository
from app.pipeline.engine import build_daily_snapshot, run_pipeline

BASE_DIR = Path(__file__).resolve().parents[2]
MIGRATION_SQL = BASE_DIR / "migrations" / "001_init.sql"
FRONTEND_DIR = BASE_DIR / "frontend" / "public"


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    repository.run_migrations(str(MIGRATION_SQL))
    run_pipeline()
    build_daily_snapshot()
    if settings.enable_internal_scheduler:
        start_scheduler()
    yield
    if settings.enable_internal_scheduler:
        stop_scheduler()


app = FastAPI(title="中文版全网趋势雷达 MVP", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")
app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR)), name="assets")


@app.get("/")
def page_home() -> FileResponse:
    return FileResponse(str(FRONTEND_DIR / "index.html"))


@app.get("/event")
def page_event() -> FileResponse:
    return FileResponse(str(FRONTEND_DIR / "event.html"))


@app.get("/sources")
def page_sources() -> FileResponse:
    return FileResponse(str(FRONTEND_DIR / "sources.html"))


@app.get("/platform")
def page_platform_query() -> FileResponse:
    return FileResponse(str(FRONTEND_DIR / "platform.html"))


@app.get("/platform/{source_id}")
def page_platform(source_id: str) -> FileResponse:
    _ = source_id
    return FileResponse(str(FRONTEND_DIR / "platform.html"))


@app.get("/styles.css")
def page_styles() -> FileResponse:
    return FileResponse(str(FRONTEND_DIR / "styles.css"))


@app.get("/app.js")
def page_script() -> FileResponse:
    return FileResponse(str(FRONTEND_DIR / "app.js"))
