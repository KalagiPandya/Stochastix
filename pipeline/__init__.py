"""
pipeline/__init__.py

Selects the active persistence backend based on the DB_BACKEND env var:

    DB_BACKEND=duckdb     (default) -> pipeline.database   (embedded DuckDB)
    DB_BACKEND=postgres            -> pipeline.postgres_db (PostgreSQL/TimescaleDB)

Re-exports the shared API (init_db, insert_tick, insert_metrics,
upsert_candle, fetch_recent_ticks, fetch_analytics, fetch_candles,
fetch_latest_price, count_anomalies) so app.py and the page modules can do:

    from pipeline import init_db, fetch_recent_ticks, ...

without caring which database is behind it.
"""

import os

DB_BACKEND = os.environ.get("DB_BACKEND", "duckdb").lower()

if DB_BACKEND == "postgres":
    from pipeline.postgres_db import (  # noqa: F401
        init_db,
        insert_tick,
        insert_metrics,
        upsert_candle,
        fetch_recent_ticks,
        fetch_analytics,
        fetch_candles,
        fetch_latest_price,
        count_anomalies,
    )
else:
    from pipeline.database import (  # noqa: F401
        init_db,
        insert_tick,
        insert_metrics,
        upsert_candle,
        fetch_recent_ticks,
        fetch_analytics,
        fetch_candles,
        fetch_latest_price,
        count_anomalies,
    )

__all__ = [
    "DB_BACKEND",
    "init_db",
    "insert_tick",
    "insert_metrics",
    "upsert_candle",
    "fetch_recent_ticks",
    "fetch_analytics",
    "fetch_candles",
    "fetch_latest_price",
    "count_anomalies",
]
