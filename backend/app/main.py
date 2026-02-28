from __future__ import annotations

import base64
import hmac
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse, JSONResponse, Response

from app.api.routes import router
from app.core.config import get_settings
from app.core.scheduler import start_scheduler, stop_scheduler
from app.db import repository
from app.pipeline.engine import build_daily_snapshot, run_pipeline

BACKEND_DIR = Path(__file__).resolve().parents[1]
MIGRATION_CANDIDATES = [
    BACKEND_DIR / "migrations" / "001_init.sql",  # local/render
    BACKEND_DIR.parent / "migrations" / "001_init.sql",  # docker
]
MIGRATION_SQL = next((p for p in MIGRATION_CANDIDATES if p.exists()), MIGRATION_CANDIDATES[0])

FRONTEND_CANDIDATES = [
    BACKEND_DIR.parent / "frontend" / "public",  # local/render
    BACKEND_DIR / "frontend" / "public",  # optional fallback
]
FRONTEND_DIR = next((p for p in FRONTEND_CANDIDATES if p.exists()), FRONTEND_CANDIDATES[0])


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


def _unauthorized() -> Response:
    return Response(
        content="Unauthorized",
        status_code=401,
        headers={"WWW-Authenticate": 'Basic realm="Trend Radar"'},
    )


@app.middleware("http")
async def share_basic_auth(request: Request, call_next):
    settings = get_settings()
    if not settings.share_auth_enabled:
        return await call_next(request)

    path = request.url.path
    if path == "/api/health":
        return await call_next(request)

    auth = request.headers.get("authorization", "")
    if not auth.startswith("Basic "):
        return _unauthorized()

    try:
        encoded = auth.split(" ", 1)[1].strip()
        decoded = base64.b64decode(encoded).decode("utf-8")
        username, password = decoded.split(":", 1)
    except Exception:
        return _unauthorized()

    user_ok = hmac.compare_digest(username, settings.share_auth_username)
    pass_ok = hmac.compare_digest(password, settings.share_auth_password)
    if not (user_ok and pass_ok):
        return _unauthorized()

    return await call_next(request)


app.include_router(router, prefix="/api")
if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR)), name="assets")


@app.get("/")
def page_home() -> FileResponse:
    if not FRONTEND_DIR.exists():
        return JSONResponse({"message": "frontend not found on this runtime", "api": "/api/health"})
    return FileResponse(str(FRONTEND_DIR / "index.html"))


@app.get("/event")
def page_event() -> FileResponse:
    if not FRONTEND_DIR.exists():
        return JSONResponse({"message": "frontend not found on this runtime", "api": "/api/health"})
    return FileResponse(str(FRONTEND_DIR / "event.html"))


@app.get("/sources")
def page_sources() -> FileResponse:
    if not FRONTEND_DIR.exists():
        return JSONResponse({"message": "frontend not found on this runtime", "api": "/api/health"})
    return FileResponse(str(FRONTEND_DIR / "sources.html"))


@app.get("/platform")
def page_platform_query() -> FileResponse:
    if not FRONTEND_DIR.exists():
        return JSONResponse({"message": "frontend not found on this runtime", "api": "/api/health"})
    return FileResponse(str(FRONTEND_DIR / "platform.html"))


@app.get("/platform/{source_id}")
def page_platform(source_id: str) -> FileResponse:
    _ = source_id
    if not FRONTEND_DIR.exists():
        return JSONResponse({"message": "frontend not found on this runtime", "api": "/api/health"})
    return FileResponse(str(FRONTEND_DIR / "platform.html"))


@app.get("/styles.css")
def page_styles() -> FileResponse:
    if not FRONTEND_DIR.exists():
        return JSONResponse({"message": "frontend not found on this runtime", "api": "/api/health"})
    return FileResponse(str(FRONTEND_DIR / "styles.css"))


@app.get("/app.js")
def page_script() -> FileResponse:
    if not FRONTEND_DIR.exists():
        return JSONResponse({"message": "frontend not found on this runtime", "api": "/api/health"})
    return FileResponse(str(FRONTEND_DIR / "app.js"))
