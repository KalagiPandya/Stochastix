"""
services/stream.py
Binance WebSocket streaming service.
Runs in a background thread and feeds data into DuckDB.
Falls back to REST polling if WebSocket is unavailable.
"""

import threading
import logging
import time
import json
import requests
from datetime import datetime, timezone
from collections import defaultdict

try:
    import websocket
    WS_AVAILABLE = True
except ImportError:
    WS_AVAILABLE = False

from pipeline import insert_tick, insert_metrics, upsert_candle
from services.analytics import sma, ema, volatility, z_score, is_anomaly
from services.streaming_backbone import get_backbone

logger = logging.getLogger(__name__)

# ── In-memory ring buffer (last 500 ticks per symbol) ──────────────────────
_price_buffer: dict[str, list[float]] = defaultdict(list)
_buffer_lock = threading.Lock()
_MAX_BUFFER = 500

# ── Candle state ────────────────────────────────────────────────────────────
_candle_state: dict[str, dict] = {}

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
WS_BASE = "wss://stream.binance.com:9443/stream?streams="
REST_URL = "https://api.binance.com/api/v3/ticker/price"

_stream_thread: threading.Thread | None = None
_stop_event = threading.Event()


def _push_price(symbol: str, price: float, volume: float = 0.0) -> None:
    """Store tick in memory buffer + DB, compute analytics."""
    with _buffer_lock:
        buf = _price_buffer[symbol]
        buf.append(price)
        if len(buf) > _MAX_BUFFER:
            buf.pop(0)
        prices = list(buf)

    # Persist raw tick
    insert_tick(symbol, price, volume)

    # Publish raw tick to Kafka / Redis Streams (no-op if not configured)
    backbone = get_backbone()
    backbone.publish_tick(symbol, price, volume)

    # Compute analytics
    _sma = sma(prices, 20)
    _ema = ema(prices, 20)
    _vol = volatility(prices, 20)
    _z = z_score(price, prices, 30)
    _anomaly = is_anomaly(_z)

    if _sma is not None:
        insert_metrics(symbol, _sma, _ema or _sma, _vol, _z or 0.0, _anomaly)
        backbone.publish_metric(
            symbol, sma=_sma, ema=_ema or _sma, volatility=_vol,
            z_score=_z or 0.0, anomaly_flag=_anomaly,
        )
        if _anomaly:
            backbone.publish_anomaly(symbol, price=price, z_score=_z, method="z_score")

    # Update 1-minute candle
    _update_candle(symbol, price, volume)


def _update_candle(symbol: str, price: float, volume: float) -> None:
    now = datetime.now(timezone.utc)
    candle_ts = now.replace(second=0, microsecond=0)

    state = _candle_state.get(symbol)
    if state is None or state["ts"] != candle_ts:
        _candle_state[symbol] = {
            "ts": candle_ts, "open": price, "high": price,
            "low": price, "close": price, "volume": volume
        }
    else:
        state["high"] = max(state["high"], price)
        state["low"] = min(state["low"], price)
        state["close"] = price
        state["volume"] += volume

    s = _candle_state[symbol]
    upsert_candle(symbol, s["ts"], s["open"], s["high"], s["low"], s["close"], s["volume"])


# ── WebSocket handler ────────────────────────────────────────────────────────

def _on_message(ws, message: str) -> None:
    try:
        data = json.loads(message)
        stream = data.get("stream", "")
        payload = data.get("data", {})
        # Trade stream: btcusdt@trade
        if "@trade" in stream:
            symbol = payload.get("s", "").upper()
            price = float(payload.get("p", 0))
            qty = float(payload.get("q", 0))
            if price > 0:
                _push_price(symbol, price, qty)
    except Exception as e:
        logger.error("WS message error: %s", e)


def _on_error(ws, error) -> None:
    logger.warning("WS error: %s", error)


def _on_close(ws, close_status_code, close_msg) -> None:
    logger.info("WS closed: %s %s", close_status_code, close_msg)


def _on_open(ws) -> None:
    logger.info("WS connection opened")


def _run_websocket() -> None:
    streams = "/".join(f"{s.lower()}@trade" for s in SYMBOLS)
    url = WS_BASE + streams
    retry_delay = 2

    while not _stop_event.is_set():
        try:
            ws = websocket.WebSocketApp(
                url,
                on_open=_on_open,
                on_message=_on_message,
                on_error=_on_error,
                on_close=_on_close,
            )
            ws.run_forever(ping_interval=30, ping_timeout=10)
        except Exception as e:
            logger.error("WS connection failed: %s — retrying in %ss", e, retry_delay)

        if not _stop_event.is_set():
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 30)  # exponential backoff


def _run_rest_fallback() -> None:
    """REST polling fallback when WebSocket is unavailable."""
    logger.info("Starting REST polling fallback")
    while not _stop_event.is_set():
        for symbol in SYMBOLS:
            try:
                r = requests.get(REST_URL, params={"symbol": symbol}, timeout=5)
                r.raise_for_status()
                price = float(r.json()["price"])
                _push_price(symbol, price)
            except requests.RequestException as e:
                logger.warning("REST fetch failed for %s: %s", symbol, e)
        time.sleep(2)


# ── Public API ───────────────────────────────────────────────────────────────

def start_stream() -> None:
    """Start the background streaming thread (idempotent)."""
    global _stream_thread
    if _stream_thread and _stream_thread.is_alive():
        return
    _stop_event.clear()
    target = _run_websocket if WS_AVAILABLE else _run_rest_fallback
    _stream_thread = threading.Thread(target=target, daemon=True, name="stochastix-stream")
    _stream_thread.start()
    logger.info("Stream thread started (WS=%s)", WS_AVAILABLE)


def stop_stream() -> None:
    _stop_event.set()


def get_buffer(symbol: str) -> list[float]:
    with _buffer_lock:
        return list(_price_buffer.get(symbol, []))


def latest_price(symbol: str) -> float | None:
    buf = get_buffer(symbol)
    return buf[-1] if buf else None
