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
    mode = source["mode"]
    is_mock = bool(source.get("is_mock"))
    allow_mock_backfill = get_settings().allow_mock_backfill
    items = repository.list_source_items(source_id, mode, limit_each=10)

    hot_items = [x for x in items if x.get("mode") == "hot"]
    new_items = [x for x in items if x.get("mode") == "new"]

    if is_mock and allow_mock_backfill and mode == "hot" and len(hot_items) < 10:
        hot_items.extend(_fallback_items(source_id, source_name, "hot", len(hot_items), 10 - len(hot_items)))
        items = hot_items[:10]
    elif is_mock and allow_mock_backfill and mode == "new" and len(new_items) < 10:
        new_items.extend(_fallback_items(source_id, source_name, "new", len(new_items), 10 - len(new_items)))
        items = new_items[:10]
    elif mode == "both":
        if not (is_mock and allow_mock_backfill):
            items = hot_items + new_items
        else:
            if len(hot_items) < 10:
                hot_items.extend(_fallback_items(source_id, source_name, "hot", len(hot_items), 10 - len(hot_items)))
            if len(new_items) < 10:
                new_items.extend(_fallback_items(source_id, source_name, "new", len(new_items), 10 - len(new_items)))
            items = hot_items[:10] + new_items[:10]

    return {
        "source_id": source_id,
        "source_name": source_name,
        "mode": mode,
        "items": items,
    }


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "now": datetime.now(timezone.utc).isoformat()}


@router.get("/sources")
def get_sources() -> dict:
    rows = repository.list_sources()
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
    if payload.mode not in {"hot", "new", "both"}:
        raise HTTPException(status_code=400, detail="mode must be hot/new/both")
    row = repository.update_source_mode(source_id, payload.mode)
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
    events = [serialize_event(x) for x in repository.list_events(limit=200)]
    sources = [x for x in repository.list_sources() if x["enabled"]]

    sections = [_build_section_payload(s) for s in sources]

    return {
        "sections": sections,
        "breaking": [e for e in events if e["is_breaking"]][:3],
        "top_events": events[:5],
    }


@router.get("/platform/{source_id}")
def platform_feed(source_id: str) -> dict:
    source = repository.get_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="source not found")
    section = _build_section_payload(source)
    return {
        "source_id": source["id"],
        "source_name": source["name"],
        "enabled": bool(source["enabled"]),
        "mode": source["mode"],
        "last_fetch": source["last_fetch"].isoformat() if source.get("last_fetch") else None,
        "items": section["items"],
    }


@router.get("/sources/contribution")
def source_contribution() -> dict:
    rows = repository.source_contribution_today()
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
    signals = repository.get_event_signals(event_id)

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
        if jaccard(target_kw, set(item["top_keywords"])) > 0:
            related.append(item)
    related = related[:5]

    return {"event": event, "signals_by_source": grouped, "related_events": related}


@router.post("/digest/generate")
def digest_generate() -> dict:
    payload = build_daily_snapshot()
    return {"message": "daily snapshot generated", "payload": payload}
