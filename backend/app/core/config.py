from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "trend-radar-mvp")
    app_host: str = os.getenv("APP_HOST", "0.0.0.0")
    app_port: int = int(os.getenv("APP_PORT", "8080"))
    app_timezone: str = os.getenv("APP_TIMEZONE", "Asia/Shanghai")
    app_env: str = os.getenv("APP_ENV", "dev")

    database_url: str = os.getenv("DATABASE_URL", "postgresql://trend:trend@localhost:5432/trend_radar")

    pipeline_interval_minutes: int = int(os.getenv("PIPELINE_INTERVAL_MINUTES", "5"))
    breaking_growth_threshold: float = float(os.getenv("BREAKING_GROWTH_THRESHOLD", "0.40"))
    breaking_min_source_count: int = int(os.getenv("BREAKING_MIN_SOURCE_COUNT", "3"))
    breaking_hours: int = int(os.getenv("BREAKING_HOURS", "6"))
    enable_internal_scheduler: bool = _as_bool(os.getenv("ENABLE_INTERNAL_SCHEDULER"), True)

    zhihu_hot_rss: str = os.getenv("ZHIHU_HOT_RSS", "https://rsshub.app/zhihu/hotlist")
    x_trend_rss: str = os.getenv("X_TREND_RSS", "https://rsshub.app/x/trending")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
