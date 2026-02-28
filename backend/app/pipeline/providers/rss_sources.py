from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser

from app.core.types import RawSignal
from app.pipeline.providers.base import Provider


def _parse_dt(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        return parsedate_to_datetime(value).astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


class RSSProvider(Provider):
    def __init__(self, source_id: str, name: str, feed_url: str, default_tags: list[str] | None = None):
        self.source_id = source_id
        self.name = name
        self.feed_url = feed_url
        self.provider_type = "rss"
        self.is_mock = False
        self.default_tags = default_tags or []

    def fetch(self) -> list[RawSignal]:
        items: list[RawSignal] = []
        feed = feedparser.parse(self.feed_url)
        for entry in feed.entries[:40]:
            title = (getattr(entry, "title", "") or "").strip()
            url = getattr(entry, "link", "") or ""
            if not title or not url:
                continue
            content = (getattr(entry, "summary", "") or "")[:1000]
            publish_time = _parse_dt(getattr(entry, "published", None) or getattr(entry, "updated", None))
            author = (getattr(entry, "author", "") or "").strip()

            items.append(
                RawSignal(
                    id=self.make_signal_id(title, url, publish_time),
                    source_id=self.source_id,
                    title=title,
                    content=content,
                    url=url,
                    author=author,
                    publish_time=publish_time,
                    metrics={"views": 200.0},
                    extracted_keywords=self.default_tags[:],
                    language="zh",
                )
            )
        return items
