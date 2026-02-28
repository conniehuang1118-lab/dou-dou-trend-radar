from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import feedparser
import requests
from bs4 import BeautifulSoup

from app.core.config import get_settings
from app.core.types import RawSignal
from app.pipeline.providers.base import Provider


def _parse_dt(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        return parsedate_to_datetime(value).astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


class ZhihuHotProvider(Provider):
    source_id = "zhihu_hot"
    name = "知乎热榜"
    provider_type = "hotlist"
    is_mock = False

    def fetch(self) -> list[RawSignal]:
        settings = get_settings()
        items: list[RawSignal] = []
        feed = feedparser.parse(settings.zhihu_hot_rss)
        rank = 0
        for entry in feed.entries[:50]:
            title = (getattr(entry, "title", "") or "").strip()
            url = (getattr(entry, "link", "") or "").strip()
            if not title or not url:
                continue
            rank += 1
            content = (getattr(entry, "summary", "") or "")[:800]
            publish_time = _parse_dt(getattr(entry, "published", None) or getattr(entry, "updated", None))
            items.append(
                RawSignal(
                    id=self.make_signal_id(title, url, publish_time),
                    source_id=self.source_id,
                    title=title,
                    content=content,
                    url=url,
                    author="",
                    publish_time=publish_time,
                    metrics={"views": float((51 - rank) * 600), "comments": float((51 - rank) * 18)},
                    extracted_keywords=["知乎热榜", "热点"],
                    language="zh",
                )
            )
        return items


class WeiboHotProvider(Provider):
    source_id = "weibo_hot"
    name = "微博热榜"
    provider_type = "hotlist"
    is_mock = False

    def fetch(self) -> list[RawSignal]:
        headers = {"User-Agent": "Mozilla/5.0"}
        items: list[RawSignal] = []

        # first try JSON endpoint
        try:
            resp = requests.get("https://weibo.com/ajax/side/hotSearch", headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json().get("data", {}).get("realtime", [])
            rank = 0
            for row in data[:50]:
                title = (row.get("note") or row.get("word") or "").strip()
                if not title:
                    continue
                rank += 1
                hot_num = float(row.get("num") or 0)
                url = f"https://s.weibo.com/weibo?q={quote('#' + title + '#')}"
                now = datetime.now(timezone.utc)
                items.append(
                    RawSignal(
                        id=self.make_signal_id(title, url, now),
                        source_id=self.source_id,
                        title=title,
                        content=f"微博热搜第{rank}位，热度值{int(hot_num)}",
                        url=url,
                        author="",
                        publish_time=now,
                        metrics={"views": hot_num, "reposts": hot_num / 50.0, "comments": hot_num / 80.0},
                        extracted_keywords=["微博", "热搜"],
                        language="zh",
                    )
                )
            if items:
                return items
        except Exception:
            pass

        # fallback HTML parse
        try:
            resp = requests.get("https://s.weibo.com/top/summary?cate=realtimehot", headers=headers, timeout=10)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            rows = soup.select("table tbody tr")
            rank = 0
            for row in rows:
                link = row.select_one("td.td-02 a")
                if not link:
                    continue
                title = link.get_text(" ", strip=True)
                href = link.get("href", "")
                if not title or not href:
                    continue
                rank += 1
                if href.startswith("/"):
                    href = f"https://s.weibo.com{href}"
                hot_node = row.select_one("td.td-02 span")
                num = 0.0
                if hot_node:
                    digits = "".join(ch for ch in hot_node.get_text(strip=True) if ch.isdigit())
                    num = float(digits or 0)
                now = datetime.now(timezone.utc)
                items.append(
                    RawSignal(
                        id=self.make_signal_id(title, href, now),
                        source_id=self.source_id,
                        title=title,
                        content=f"微博热搜第{rank}位",
                        url=href,
                        author="",
                        publish_time=now,
                        metrics={"views": num, "reposts": num / 50.0, "comments": num / 80.0},
                        extracted_keywords=["微博", "热搜"],
                        language="zh",
                    )
                )
                if rank >= 50:
                    break
        except Exception:
            return []

        return items


class XTrendingProvider(Provider):
    source_id = "x_trending"
    name = "X Trending"
    provider_type = "hotlist"
    is_mock = False

    def fetch(self) -> list[RawSignal]:
        settings = get_settings()
        items: list[RawSignal] = []
        feed = feedparser.parse(settings.x_trend_rss)

        rank = 0
        for entry in feed.entries[:50]:
            title = (getattr(entry, "title", "") or "").strip()
            url = (getattr(entry, "link", "") or "").strip()
            if not title or not url:
                continue
            rank += 1
            summary = (getattr(entry, "summary", "") or "")[:700]
            publish_time = _parse_dt(getattr(entry, "published", None) or getattr(entry, "updated", None))
            items.append(
                RawSignal(
                    id=self.make_signal_id(title, url, publish_time),
                    source_id=self.source_id,
                    title=title,
                    content=summary,
                    url=url,
                    author="",
                    publish_time=publish_time,
                    metrics={"views": float((51 - rank) * 500), "reposts": float((51 - rank) * 9)},
                    extracted_keywords=["X", "Trending"],
                    language="zh",
                )
            )
        return items
