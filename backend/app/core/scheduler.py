from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import get_settings
from app.pipeline.engine import build_daily_snapshot, run_pipeline

logger = logging.getLogger(__name__)
_scheduler: AsyncIOScheduler | None = None


def start_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler and _scheduler.running:
        return _scheduler

    settings = get_settings()
    _scheduler = AsyncIOScheduler(timezone=settings.app_timezone)
    _scheduler.add_job(run_pipeline, "interval", minutes=settings.pipeline_interval_minutes, id="pipeline_5min")
    _scheduler.add_job(build_daily_snapshot, "cron", hour=8, minute=0, id="daily_snapshot_0800")
    _scheduler.start()
    logger.info("scheduler started")
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
