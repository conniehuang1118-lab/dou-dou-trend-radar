from __future__ import annotations

from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from app.core.types import RawSignal
from app.pipeline.providers.base import Provider


class GitHubTrendingProvider(Provider):
    source_id = "github_trending"
    name = "GitHub Trending"
    provider_type = "tech_signal"
    is_mock = False

    def fetch(self) -> list[RawSignal]:
        headers = {"User-Agent": "Mozilla/5.0"}
        try:
            resp = requests.get("https://github.com/trending", headers=headers, timeout=12)
            resp.raise_for_status()
        except Exception:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.select("article.Box-row")[:35]
        items: list[RawSignal] = []

        rank = 0
        for card in cards:
            a = card.select_one("h2 a")
            if not a:
                continue
            rank += 1
            path = (a.get("href", "") or "").strip("/")
            if not path:
                continue
            url = f"https://github.com/{path}"
            title = path
            desc = card.select_one("p")
            content = desc.get_text(" ", strip=True) if desc else ""
            star_nodes = card.select("a.Link--muted")
            star_today = 0.0
            if star_nodes:
                raw = star_nodes[-1].get_text(" ", strip=True)
                star_today = float("".join(ch for ch in raw if ch.isdigit()) or 0)

            now = datetime.now(timezone.utc)
            items.append(
                RawSignal(
                    id=self.make_signal_id(title, url, now),
                    source_id=self.source_id,
                    title=title,
                    content=content,
                    url=url,
                    author="",
                    publish_time=now,
                    metrics={"likes": star_today, "views": max(100.0, star_today * 30)},
                    extracted_keywords=["GitHub", "开源"],
                    language="zh",
                )
            )
        return items


class HuggingFaceTrendingProvider(Provider):
    source_id = "huggingface_trending"
    name = "HuggingFace Trending"
    provider_type = "tech_signal"
    is_mock = False

    def fetch(self) -> list[RawSignal]:
        headers = {"User-Agent": "Mozilla/5.0"}
        try:
            resp = requests.get("https://huggingface.co/models?sort=trending", headers=headers, timeout=12)
            resp.raise_for_status()
        except Exception:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        links = soup.select("a[href^='/'][class*='group']")

        items: list[RawSignal] = []
        rank = 0
        seen: set[str] = set()

        for link in links:
            href = link.get("href", "").strip()
            if not href or href.count("/") != 1:
                continue
            if href in seen:
                continue
            seen.add(href)

            title = href.strip("/")
            rank += 1
            if rank > 35:
                break

            url = f"https://huggingface.co{href}"
            content = link.get_text(" ", strip=True)
            now = datetime.now(timezone.utc)
            score = float((36 - rank) * 40)

            items.append(
                RawSignal(
                    id=self.make_signal_id(title, url, now),
                    source_id=self.source_id,
                    title=f"{title} trending on HuggingFace",
                    content=content,
                    url=url,
                    author="",
                    publish_time=now,
                    metrics={"likes": score / 5.0, "views": score * 10},
                    extracted_keywords=["HuggingFace", "模型", "AI"],
                    language="zh",
                )
            )

        return items
