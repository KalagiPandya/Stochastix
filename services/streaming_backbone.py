"""
services/streaming_backbone.py
Data-engineering backbone: publishes every live tick onto a message bus
(Apache Kafka or Redis Streams) so downstream consumers — analytics workers,
ML scoring services, alerting, audit logging — can subscribe independently of
the Streamlit process.

Design goals:
- Zero hard dependency: if neither `kafka-python`/`confluent-kafka` nor
  `redis` is installed, or no broker is reachable, the publisher silently
  becomes a no-op so the core dashboard keeps working.
- Pluggable backend selected via STREAM_BACKEND env var: "kafka" | "redis" | "none"
- Simple, JSON-serialised message envelope shared by both backends so a
  consumer doesn't need to care which transport was used.

Topic / stream naming convention:
    stochastix.ticks.<SYMBOL>        — raw trade ticks
    stochastix.metrics.<SYMBOL>      — computed analytics (SMA/EMA/Z-score/...)
    stochastix.anomalies.<SYMBOL>    — anomaly events (statistical + ML)

Example standalone consumer (Kafka):
    from services.streaming_backbone import KafkaTickConsumer
    for msg in KafkaTickConsumer("BTCUSDT").poll():
        print(msg)

Example standalone consumer (Redis Streams):
    from services.streaming_backbone import RedisTickConsumer
    for msg in RedisTickConsumer("BTCUSDT").poll():
        print(msg)
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

STREAM_BACKEND = os.environ.get("STREAM_BACKEND", "none").lower()  # kafka | redis | none
KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
REDIS_STREAM_MAXLEN = int(os.environ.get("REDIS_STREAM_MAXLEN", "10000"))


def _topic(kind: str, symbol: str) -> str:
    return f"stochastix.{kind}.{symbol.lower()}"


def make_envelope(kind: str, symbol: str, payload: dict) -> dict:
    return {
        "schema": "stochastix.v1",
        "kind": kind,            # tick | metric | anomaly
        "symbol": symbol,
        "ts": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }


# ── Kafka backend ─────────────────────────────────────────────────────────

class KafkaPublisher:
    """Thin wrapper around kafka-python's KafkaProducer with lazy connect
    and graceful degradation if the broker is unreachable."""

    def __init__(self, bootstrap_servers: str = KAFKA_BOOTSTRAP_SERVERS):
        self.bootstrap_servers = bootstrap_servers
        self._producer = None
        self._unavailable = False

    def _ensure_producer(self):
        if self._producer is not None or self._unavailable:
            return self._producer
        try:
            from kafka import KafkaProducer
            self._producer = KafkaProducer(
                bootstrap_servers=self.bootstrap_servers.split(","),
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                key_serializer=lambda k: k.encode("utf-8") if k else None,
                linger_ms=20,
                retries=3,
                request_timeout_ms=3000,
            )
            logger.info("Kafka producer connected: %s", self.bootstrap_servers)
        except Exception as e:
            logger.warning("Kafka unavailable (%s) — publisher disabled", e)
            self._unavailable = True
            self._producer = None
        return self._producer

    def publish(self, kind: str, symbol: str, payload: dict) -> bool:
        producer = self._ensure_producer()
        if producer is None:
            return False
        try:
            topic = _topic(kind, symbol)
            envelope = make_envelope(kind, symbol, payload)
            producer.send(topic, key=symbol, value=envelope)
            return True
        except Exception as e:
            logger.debug("Kafka publish failed: %s", e)
            return False

    def flush(self):
        if self._producer:
            try:
                self._producer.flush(timeout=2)
            except Exception:
                pass


class KafkaTickConsumer:
    """Standalone consumer for downstream services / notebooks / workers."""

    def __init__(self, symbol: str, kind: str = "ticks",
                 bootstrap_servers: str = KAFKA_BOOTSTRAP_SERVERS,
                 group_id: str = "stochastix-consumers"):
        self.symbol = symbol
        self.kind = kind
        self.bootstrap_servers = bootstrap_servers
        self.group_id = group_id

    def poll(self) -> Iterable[dict]:
        from kafka import KafkaConsumer
        consumer = KafkaConsumer(
            _topic(self.kind, self.symbol),
            bootstrap_servers=self.bootstrap_servers.split(","),
            group_id=self.group_id,
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            auto_offset_reset="latest",
        )
        for msg in consumer:
            yield msg.value


# ── Redis Streams backend ────────────────────────────────────────────────

class RedisStreamsPublisher:
    """Publishes onto Redis Streams (XADD). Lighter-weight alternative to
    Kafka for smaller deployments — still gives consumer groups, replay,
    and at-least-once delivery semantics."""

    def __init__(self, redis_url: str = REDIS_URL):
        self.redis_url = redis_url
        self._client = None
        self._unavailable = False

    def _ensure_client(self):
        if self._client is not None or self._unavailable:
            return self._client
        try:
            import redis
            self._client = redis.Redis.from_url(self.redis_url, socket_connect_timeout=2)
            self._client.ping()
            logger.info("Redis Streams connected: %s", self.redis_url)
        except Exception as e:
            logger.warning("Redis unavailable (%s) — publisher disabled", e)
            self._unavailable = True
            self._client = None
        return self._client

    def publish(self, kind: str, symbol: str, payload: dict) -> bool:
        client = self._ensure_client()
        if client is None:
            return False
        try:
            stream = _topic(kind, symbol)
            envelope = make_envelope(kind, symbol, payload)
            client.xadd(stream, {"data": json.dumps(envelope)}, maxlen=REDIS_STREAM_MAXLEN, approximate=True)
            return True
        except Exception as e:
            logger.debug("Redis Streams publish failed: %s", e)
            return False


class RedisTickConsumer:
    """Standalone consumer reading from a Redis Stream, using a consumer group
    so multiple workers can share the load with at-least-once delivery."""

    def __init__(self, symbol: str, kind: str = "ticks",
                 redis_url: str = REDIS_URL,
                 group: str = "stochastix-consumers",
                 consumer_name: str = "worker-1"):
        self.symbol = symbol
        self.kind = kind
        self.redis_url = redis_url
        self.group = group
        self.consumer_name = consumer_name

    def poll(self, block_ms: int = 5000) -> Iterable[dict]:
        import redis
        client = redis.Redis.from_url(self.redis_url)
        stream = _topic(self.kind, self.symbol)

        try:
            client.xgroup_create(stream, self.group, id="0", mkstream=True)
        except redis.exceptions.ResponseError:
            pass  # group already exists

        while True:
            resp = client.xreadgroup(
                self.group, self.consumer_name,
                {stream: ">"}, count=10, block=block_ms,
            )
            for _stream_name, messages in resp or []:
                for msg_id, fields in messages:
                    try:
                        yield json.loads(fields[b"data"])
                    finally:
                        client.xack(stream, self.group, msg_id)


# ── Unified publisher facade ─────────────────────────────────────────────

class StreamingBackbone:
    """
    Picks the configured backend (Kafka, Redis Streams, or none) and exposes
    a single `publish_tick` / `publish_metric` / `publish_anomaly` API used
    by `services/stream.py`. Safe to call even when no broker is configured —
    publishes simply become no-ops, returning False.
    """

    def __init__(self, backend: str = STREAM_BACKEND):
        self.backend = backend
        self._impl = None
        if backend == "kafka":
            self._impl = KafkaPublisher()
        elif backend == "redis":
            self._impl = RedisStreamsPublisher()
        elif backend not in ("none", ""):
            logger.warning("Unknown STREAM_BACKEND=%s — streaming disabled", backend)

    @property
    def enabled(self) -> bool:
        return self._impl is not None

    def publish_tick(self, symbol: str, price: float, volume: float) -> bool:
        if self._impl is None:
            return False
        return self._impl.publish("ticks", symbol, {"price": price, "volume": volume})

    def publish_metric(self, symbol: str, **metrics) -> bool:
        if self._impl is None:
            return False
        return self._impl.publish("metrics", symbol, metrics)

    def publish_anomaly(self, symbol: str, **details) -> bool:
        if self._impl is None:
            return False
        return self._impl.publish("anomalies", symbol, details)


_backbone: Optional[StreamingBackbone] = None


def get_backbone() -> StreamingBackbone:
    global _backbone
    if _backbone is None:
        _backbone = StreamingBackbone()
    return _backbone


# ── CLI demo consumer ────────────────────────────────────────────────────

if __name__ == "__main__":  # pragma: no cover
    import sys

    backend = STREAM_BACKEND
    symbol = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    print(f"Listening on backend={backend} symbol={symbol} (Ctrl+C to stop)")

    if backend == "kafka":
        for m in KafkaTickConsumer(symbol).poll():
            print(m)
    elif backend == "redis":
        for m in RedisTickConsumer(symbol).poll():
            print(m)
    else:
        print("Set STREAM_BACKEND=kafka or STREAM_BACKEND=redis to run a consumer.")
        while True:
            time.sleep(1)
