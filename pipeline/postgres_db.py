"""
pipeline/postgres_db.py
Enterprise-grade persistence layer using PostgreSQL + TimescaleDB.

This is an alternative backend to `pipeline/database.py` (DuckDB), selected
via the DB_BACKEND env var:

    DB_BACKEND=duckdb     (default) — embedded, zero-config, single-process
    DB_BACKEND=postgres   — TimescaleDB hypertables, multi-node ready

Why TimescaleDB:
- `market_data`, `analytics_metrics`, and `ohlc_candles` become hypertables,
  automatically partitioned by time (chunking) for fast inserts and pruning.
- Native continuous aggregates can pre-compute OHLC candles at the DB layer.
- Standard PostgreSQL underneath -> works with any BI tool, ORM, or
  replication / HA setup (Patroni, RDS Multi-AZ, Cloud SQL, etc.)
- Retention policies (`add_retention_policy`) automatically drop old chunks
  so storage stays bounded in a long-running production deployment.

The public function names mirror `pipeline/database.py` so `app.py` and the
page modules can switch backends via `pipeline/__init__.py` without code
changes elsewhere.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager

logger = logging.getLogger(__name__)

PG_HOST = os.environ.get("POSTGRES_HOST", "localhost")
PG_PORT = os.environ.get("POSTGRES_PORT", "5432")
PG_DB = os.environ.get("POSTGRES_DB", "stochastix")
PG_USER = os.environ.get("POSTGRES_USER", "stochastix")
PG_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "stochastix")
PG_RETENTION_DAYS = os.environ.get("POSTGRES_RETENTION_DAYS", "30")

_pool = None


def _dsn() -> str:
    return f"host={PG_HOST} port={PG_PORT} dbname={PG_DB} user={PG_USER} password={PG_PASSWORD}"


def _get_pool():
    global _pool
    if _pool is None:
        import psycopg2.pool
        _pool = psycopg2.pool.ThreadedConnectionPool(1, 10, dsn=_dsn())
        logger.info("PostgreSQL connection pool created (%s:%s/%s)", PG_HOST, PG_PORT, PG_DB)
    return _pool


@contextmanager
def _conn():
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def _exec(sql: str, params: tuple = None) -> None:
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(sql, params or ())


def _query(sql: str, params: tuple = None):
    """Returns a pandas DataFrame, matching the DuckDB module's API."""
    import pandas as pd
    with _conn() as conn:
        return pd.read_sql_query(sql, conn, params=params)


def _query_one(sql: str, params: tuple = None):
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(sql, params or ())
        return cur.fetchone()


# ── Schema / hypertable setup ────────────────────────────────────────────

def init_db() -> None:
    """Create tables, convert to TimescaleDB hypertables, add indexes,
    enable compression and a retention policy. Idempotent — safe to call
    on every app start."""

    table_statements = [
        """
        CREATE TABLE IF NOT EXISTS market_data (
            id      BIGSERIAL,
            symbol  VARCHAR(20) NOT NULL,
            price   DOUBLE PRECISION NOT NULL,
            volume  DOUBLE PRECISION DEFAULT 0,
            ts      TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (ts, id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS analytics_metrics (
            id            BIGSERIAL,
            symbol        VARCHAR(20) NOT NULL,
            sma           DOUBLE PRECISION,
            ema           DOUBLE PRECISION,
            volatility    DOUBLE PRECISION,
            z_score       DOUBLE PRECISION,
            anomaly_flag  BOOLEAN DEFAULT FALSE,
            ml_score      DOUBLE PRECISION,
            ml_method     VARCHAR(40),
            ts            TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (ts, id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS ohlc_candles (
            symbol     VARCHAR(20) NOT NULL,
            open       DOUBLE PRECISION NOT NULL,
            high       DOUBLE PRECISION NOT NULL,
            low        DOUBLE PRECISION NOT NULL,
            close      DOUBLE PRECISION NOT NULL,
            volume     DOUBLE PRECISION DEFAULT 0,
            candle_ts  TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (candle_ts, symbol)
        )
        """,
        # Auth tables — used by auth/security.py regardless of DB backend
        # when DB_BACKEND=postgres (kept here so a single init_db() call
        # provisions everything for a fresh deployment).
        """
        CREATE TABLE IF NOT EXISTS users (
            id            BIGSERIAL PRIMARY KEY,
            username      VARCHAR(64) UNIQUE NOT NULL,
            email         VARCHAR(255) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            role          VARCHAR(20) NOT NULL DEFAULT 'viewer',
            is_active     BOOLEAN DEFAULT TRUE,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
    ]

    index_statements = [
        "CREATE INDEX IF NOT EXISTS idx_market_data_symbol_ts ON market_data (symbol, ts DESC)",
        "CREATE INDEX IF NOT EXISTS idx_analytics_symbol_ts ON analytics_metrics (symbol, ts DESC)",
        "CREATE INDEX IF NOT EXISTS idx_candles_symbol_ts ON ohlc_candles (symbol, candle_ts DESC)",
    ]

    # TimescaleDB-specific: hypertables, compression, retention.
    # Wrapped individually in try/except so a plain-PostgreSQL deployment
    # (without the timescaledb extension) still gets working plain tables.
    timescale_statements = [
        "CREATE EXTENSION IF NOT EXISTS timescaledb",
        "SELECT create_hypertable('market_data', 'ts', if_not_exists => TRUE, migrate_data => TRUE)",
        "SELECT create_hypertable('analytics_metrics', 'ts', if_not_exists => TRUE, migrate_data => TRUE)",
        "SELECT create_hypertable('ohlc_candles', 'candle_ts', if_not_exists => TRUE, migrate_data => TRUE)",
        "ALTER TABLE market_data SET (timescaledb.compress, timescaledb.compress_segmentby = 'symbol')",
        "SELECT add_compression_policy('market_data', INTERVAL '1 day', if_not_exists => TRUE)",
        f"SELECT add_retention_policy('market_data', INTERVAL '{PG_RETENTION_DAYS} days', if_not_exists => TRUE)",
        f"SELECT add_retention_policy('analytics_metrics', INTERVAL '{PG_RETENTION_DAYS} days', if_not_exists => TRUE)",
    ]

    for stmt in table_statements:
        _exec(stmt)
    for stmt in index_statements:
        _exec(stmt)

    for stmt in timescale_statements:
        try:
            _exec(stmt)
        except Exception as e:
            logger.debug("TimescaleDB statement skipped (%s): %s", stmt.split()[0:3], e)

    logger.info("PostgreSQL/TimescaleDB schema ready (db=%s)", PG_DB)


# ── Write API (mirrors pipeline/database.py) ─────────────────────────────

def insert_tick(symbol: str, price: float, volume: float = 0.0) -> None:
    try:
        _exec(
            "INSERT INTO market_data (symbol, price, volume, ts) VALUES (%s, %s, %s, now())",
            (symbol, price, volume),
        )
    except Exception as e:
        logger.error("insert_tick error: %s", e)


def insert_metrics(symbol: str, sma: float, ema: float, volatility: float,
                    z_score: float, anomaly: bool,
                    ml_score: float = None, ml_method: str = None) -> None:
    try:
        _exec(
            """
            INSERT INTO analytics_metrics
                (symbol, sma, ema, volatility, z_score, anomaly_flag, ml_score, ml_method, ts)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now())
            """,
            (symbol, sma, ema, volatility, z_score, anomaly, ml_score, ml_method),
        )
    except Exception as e:
        logger.error("insert_metrics error: %s", e)


def upsert_candle(symbol: str, candle_ts, o: float, h: float,
                   l: float, c: float, vol: float) -> None:
    try:
        _exec(
            """
            INSERT INTO ohlc_candles (symbol, open, high, low, close, volume, candle_ts)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (candle_ts, symbol) DO UPDATE SET
                high   = GREATEST(EXCLUDED.high,  ohlc_candles.high),
                low    = LEAST(EXCLUDED.low,    ohlc_candles.low),
                close  = EXCLUDED.close,
                volume = ohlc_candles.volume + EXCLUDED.volume
            """,
            (symbol, o, h, l, c, vol, candle_ts),
        )
    except Exception as e:
        logger.error("upsert_candle error: %s", e)


# ── Read API (mirrors pipeline/database.py) ──────────────────────────────

def fetch_recent_ticks(symbol: str, limit: int = 300):
    return _query(
        "SELECT price, ts FROM market_data WHERE symbol = %s ORDER BY ts DESC LIMIT %s",
        (symbol, limit),
    )


def fetch_analytics(symbol: str, limit: int = 300):
    return _query(
        """
        SELECT sma, ema, volatility, z_score, anomaly_flag, ml_score, ml_method, ts
        FROM analytics_metrics WHERE symbol = %s ORDER BY ts DESC LIMIT %s
        """,
        (symbol, limit),
    )


def fetch_candles(symbol: str, limit: int = 100):
    return _query(
        """
        SELECT open, high, low, close, volume, candle_ts
        FROM ohlc_candles WHERE symbol = %s ORDER BY candle_ts DESC LIMIT %s
        """,
        (symbol, limit),
    )


def fetch_latest_price(symbol: str):
    row = _query_one(
        "SELECT price FROM market_data WHERE symbol = %s ORDER BY ts DESC LIMIT 1",
        (symbol,),
    )
    return row[0] if row else None


def count_anomalies(symbol: str, minutes: int = 60) -> int:
    row = _query_one(
        """
        SELECT COUNT(*) FROM analytics_metrics
        WHERE symbol = %s AND anomaly_flag = TRUE
          AND ts >= now() - (%s || ' minutes')::interval
        """,
        (symbol, str(minutes)),
    )
    return row[0] if row else 0


# ── Continuous aggregate helper (TimescaleDB-only convenience) ───────────

CONTINUOUS_AGGREGATE_SQL = """
-- Optional: run once to let TimescaleDB pre-compute 1-minute OHLC candles
-- straight from market_data via a continuous aggregate, instead of (or in
-- addition to) the application-level upsert_candle() path.
CREATE MATERIALIZED VIEW IF NOT EXISTS ohlc_1min
WITH (timescaledb.continuous) AS
SELECT
    symbol,
    time_bucket('1 minute', ts) AS bucket,
    first(price, ts) AS open,
    max(price)       AS high,
    min(price)       AS low,
    last(price, ts)  AS close,
    sum(volume)      AS volume
FROM market_data
GROUP BY symbol, bucket;

SELECT add_continuous_aggregate_policy('ohlc_1min',
    start_offset => INTERVAL '1 hour',
    end_offset   => INTERVAL '1 minute',
    schedule_interval => INTERVAL '1 minute',
    if_not_exists => TRUE);
"""
