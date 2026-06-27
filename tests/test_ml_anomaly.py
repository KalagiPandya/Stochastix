"""
tests/test_ml_anomaly.py
Unit tests for the ML-based anomaly detectors. Each detector degrades
gracefully (available=False) when its optional dependency isn't installed,
so these tests assert on that contract as well as on correct scoring when
the dependency IS present.
"""

import numpy as np
import pytest

from services.ml_anomaly import (
    IsolationForestDetector,
    ProphetDetector,
    LSTMAnomalyDetector,
    MLAnomalyEnsemble,
    AnomalyResult,
)


@pytest.fixture
def normal_prices():
    rng = np.random.default_rng(42)
    return list(100 + rng.normal(0, 1, 150).cumsum() * 0.1 + 100)


@pytest.fixture
def spike_prices(normal_prices):
    prices = list(normal_prices)
    prices[-1] = prices[-1] * 1.5  # 50% spike
    return prices


class TestIsolationForestDetector:
    def test_insufficient_data_returns_safe_default(self):
        det = IsolationForestDetector()
        result = det.score([100.0, 101.0])
        assert isinstance(result, AnomalyResult)
        assert result.is_anomaly is False
        assert result.method == "isolation_forest"

    def test_scores_normal_and_spike_data(self, normal_prices, spike_prices):
        det = IsolationForestDetector(window=100)
        result_normal = det.score(normal_prices)
        if not result_normal.available:
            pytest.skip("scikit-learn not installed")

        det2 = IsolationForestDetector(window=100)
        result_spike = det2.score(spike_prices)

        assert result_normal.method == "isolation_forest"
        assert result_spike.method == "isolation_forest"
        assert 0.0 <= result_normal.score <= 1.0
        assert 0.0 <= result_spike.score <= 1.0


class TestProphetDetector:
    def test_insufficient_data_returns_safe_default(self):
        det = ProphetDetector()
        result = det.score([100.0] * 5)
        assert result.is_anomaly is False
        assert result.method == "prophet"

    def test_unavailable_reports_gracefully(self, normal_prices):
        det = ProphetDetector()
        if det._available:
            pytest.skip("prophet is installed; availability test not applicable")
        result = det.score(normal_prices)
        assert result.available is False
        assert result.error is not None


class TestLSTMAnomalyDetector:
    def test_insufficient_data_returns_safe_default(self):
        det = LSTMAnomalyDetector(seq_len=20)
        result = det.score([100.0] * 10)
        assert result.is_anomaly is False
        assert result.method == "lstm_autoencoder"

    def test_unavailable_reports_gracefully(self, normal_prices):
        det = LSTMAnomalyDetector(seq_len=10)
        if det._available:
            pytest.skip("torch is installed; availability test not applicable")
        result = det.score(normal_prices)
        assert result.available is False
        assert result.error is not None


class TestMLAnomalyEnsemble:
    def test_score_all_returns_three_methods(self, normal_prices):
        ensemble = MLAnomalyEnsemble()
        results = ensemble.score_all("TESTUSDT", normal_prices)
        assert set(results.keys()) == {"isolation_forest", "prophet", "lstm_autoencoder"}
        for r in results.values():
            assert isinstance(r, AnomalyResult)

    def test_ensemble_vote_with_no_available_detectors(self):
        results = {
            "a": AnomalyResult(is_anomaly=False, score=0.0, method="a", available=False, error="missing"),
            "b": AnomalyResult(is_anomaly=False, score=0.0, method="b", available=False, error="missing"),
        }
        vote = MLAnomalyEnsemble.ensemble_vote(results)
        assert vote["anomaly"] is False
        assert vote["of"] == 0

    def test_ensemble_vote_majority(self):
        results = {
            "a": AnomalyResult(is_anomaly=True, score=0.9, method="a"),
            "b": AnomalyResult(is_anomaly=True, score=0.8, method="b"),
            "c": AnomalyResult(is_anomaly=False, score=0.1, method="c"),
        }
        vote = MLAnomalyEnsemble.ensemble_vote(results)
        assert vote["of"] == 3
        assert vote["votes"] == 2
        assert vote["anomaly"] is True
        assert 0.0 < vote["avg_score"] < 1.0
