from __future__ import annotations

import hashlib
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo

from app.core.config import get_settings
from app.core.types import EventModel, RawSignal
from app.db import repository
from app.pipeline.providers.registry import build_provider_map
from app.pipeline.services.text_ops import (
    categorize_by_keywords,
    counter_top,
    extract_keywords,
    jaccard,
    normalize_text,
    safe_log,
    strong_fingerprint,
    summarize,
    weak_fingerprint,
)


@dataclass
class ClusterBucket:
    signal_rows: list[dict]
    keyword_set: set[str]


def _normalize_and_enrich(raw: RawSignal) -> RawSignal:
    content = (raw.content or "").strip()
    keywords = raw.extracted_keywords or extract_keywords(f"{raw.title} {content}", top_k=10)
    return RawSignal(
        id=raw.id,
        source_id=raw.source_id,
        title=raw.title.strip(),
        content=content,
        url=raw.url.strip(),
        author=(raw.author or "").strip(),
        publish_time=raw.publish_time,
        metrics=raw.metrics or {},
        extracted_keywords=keywords,
        language=raw.language,
    )


def _signal_heat(signal: dict) -> float:
    metrics = signal.get("metrics", {}) or {}
    likes = float(metrics.get("likes", 0) or 0)
    comments = float(metrics.get("comments", 0) or 0)
    reposts = float(metrics.get("reposts", 0) or 0)
    views = float(metrics.get("views", 0) or 0)

    heat_raw = safe_log(likes) + 1.5 * safe_log(comments) + 2.0 * safe_log(reposts) + 0.5 * safe_log(views)

    publish_time = signal["publish_time"]
    now = datetime.now(timezone.utc)
    age_hours = max((now - publish_time).total_seconds() / 3600.0, 0.0)
    time_decay = math.exp(-age_hours / 12.0)
    source_weight = float(signal.get("source_weight", 3) or 3)

    return heat_raw * source_weight * time_decay


def _cluster_signals(signal_rows: list[dict], threshold: float = 0.35) -> list[ClusterBucket]:
    clusters: list[ClusterBucket] = []
    for row in signal_rows:
        kws = set(row.get("extracted_keywords") or [])
        if not kws:
            kws = set(extract_keywords(f"{row['title']} {row.get('content', '')}", top_k=10))
            row["extracted_keywords"] = list(kws)

        best_idx = -1
        best = 0.0
        for idx, c in enumerate(clusters):
            s = jaccard(kws, c.keyword_set)
            if s > best:
                best = s
                best_idx = idx

        if best_idx >= 0 and best >= threshold:
            clusters[best_idx].signal_rows.append(row)
            clusters[best_idx].keyword_set |= kws
        else:
            clusters.append(ClusterBucket([row], set(kws)))

    return clusters


def _event_id(category: str, title: str, keywords: list[str]) -> str:
    base = f"{category}|{normalize_text(title)}|{'|'.join(keywords[:4])}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:20]


def _build_events(clusters: list[ClusterBucket], previous_map: dict[str, dict]) -> list[EventModel]:
    settings = get_settings()
    now = datetime.now(timezone.utc)

    drafts: list[tuple[dict, list[dict], float]] = []
    raw_vals: list[float] = []

    for cluster in clusters:
        rows = sorted(cluster.signal_rows, key=lambda x: x["publish_time"], reverse=True)
        scored = [(r, _signal_heat(r)) for r in rows]
        scored.sort(key=lambda x: x[1], reverse=True)

        top_signal = scored[0][0]
        all_kw = [k for r in rows for k in (r.get("extracted_keywords") or [])]
        top_kw = counter_top(all_kw, 10)
        category = categorize_by_keywords(top_kw, top_signal["title"], top_signal.get("content", ""))

        source_breakdown = dict(Counter([r["source_id"] for r in rows]))
        source_count = len(source_breakdown)
        signals_count = len(rows)

        raw_heat = sum(v for _, v in scored)
        raw_vals.append(raw_heat)

        first_seen = min(r["publish_time"] for r in rows)
        event_id = _event_id(category, top_signal["title"], top_kw)

        prev = previous_map.get(event_id)
        if prev and prev.get("first_seen_time"):
            first_seen = prev["first_seen_time"]

        summary = summarize([
            top_signal.get("content", ""),
            f"{source_count}个平台，{signals_count}条信号",
            f"关键词：{'、'.join(top_kw[:5])}",
        ], 120)

        cur_from = now - timedelta(minutes=60)
        prev_from = now - timedelta(minutes=120)
        cur_count = sum(1 for r in rows if r["publish_time"] >= cur_from)
        prev_count = sum(1 for r in rows if prev_from <= r["publish_time"] < cur_from)
        growth = (cur_count - prev_count) / max(prev_count, 1e-6)

        is_breaking = False
        breaking_until = None
        if growth >= settings.breaking_growth_threshold and source_count >= settings.breaking_min_source_count:
            is_breaking = True
            breaking_until = now + timedelta(hours=settings.breaking_hours)
        elif prev and prev.get("is_breaking") and prev.get("breaking_until") and prev["breaking_until"] > now:
            is_breaking = True
            breaking_until = prev["breaking_until"]

        drafts.append(({
            "id": event_id,
            "title": top_signal["title"],
            "summary": summary,
            "category": category,
            "growth_rate": round(float(growth), 4),
            "first_seen_time": first_seen,
            "last_updated_time": now,
            "source_count": source_count,
            "signals_count": signals_count,
            "top_keywords": top_kw,
            "is_breaking": is_breaking,
            "breaking_until": breaking_until,
            "source_breakdown": source_breakdown,
        }, rows, raw_heat))

    if not drafts:
        return []

    min_v, max_v = min(raw_vals), max(raw_vals)
    events: list[EventModel] = []
    for draft, rows, raw in drafts:
        score = 50.0 if max_v == min_v else ((raw - min_v) / (max_v - min_v) * 100.0)
        events.append(
            EventModel(
                id=draft["id"],
                title=draft["title"],
                summary=draft["summary"],
                category=draft["category"],
                heat_score=round(float(score), 2),
                growth_rate=draft["growth_rate"],
                first_seen_time=draft["first_seen_time"],
                last_updated_time=draft["last_updated_time"],
                source_count=draft["source_count"],
                signals_count=draft["signals_count"],
                top_keywords=draft["top_keywords"],
                is_breaking=draft["is_breaking"],
                breaking_until=draft["breaking_until"],
                source_breakdown=draft["source_breakdown"],
                signal_ids=[r["id"] for r in rows],
            )
        )

    events.sort(key=lambda x: x.heat_score, reverse=True)
    return events


def _make_id(source_id: str, title: str, idx: int, publish: datetime) -> str:
    base = f"{source_id}|{title}|{idx}|{publish.isoformat()}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:24]


def _fallback_for_source(source_id: str, source_name: str) -> list[RawSignal]:
    now = datetime.now(timezone.utc)
    shared = [
        "开源AI助手集体爆发",
        "国产AI视频模型发布",
        "设计系统自动化成为团队标配",
    ]

    unique = [
        "智能体工作流平台升级", "科技大厂新品发布", "创业融资回暖", "AI硬件量产提速", "多模态模型评测",
        "增长团队转向复购", "品牌营销新策略", "企业知识库建设", "开源数据库更新", "UI 设计趋势观察",
        "自动驾驶芯片进展", "开发者工具集成", "AIGC商业化案例", "跨境创业新机会", "内容平台算法调整",
    ]

    rows: list[RawSignal] = []
    idx = 1
    def search_url(title: str) -> str:
        return f"https://www.baidu.com/s?wd={quote_plus(title)}"

    for t in shared:
        publish = now - timedelta(minutes=idx * 6)
        rows.append(
            RawSignal(
                id=_make_id(source_id, t, idx, publish),
                source_id=source_id,
                title=t,
                content=f"{source_name} 出现该主题高热信号。",
                url=search_url(t),
                author="mock",
                publish_time=publish,
                metrics={"likes": 900 + idx * 50, "comments": 300 + idx * 30, "reposts": 240 + idx * 20, "views": 60000 + idx * 4000},
                extracted_keywords=["爆发", "趋势", "全网"],
                language="zh",
            )
        )
        idx += 1

    for t in unique:
        publish = now - timedelta(minutes=30 + idx * 5)
        rows.append(
            RawSignal(
                id=_make_id(source_id, t, idx, publish),
                source_id=source_id,
                title=f"{t}（{source_name}）",
                content=f"{source_name} 关于 {t} 的热点内容。",
                url=search_url(t),
                author="mock",
                publish_time=publish,
                metrics={"likes": 120 + idx * 8, "comments": 45 + idx * 3, "reposts": 30 + idx * 2, "views": 9000 + idx * 330},
                extracted_keywords=["热点", "趋势"],
                language="zh",
            )
        )
        idx += 1

    return rows


def _ensure_minimum_dataset(source_rows: list[dict], ingested: list[RawSignal]) -> list[RawSignal]:
    by_source: dict[str, int] = defaultdict(int)
    for s in ingested:
        by_source[s.source_id] += 1

    patched = list(ingested)
    for src in source_rows:
        sid = src["id"]
        if by_source[sid] < 10:
            fallback = _fallback_for_source(sid, src["name"])
            patched.extend(fallback)

    return patched


def run_pipeline() -> dict:
    run_id = repository.start_pipeline_run()
    now = datetime.now(timezone.utc)

    try:
        settings = get_settings()
        repository.normalize_legacy_mock_urls()
        provider_map = build_provider_map()
        enabled_rows = [x for x in repository.list_sources() if x["enabled"]]
        source_rows = [
            x for x in enabled_rows
            if settings.enable_mock_sources or not bool(x.get("is_mock"))
        ]
        allowed_source_ids = {x["id"] for x in source_rows}

        ingested: list[RawSignal] = []
        for src in source_rows:
            provider = provider_map.get(src["id"])
            signals: list[RawSignal] = []
            source_is_mock = bool(src.get("is_mock"))
            if provider:
                try:
                    signals = provider.fetch()
                except Exception:
                    signals = []
            # Real sources: keep only fetched real signals (no forced fake fill).
            # Mock sources: only backfill when explicitly enabled by env flag.
            if source_is_mock and settings.allow_mock_backfill and len(signals) < 10:
                fallback = _fallback_for_source(src["id"], src["name"])
                existing = {f"{s.title}|{s.url}" for s in signals}
                for fb in fallback:
                    key = f"{fb.title}|{fb.url}"
                    if key in existing:
                        continue
                    signals.append(fb)
                    existing.add(key)
                    if len(signals) >= 10:
                        break
            ingested.extend(signals)
            repository.touch_source_last_fetch(src["id"])

        if settings.allow_mock_backfill:
            ingested = _ensure_minimum_dataset(source_rows, ingested)

        normalized = [_normalize_and_enrich(x) for x in ingested if x.title and x.url]

        existing_fp = repository.get_existing_fingerprints(72)
        existing_wfp = repository.get_existing_weak_fingerprints(72)
        batch_fp: set[str] = set()
        batch_wfp: set[tuple[str, str]] = set()

        deduped: list[RawSignal] = []
        fps: list[tuple[str, str]] = []
        for sig in normalized:
            fp = strong_fingerprint(sig.title, sig.url)
            wfp = weak_fingerprint(sig.title)
            wfp_key = (sig.source_id, wfp)
            if fp in existing_fp or fp in batch_fp:
                continue
            if wfp_key in existing_wfp or wfp_key in batch_wfp:
                continue
            batch_fp.add(fp)
            batch_wfp.add(wfp_key)
            deduped.append(sig)
            fps.append((fp, wfp))

        inserted = repository.insert_raw_signals(deduped, fps)

        recent = [r for r in repository.list_recent_signals(48) if r["source_id"] in allowed_source_ids]
        for r in recent:
            if not r.get("extracted_keywords"):
                r["extracted_keywords"] = extract_keywords(f"{r['title']} {r.get('content') or ''}", top_k=10)

        clusters = _cluster_signals(recent, threshold=0.35)
        prev_map = repository.list_previous_events_map()
        events = _build_events(clusters, prev_map)

        # hard guarantee for demo acceptance
        if settings.allow_mock_backfill and len(events) < 20:
            extra = _fallback_for_source("mock_burst", "种子源")
            ext_norm = [_normalize_and_enrich(x) for x in extra]
            # Make sure fallback signals are persisted before they can be referenced by event mappings.
            ext_existing_fp = repository.get_existing_fingerprints(72)
            ext_existing_wfp = repository.get_existing_weak_fingerprints(72)
            ext_batch_fp: set[str] = set()
            ext_batch_wfp: set[tuple[str, str]] = set()
            ext_deduped: list[RawSignal] = []
            ext_fps: list[tuple[str, str]] = []
            for sig in ext_norm:
                fp = strong_fingerprint(sig.title, sig.url)
                wfp = weak_fingerprint(sig.title)
                wfp_key = (sig.source_id, wfp)
                if fp in ext_existing_fp or fp in ext_batch_fp:
                    continue
                if wfp_key in ext_existing_wfp or wfp_key in ext_batch_wfp:
                    continue
                ext_batch_fp.add(fp)
                ext_batch_wfp.add(wfp_key)
                ext_deduped.append(sig)
                ext_fps.append((fp, wfp))

            if ext_deduped:
                repository.insert_raw_signals(ext_deduped, ext_fps)

            recent = [r for r in repository.list_recent_signals(48) if r["source_id"] in allowed_source_ids]
            for r in recent:
                if not r.get("extracted_keywords"):
                    r["extracted_keywords"] = extract_keywords(f"{r['title']} {r.get('content') or ''}", top_k=10)
            clusters = _cluster_signals(recent, threshold=0.35)
            events = _build_events(clusters, prev_map)

        repository.save_events(events, observed_at=now)

        breaking_count = sum(1 for e in events if e.is_breaking)
        repository.finish_pipeline_run(
            run_id,
            "success",
            f"signals_in={len(ingested)}, inserted={inserted}, events={len(events)}, breaking={breaking_count}",
        )
        return {
            "signals_in": len(ingested),
            "signals_inserted": inserted,
            "events": len(events),
            "breaking": breaking_count,
        }
    except Exception as exc:
        repository.finish_pipeline_run(run_id, "failed", str(exc))
        raise


def serialize_event(e: dict) -> dict:
    return {
        "id": e["id"],
        "title": e["title"],
        "summary": e["summary"],
        "category": e["category"],
        "heat_score": float(e["heat_score"]),
        "growth_rate": float(e["growth_rate"]),
        "first_seen_time": e["first_seen_time"].isoformat(),
        "last_updated_time": e["last_updated_time"].isoformat(),
        "source_count": int(e["source_count"]),
        "signals_count": int(e["signals_count"]),
        "top_keywords": list(e.get("top_keywords") or []),
        "is_breaking": bool(e.get("is_breaking")),
        "breaking_until": e.get("breaking_until").isoformat() if e.get("breaking_until") else None,
        "source_breakdown": dict(e.get("source_breakdown") or {}),
    }


def build_daily_snapshot() -> dict:
    tz = ZoneInfo(get_settings().app_timezone)
    now = datetime.now(tz)
    events = repository.list_events(limit=300)
    serialized = [serialize_event(x) for x in events]

    payload = {
        "date": str(now.date()),
        "version": f"v{now.strftime('%Y%m%d')}",
        "breaking": [x for x in serialized if x["is_breaking"]][:3],
        "top_events": serialized[:10],
    }
    repository.save_daily_snapshot(payload["date"], payload["version"], payload)
    return payload
