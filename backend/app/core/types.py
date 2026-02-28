from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


@dataclass
class RawSignal:
    id: str
    source_id: str
    title: str
    content: str
    url: str
    author: str
    publish_time: datetime
    metrics: dict[str, float]
    extracted_keywords: list[str] = field(default_factory=list)
    language: Literal["zh", "en"] = "zh"


@dataclass
class EventModel:
    id: str
    title: str
    summary: str
    category: str
    heat_score: float
    growth_rate: float
    first_seen_time: datetime
    last_updated_time: datetime
    source_count: int
    signals_count: int
    top_keywords: list[str]
    is_breaking: bool
    breaking_until: datetime | None
    source_breakdown: dict[str, int]
    signal_ids: list[str] = field(default_factory=list)
