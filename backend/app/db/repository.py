from __future__ import annotations

import json
import math
from datetime import datetime, timezone

from app.core.types import EventModel, RawSignal
from app.db.database import get_conn


def run_migrations(sql_path: str) -> None:
    with open(sql_path, "r", encoding="utf-8") as f:
        ddl = f.read()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(ddl)
        conn.commit()


def list_sources() -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT s.*,
                       COALESCE(sh.status, 'unknown') AS availability_status,
                       sh.message AS availability_message,
                       sh.last_checked_at AS availability_checked_at,
                       sh.last_success_at AS availability_success_at,
                       COALESCE(sh.last_fetched_count, 0) AS availability_fetched_count
                FROM sources s
                LEFT JOIN source_health sh ON sh.source_id = s.id
                ORDER BY s.is_mock ASC, s.id ASC
                """
            )
            return list(cur.fetchall())


def get_source(source_id: str) -> dict | None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT s.*,
                       COALESCE(sh.status, 'unknown') AS availability_status,
                       sh.message AS availability_message,
                       sh.last_checked_at AS availability_checked_at,
                       sh.last_success_at AS availability_success_at,
                       COALESCE(sh.last_fetched_count, 0) AS availability_fetched_count
                FROM sources s
                LEFT JOIN source_health sh ON sh.source_id = s.id
                WHERE s.id = %s
                """,
                (source_id,),
            )
            return cur.fetchone()


def update_source_toggle(source_id: str, enabled: bool) -> dict | None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE sources SET enabled=%s, updated_at=NOW() WHERE id=%s RETURNING *",
                (enabled, source_id),
            )
            row = cur.fetchone()
        conn.commit()
    return row


def update_source_mode(source_id: str, mode: str) -> dict | None:
    if mode not in {"hot", "new", "both"}:
        return None
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE sources SET mode=%s, updated_at=NOW() WHERE id=%s RETURNING *",
                (mode, source_id),
            )
            row = cur.fetchone()
        conn.commit()
    return row


def touch_source_last_fetch(source_id: str) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE sources SET last_fetch=NOW(), updated_at=NOW() WHERE id=%s", (source_id,))
        conn.commit()


def upsert_source_health(
    source_id: str,
    status: str,
    message: str,
    fetched_count: int,
    checked_at: datetime,
) -> None:
    if status not in {"ok", "unavailable", "unknown"}:
        status = "unknown"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO source_health(
                    source_id, status, message, last_checked_at, last_success_at, last_fetched_count, updated_at
                )
                VALUES(
                    %s, %s, %s, %s,
                    CASE WHEN %s = 'ok' THEN %s ELSE NULL END,
                    %s, NOW()
                )
                ON CONFLICT(source_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    message = EXCLUDED.message,
                    last_checked_at = EXCLUDED.last_checked_at,
                    last_success_at = CASE
                        WHEN EXCLUDED.status = 'ok' THEN EXCLUDED.last_checked_at
                        ELSE source_health.last_success_at
                    END,
                    last_fetched_count = EXCLUDED.last_fetched_count,
                    updated_at = NOW()
                """,
                (source_id, status, message, checked_at, status, checked_at, max(0, int(fetched_count))),
            )
        conn.commit()


def normalize_legacy_mock_urls() -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE raw_signals
                SET url = 'https://www.baidu.com/s?wd=' || replace(title, ' ', '+')
                WHERE url ~ '^https://mock[\\.-]'
                """
            )
        conn.commit()


def insert_raw_signals(signals: list[RawSignal], fingerprints: list[tuple[str, str]]) -> int:
    if not signals:
        return 0

    inserted = 0
    with get_conn() as conn:
        with conn.cursor() as cur:
            for signal, fp in zip(signals, fingerprints):
                cur.execute(
                    """
                    INSERT INTO raw_signals (
                        id, source_id, title, content, url, author, publish_time,
                        metrics, extracted_keywords, language, fingerprint, weak_fingerprint
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s)
                    ON CONFLICT(id) DO NOTHING
                    """,
                    (
                        signal.id,
                        signal.source_id,
                        signal.title,
                        signal.content,
                        signal.url,
                        signal.author,
                        signal.publish_time,
                        json.dumps(signal.metrics, ensure_ascii=False),
                        signal.extracted_keywords,
                        signal.language,
                        fp[0],
                        fp[1],
                    ),
                )
                inserted += cur.rowcount
        conn.commit()
    return inserted


def get_existing_fingerprints(hours: int = 72) -> set[str]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT fingerprint FROM raw_signals WHERE publish_time >= NOW() - (%s || ' hours')::interval",
                (str(hours),),
            )
            rows = cur.fetchall()
    return {r["fingerprint"] for r in rows}


def get_existing_weak_fingerprints(hours: int = 72) -> set[tuple[str, str]]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT source_id, weak_fingerprint
                FROM raw_signals
                WHERE publish_time >= NOW() - (%s || ' hours')::interval
                """,
                (str(hours),),
            )
            rows = cur.fetchall()
    return {(r["source_id"], r["weak_fingerprint"]) for r in rows}


def list_recent_signals(hours: int = 48) -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT rs.*, s.weight as source_weight, s.enabled as source_enabled
                FROM raw_signals rs
                JOIN sources s ON s.id = rs.source_id
                WHERE rs.publish_time >= NOW() - (%s || ' hours')::interval
                  AND s.enabled = TRUE
                ORDER BY rs.publish_time DESC
                """,
                (str(hours),),
            )
            return list(cur.fetchall())


def list_source_items(source_id: str, mode: str, limit_each: int = 10) -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, source_id, title, content, url, publish_time, metrics
                FROM raw_signals
                WHERE source_id = %s
                ORDER BY publish_time DESC
                LIMIT 150
                """,
                (source_id,),
            )
            rows = list(cur.fetchall())

    def hot_score(row: dict) -> float:
        m = row.get("metrics") or {}
        likes = float(m.get("likes", 0) or 0)
        comments = float(m.get("comments", 0) or 0)
        reposts = float(m.get("reposts", 0) or 0)
        views = float(m.get("views", 0) or 0)
        return math.log1p(likes) + 1.5 * math.log1p(comments) + 2.0 * math.log1p(reposts) + 0.5 * math.log1p(views)

    hot_rows = sorted(rows, key=hot_score, reverse=True)[:limit_each]
    new_rows = sorted(rows, key=lambda x: x["publish_time"], reverse=True)[:limit_each]

    def serialize(row: dict, mode_label: str) -> dict:
        return {
            "id": row["id"],
            "title": row["title"],
            "summary": (row.get("content") or "")[:120],
            "url": row["url"],
            "publish_time": row["publish_time"].isoformat(),
            "mode": mode_label,
        }

    if mode == "hot":
        return [serialize(x, "hot") for x in hot_rows]
    if mode == "new":
        return [serialize(x, "new") for x in new_rows]

    seen: set[str] = set()
    combined: list[dict] = []
    for x in hot_rows:
        if x["id"] in seen:
            continue
        seen.add(x["id"])
        combined.append(serialize(x, "hot"))
    for x in new_rows:
        if x["id"] in seen:
            continue
        seen.add(x["id"])
        combined.append(serialize(x, "new"))
    return combined[: limit_each * 2]


def list_events(limit: int = 200, category: str | None = None) -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            if category:
                cur.execute(
                    "SELECT * FROM events WHERE category = %s ORDER BY heat_score DESC LIMIT %s",
                    (category, limit),
                )
            else:
                cur.execute("SELECT * FROM events ORDER BY heat_score DESC LIMIT %s", (limit,))
            return list(cur.fetchall())


def get_event(event_id: str) -> dict | None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM events WHERE id = %s", (event_id,))
            return cur.fetchone()


def get_event_signals(event_id: str) -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT rs.*, s.name AS source_name
                FROM event_signal_mapping esm
                JOIN raw_signals rs ON rs.id = esm.signal_id
                JOIN sources s ON s.id = rs.source_id
                WHERE esm.event_id = %s
                ORDER BY rs.publish_time DESC
                """,
                (event_id,),
            )
            return list(cur.fetchall())


def list_previous_events_map() -> dict[str, dict]:
    rows = list_events(limit=2000)
    return {r["id"]: r for r in rows}


def save_events(events: list[EventModel], observed_at: datetime) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM event_signal_mapping")
            cur.execute("DELETE FROM events")

            for event in events:
                cur.execute(
                    """
                    INSERT INTO events (
                        id, title, summary, category, heat_score, growth_rate,
                        first_seen_time, last_updated_time, source_count, signals_count,
                        top_keywords, is_breaking, breaking_until, source_breakdown, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, NOW())
                    """,
                    (
                        event.id,
                        event.title,
                        event.summary,
                        event.category,
                        event.heat_score,
                        event.growth_rate,
                        event.first_seen_time,
                        event.last_updated_time,
                        event.source_count,
                        event.signals_count,
                        event.top_keywords,
                        event.is_breaking,
                        event.breaking_until,
                        json.dumps(event.source_breakdown, ensure_ascii=False),
                    ),
                )

                for sid in event.signal_ids:
                    cur.execute(
                        """
                        INSERT INTO event_signal_mapping(event_id, signal_id)
                        SELECT %s, %s
                        WHERE EXISTS (SELECT 1 FROM raw_signals WHERE id = %s)
                        """,
                        (event.id, sid, sid),
                    )

                cur.execute(
                    "INSERT INTO event_heat_history(event_id, observed_at, heat_score) VALUES (%s, %s, %s)",
                    (event.id, observed_at, event.heat_score),
                )
        conn.commit()


def get_event_heat_trend(event_id: str, hours: int = 24) -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT observed_at, heat_score
                FROM event_heat_history
                WHERE event_id = %s
                  AND observed_at >= NOW() - (%s || ' hours')::interval
                ORDER BY observed_at ASC
                """,
                (event_id, str(hours)),
            )
            return list(cur.fetchall())


def save_daily_snapshot(snapshot_date: str, version: str, payload: dict) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO daily_snapshots(snapshot_date, version, payload)
                VALUES (%s, %s, %s::jsonb)
                ON CONFLICT(snapshot_date, version) DO UPDATE SET
                  payload = EXCLUDED.payload,
                  created_at = NOW()
                """,
                (snapshot_date, version, json.dumps(payload, ensure_ascii=False)),
            )
        conn.commit()


def get_latest_snapshot() -> dict | None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM daily_snapshots ORDER BY created_at DESC LIMIT 1")
            return cur.fetchone()


def start_pipeline_run() -> int:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO pipeline_runs(status, message) VALUES (%s, %s) RETURNING id",
                ("running", "pipeline started"),
            )
            rid = cur.fetchone()["id"]
        conn.commit()
    return rid


def finish_pipeline_run(run_id: int, status: str, message: str) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE pipeline_runs SET status=%s, message=%s, finished_at=NOW() WHERE id=%s",
                (status, message, run_id),
            )
        conn.commit()


def source_contribution_today() -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH signal_cte AS (
                  SELECT source_id, COUNT(*) AS signals_count
                  FROM raw_signals
                  WHERE publish_time::date = (NOW() AT TIME ZONE 'Asia/Shanghai')::date
                  GROUP BY source_id
                ),
                event_cte AS (
                  SELECT rs.source_id, COUNT(DISTINCT esm.event_id) AS events_count
                  FROM event_signal_mapping esm
                  JOIN raw_signals rs ON rs.id = esm.signal_id
                  GROUP BY rs.source_id
                )
                SELECT s.id, s.name, s.enabled, s.mode, s.weight, s.last_fetch,
                       s.is_mock,
                       COALESCE(sh.status, 'unknown') AS availability_status,
                       sh.message AS availability_message,
                       sh.last_checked_at AS availability_checked_at,
                       COALESCE(sh.last_fetched_count, 0) AS availability_fetched_count,
                       COALESCE(sc.signals_count, 0) AS today_signals,
                       COALESCE(ec.events_count, 0) AS covered_events
                FROM sources s
                LEFT JOIN source_health sh ON sh.source_id = s.id
                LEFT JOIN signal_cte sc ON sc.source_id = s.id
                LEFT JOIN event_cte ec ON ec.source_id = s.id
                ORDER BY s.id
                """
            )
            return list(cur.fetchall())
