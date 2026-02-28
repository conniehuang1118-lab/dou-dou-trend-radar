from __future__ import annotations

from pathlib import Path

from app.db import repository
from app.pipeline.engine import build_daily_snapshot, run_pipeline


def main() -> None:
    backend_dir = Path(__file__).resolve().parents[2]
    candidates = [
        backend_dir / "migrations" / "001_init.sql",  # local/render
        backend_dir.parent / "migrations" / "001_init.sql",  # docker fallback
    ]
    migration_sql = next((p for p in candidates if p.exists()), candidates[0])
    repository.run_migrations(str(migration_sql))

    result = run_pipeline()
    snapshot = build_daily_snapshot()

    print("seed/mock pipeline completed")
    print(result)
    print({"snapshot": snapshot["version"], "date": snapshot["date"]})


if __name__ == "__main__":
    main()
