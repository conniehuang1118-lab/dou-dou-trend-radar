from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from urllib.parse import quote_plus

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import get_settings
from app.db import repository
from app.pipeline.engine import build_daily_snapshot, run_pipeline, serialize_event
from app.pipeline.services.text_ops import jaccard

router = APIRouter()


class TogglePayload(BaseModel):
    enabled: bool


class ModePayload(BaseModel):
    mode: str


def _filter_visible_sources(rows: list[dict]) -> list[dict]:
    # Share view only exposes non-mock sources.
    return [r for r in rows if not bool(r.get("is_mock"))]


def _visible_source_ids() -> set[str]:
    return {r["id"] for r in _filter_visible_sources(repository.list_sources())}


def _fallback_items(source_id: str, source_name: str, mode: str, start_rank: int, count: int) -> list[dict]:
    now = datetime.now(timezone.utc)
    items: list[dict] = []
    for i in range(count):
        rank = start_rank + i + 1
        items.append(
            {
                "id": f"mock-{source_id}-{mode}-{rank}",
                "title": f"{source_name} {mode.upper()} 热点 {rank}",
                "summary": f"{source_name} 渠道回退示例内容（{mode}）",
                "url": f"https://www.baidu.com/s?wd={quote_plus(source_name + ' 热点')}",
                "publish_time": now.isoformat(),
                "mode": mode,
            }
        )
    return items


def _build_section_payload(source: dict) -> dict:
    source_id = source["id"]
    source_name = source["name"]
    mode = "hot"
    is_mock = bool(source.get("is_mock"))
    allow_mock_backfill = get_settings().allow_mock_backfill
    items = repository.list_source_items(source_id, "hot", limit_each=10)
    hot_items = [x for x in items if x.get("mode") != "new"]

    if is_mock and allow_mock_backfill and len(hot_items) < 10:
        hot_items.extend(_fallback_items(source_id, source_name, "hot", len(hot_items), 10 - len(hot_items)))
    items = hot_items[:10]

    return {
        "source_id": source_id,
        "source_name": source_name,
        "mode": mode,
        "items": items,
        "availability_status": source.get("availability_status") or "unknown",
        "availability_message": source.get("availability_message") or "",
        "availability_checked_at": source["availability_checked_at"].isoformat() if source.get("availability_checked_at") else None,
        "availability_fetched_count": int(source.get("availability_fetched_count") or 0),
    }


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "now": datetime.now(timezone.utc).isoformat()}


@router.get("/sources")
def get_sources() -> dict:
    rows = _filter_visible_sources(repository.list_sources())
    return {
        "items": [
            {
                "id": r["id"],
                "name": r["name"],
                "provider_type": r["provider_type"],
                "enabled": bool(r["enabled"]),
                "mode": r["mode"],
                "weight": int(r["weight"]),
                "last_fetch": r["last_fetch"].isoformat() if r.get("last_fetch") else None,
                "is_mock": bool(r["is_mock"]),
                "availability_status": r.get("availability_status") or "unknown",
                "availability_message": r.get("availability_message") or "",
                "availability_checked_at": r["availability_checked_at"].isoformat() if r.get("availability_checked_at") else None,
                "availability_fetched_count": int(r.get("availability_fetched_count") or 0),
            }
            for r in rows
        ]
    }


@router.post("/sources/{source_id}/toggle")
def toggle_source(source_id: str, payload: TogglePayload) -> dict:
    row = repository.update_source_toggle(source_id, payload.enabled)
    if not row:
        raise HTTPException(status_code=404, detail="source not found")
    return {
        "id": row["id"],
        "enabled": bool(row["enabled"]),
        "mode": row["mode"],
        "weight": int(row["weight"]),
        "last_fetch": row["last_fetch"].isoformat() if row.get("last_fetch") else None,
    }


@router.post("/sources/{source_id}/mode")
def set_mode(source_id: str, payload: ModePayload) -> dict:
    if payload.mode != "hot":
        raise HTTPException(status_code=400, detail="mode must be hot")
    row = repository.update_source_mode(source_id, "hot")
    if not row:
        raise HTTPException(status_code=404, detail="source not found")
    return {
        "id": row["id"],
        "enabled": bool(row["enabled"]),
        "mode": row["mode"],
        "weight": int(row["weight"]),
        "last_fetch": row["last_fetch"].isoformat() if row.get("last_fetch") else None,
    }


@router.post("/refresh")
def refresh() -> dict:
    result = run_pipeline()
    return {"message": "refresh completed", **result}


@router.get("/home")
def home() -> dict:
    visible_ids = _visible_source_ids()
    sources = [x for x in _filter_visible_sources(repository.list_sources()) if x["enabled"]]
    all_events = [serialize_event(x) for x in repository.list_events(limit=200)]
    events: list[dict] = []
    for event in all_events:
        sig_sources = {s["source_id"] for s in repository.get_event_signals(event["id"])}
        if sig_sources and sig_sources.isdisjoint(visible_ids):
            continue
        events.append(event)

    sections = [_build_section_payload(s) for s in sources]

    return {
        "sections": sections,
        "breaking": [e for e in events if e["is_breaking"]][:3],
        "top_events": events[:10],
    }


@router.get("/platform/{source_id}")
def platform_feed(source_id: str) -> dict:
    source = repository.get_source(source_id)
    if not source or bool(source.get("is_mock")):
        raise HTTPException(status_code=404, detail="source not found")
    section = _build_section_payload(source)
    return {
        "source_id": source["id"],
        "source_name": source["name"],
        "enabled": bool(source["enabled"]),
        "mode": "hot",
        "last_fetch": source["last_fetch"].isoformat() if source.get("last_fetch") else None,
        "availability_status": source.get("availability_status") or "unknown",
        "availability_message": source.get("availability_message") or "",
        "availability_checked_at": source["availability_checked_at"].isoformat() if source.get("availability_checked_at") else None,
        "availability_fetched_count": int(source.get("availability_fetched_count") or 0),
        "items": section["items"],
    }


@router.get("/sources/contribution")
def source_contribution() -> dict:
    rows = _filter_visible_sources(repository.source_contribution_today())
    return {
        "items": [
            {
                "source_id": r["id"],
                "source_name": r["name"],
                "enabled": bool(r["enabled"]),
                "mode": r["mode"],
                "weight": int(r["weight"]),
                "today_signals": int(r["today_signals"]),
                "covered_events": int(r["covered_events"]),
                "last_fetch": r["last_fetch"].isoformat() if r.get("last_fetch") else None,
                "availability_status": r.get("availability_status") or "unknown",
                "availability_message": r.get("availability_message") or "",
                "availability_checked_at": r["availability_checked_at"].isoformat() if r.get("availability_checked_at") else None,
                "availability_fetched_count": int(r.get("availability_fetched_count") or 0),
            }
            for r in rows
        ]
    }


# optional detail endpoint for debugging/demo
@router.get("/events/{event_id}")
def event_detail(event_id: str) -> dict:
    row = repository.get_event(event_id)
    if not row:
        raise HTTPException(status_code=404, detail="event not found")

    event = serialize_event(row)
    visible_ids = _visible_source_ids()
    signals = [s for s in repository.get_event_signals(event_id) if s["source_id"] in visible_ids]

    grouped: dict[str, list[dict]] = defaultdict(list)
    for s in signals:
        grouped[s["source_id"]].append(
            {
                "id": s["id"],
                "source_id": s["source_id"],
                "source_name": s["source_name"],
                "title": s["title"],
                "url": s["url"],
                "publish_time": s["publish_time"].isoformat(),
            }
        )

    related = []
    target_kw = set(event["top_keywords"])
    for r in repository.list_events(limit=100):
        if r["id"] == event_id:
            continue
        item = serialize_event(r)
        item_sources = {s["source_id"] for s in repository.get_event_signals(item["id"])}
        if item_sources and item_sources.isdisjoint(visible_ids):
            continue
        if jaccard(target_kw, set(item["top_keywords"])) > 0:
            related.append(item)
    related = related[:5]

    return {"event": event, "signals_by_source": grouped, "related_events": related}


@router.post("/digest/generate")
def digest_generate() -> dict:
    payload = build_daily_snapshot()
    return {"message": "daily snapshot generated", "payload": payload}
