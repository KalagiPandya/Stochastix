"""
pipeline/database.py
Persistent time-series storage using DuckDB.

DuckDB only allows one writer process at a time. We solve this with:
1. A module-level singleton connection (one per process)
2. A threading.Lock so the background stream thread and Streamlit
   reruns never call duckdb simultaneously and cause file-lock errors.
"""

import duckdb
import os
import threading
import logging

logger = logging.getLogger(__name__)

DB_PATH = os.environ.get("STOCHASTIX_DB", "stochastix.db")

_conn: duckdb.DuckDBPyConnection | None = None
_lock = threading.Lock()


def get_connection() -> duckdb.DuckDBPyConnection:
    """Return the single shared DuckDB connection, creating it once per process."""
    global _conn
    if _conn is None:
        with _lock:
            if _conn is None:
                _conn = duckdb.connect(DB_PATH)
                logger.info("DuckDB connection opened: %s", DB_PATH)
    return _conn


def _exec(sql: str, params: list = None) -> None:
    """Thread-safe execute (write)."""
    with _lock:
        con = get_connection()
        if params:
            con.execute(sql, params)
        else:
            con.execute(sql)
        con.commit()


def _query(sql: str, params: list = None):
    """Thread-safe query (read) returning a DataFrame."""
    with _lock:
        con = get_connection()
        if params:
            return con.execute(sql, params).fetchdf()
        return con.execute(sql).fetchdf()


def _query_one(sql: str, params: list = None):
    """Thread-safe fetchone."""
    with _lock:
        con = get_connection()
        if params:
            return con.execute(sql, params).fetchone()
        return con.execute(sql).fetchone()


def init_db() -> None:
    """Create tables and sequences if they don't exist."""
    con = get_connection()
    with _lock:
        con.execute("""
            CREATE TABLE IF NOT EXISTS market_data (
                id        INTEGER PRIMARY KEY,
                symbol    VARCHAR NOT NULL,
                price     DOUBLE  NOT NULL,
                volume    DOUBLE  DEFAULT 0,
                ts        TIMESTAMP NOT NULL DEFAULT current_timestamp
            )
        """)
        con.execute("""
            CREATE SEQUENCE IF NOT EXISTS market_data_id_seq START 1
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS analytics_metrics (
                id           INTEGER PRIMARY KEY,
                symbol       VARCHAR  NOT NULL,
                sma          DOUBLE,
                ema          DOUBLE,
                volatility   DOUBLE,
                z_score      DOUBLE,
                anomaly_flag BOOLEAN DEFAULT FALSE,
                ml_score     DOUBLE,
                ml_method    VARCHAR,
                ts           TIMESTAMP NOT NULL DEFAULT current_timestamp
            )
        """)
        con.execute("""
            CREATE SEQUENCE IF NOT EXISTS analytics_metrics_id_seq START 1
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS ohlc_candles (
                symbol    VARCHAR NOT NULL,
                open      DOUBLE  NOT NULL,
                high      DOUBLE  NOT NULL,
                low       DOUBLE  NOT NULL,
                close     DOUBLE  NOT NULL,
                volume    DOUBLE  DEFAULT 0,
                candle_ts TIMESTAMP NOT NULL,
                PRIMARY KEY (symbol, candle_ts)
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY,
                username      VARCHAR UNIQUE NOT NULL,
                email         VARCHAR UNIQUE NOT NULL,
                password_hash VARCHAR NOT NULL,
                role          VARCHAR NOT NULL DEFAULT 'viewer',
                is_active     BOOLEAN DEFAULT TRUE,
                created_at    TIMESTAMP NOT NULL DEFAULT current_timestamp
            )
        """)
        con.execute("""
            CREATE SEQUENCE IF NOT EXISTS users_id_seq START 1
        """)
        con.commit()
    logger.info("Database initialised at %s", DB_PATH)


def insert_tick(symbol: str, price: float, volume: float = 0.0) -> None:
    try:
        _exec("""
            INSERT INTO market_data (id, symbol, price, volume, ts)
            VALUES (nextval('market_data_id_seq'), ?, ?, ?, current_timestamp)
        """, [symbol, price, volume])
    except Exception as e:
        logger.error("insert_tick error: %s", e)


def insert_metrics(symbol: str, sma: float, ema: float,
                   volatility: float, z_score: float, anomaly: bool,
                   ml_score: float = None, ml_method: str = None) -> None:
    try:
        _exec("""
            INSERT INTO analytics_metrics
                (id, symbol, sma, ema, volatility, z_score, anomaly_flag, ml_score, ml_method, ts)
            VALUES (nextval('analytics_metrics_id_seq'), ?, ?, ?, ?, ?, ?, ?, ?, current_timestamp)
        """, [symbol, sma, ema, volatility, z_score, anomaly, ml_score, ml_method])
    except Exception as e:
        logger.error("insert_metrics error: %s", e)


def upsert_candle(symbol: str, candle_ts, o: float, h: float,
                  l: float, c: float, vol: float) -> None:
    try:
        _exec("""
            INSERT INTO ohlc_candles (symbol, open, high, low, close, volume, candle_ts)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (symbol, candle_ts) DO UPDATE SET
                high   = GREATEST(excluded.high,  ohlc_candles.high),
                low    = LEAST(excluded.low,    ohlc_candles.low),
                close  = excluded.close,
                volume = ohlc_candles.volume + excluded.volume
        """, [symbol, o, h, l, c, vol, candle_ts])
    except Exception as e:
        logger.error("upsert_candle error: %s", e)


def fetch_recent_ticks(symbol: str, limit: int = 300):
    return _query("""
        SELECT price, ts FROM market_data
        WHERE symbol = ?
        ORDER BY ts DESC
        LIMIT ?
    """, [symbol, limit])


def fetch_analytics(symbol: str, limit: int = 300):
    return _query("""
        SELECT sma, ema, volatility, z_score, anomaly_flag, ml_score, ml_method, ts
        FROM analytics_metrics
        WHERE symbol = ?
        ORDER BY ts DESC
        LIMIT ?
    """, [symbol, limit])


def fetch_candles(symbol: str, limit: int = 100):
    return _query("""
        SELECT open, high, low, close, volume, candle_ts
        FROM ohlc_candles
        WHERE symbol = ?
        ORDER BY candle_ts DESC
        LIMIT ?
    """, [symbol, limit])


def fetch_latest_price(symbol: str) -> float | None:
    row = _query_one("""
        SELECT price FROM market_data
        WHERE symbol = ?
        ORDER BY ts DESC
        LIMIT 1
    """, [symbol])
    return row[0] if row else None


def count_anomalies(symbol: str, minutes: int = 60) -> int:
    row = _query_one("""
        SELECT COUNT(*) FROM analytics_metrics
        WHERE symbol = ?
          AND anomaly_flag = TRUE
          AND ts >= current_timestamp - INTERVAL (? || ' minutes')
    """, [symbol, str(minutes)])
    return row[0] if row else 0
