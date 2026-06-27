"""
tests/test_streaming_backbone.py
Tests for the Kafka / Redis Streams publishing facade. With no broker
configured (the default), all publish calls must be safe no-ops.
"""

from services.streaming_backbone import (
    StreamingBackbone, make_envelope, _topic,
)


class TestEnvelope:
    def test_make_envelope_shape(self):
        env = make_envelope("ticks", "BTCUSDT", {"price": 100.0})
        assert env["schema"] == "stochastix.v1"
        assert env["kind"] == "ticks"
        assert env["symbol"] == "BTCUSDT"
        assert "ts" in env
        assert env["payload"] == {"price": 100.0}

    def test_topic_naming(self):
        assert _topic("ticks", "BTCUSDT") == "stochastix.ticks.btcusdt"
        assert _topic("anomalies", "ETHUSDT") == "stochastix.anomalies.ethusdt"


class TestStreamingBackboneNoOp:
    def test_disabled_backend_is_noop(self):
        backbone = StreamingBackbone(backend="none")
        assert backbone.enabled is False
        assert backbone.publish_tick("BTCUSDT", 100.0, 1.0) is False
        assert backbone.publish_metric("BTCUSDT", sma=100.0) is False
        assert backbone.publish_anomaly("BTCUSDT", z_score=3.0) is False

    def test_unknown_backend_is_noop(self):
        backbone = StreamingBackbone(backend="not-a-real-backend")
        assert backbone.enabled is False
        assert backbone.publish_tick("BTCUSDT", 100.0, 1.0) is False

    def test_kafka_backend_without_broker_is_safe(self):
        backbone = StreamingBackbone(backend="kafka")
        # enabled=True (impl object exists) but publish degrades to False
        # if kafka-python isn't installed or no broker is reachable.
        result = backbone.publish_tick("BTCUSDT", 100.0, 1.0)
        assert result in (True, False)

    def test_redis_backend_without_broker_is_safe(self):
        backbone = StreamingBackbone(backend="redis")
        result = backbone.publish_tick("BTCUSDT", 100.0, 1.0)
        assert result in (True, False)
