from __future__ import annotations

import argparse
from pathlib import Path

from app.db import repository
from app.pipeline.engine import build_daily_snapshot, run_pipeline


def _run_migrations() -> None:
    base_dir = Path(__file__).resolve().parents[3]
    migration_sql = base_dir / "migrations" / "001_init.sql"
    repository.run_migrations(str(migration_sql))


def job_refresh() -> None:
    _run_migrations()
    result = run_pipeline()
    print("[job] refresh completed")
    print(result)


def job_digest() -> None:
    _run_migrations()
    payload = build_daily_snapshot()
    print("[job] daily digest completed")
    print({"date": payload["date"], "version": payload["version"]})


def main() -> None:
    parser = argparse.ArgumentParser(description="run scheduled jobs")
    parser.add_argument("job", choices=["refresh", "digest"], help="job type")
    args = parser.parse_args()

    if args.job == "refresh":
        job_refresh()
    else:
        job_digest()


if __name__ == "__main__":
    main()
