"""
tests/test_analytics.py
Unit tests for the quantitative analytics engine.
Run: pytest tests/ -v
"""

import pytest
import math
from services.analytics import (
    sma, ema, volatility, z_score, is_anomaly,
    rate_of_change, market_stability,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def flat_prices():
    """Prices with zero variance."""
    return [100.0] * 50


@pytest.fixture
def rising_prices():
    """Steadily rising prices."""
    return [100.0 + i for i in range(50)]


@pytest.fixture
def spike_prices():
    """Normal data with a single large spike."""
    base = [100.0 + (i % 5) for i in range(49)]
    return base + [500.0]  # extreme spike at end


# ── SMA tests ─────────────────────────────────────────────────────────────────

class TestSMA:
    def test_returns_none_when_insufficient_data(self):
        assert sma([100, 200], window=5) is None

    def test_correct_value(self):
        result = sma([10, 20, 30, 40, 50], window=5)
        assert result == pytest.approx(30.0)

    def test_uses_last_window_only(self):
        prices = [1000.0] * 10 + [200.0] * 5
        result = sma(prices, window=5)
        assert result == pytest.approx(200.0)

    def test_flat_prices(self, flat_prices):
        result = sma(flat_prices, window=20)
        assert result == pytest.approx(100.0)

    def test_single_element_window(self):
        result = sma([42.0, 99.0], window=1)
        assert result == pytest.approx(99.0)


# ── EMA tests ─────────────────────────────────────────────────────────────────

class TestEMA:
    def test_returns_none_when_insufficient_data(self):
        assert ema([100, 200], window=10) is None

    def test_flat_prices_equals_price(self, flat_prices):
        result = ema(flat_prices, window=20)
        assert result == pytest.approx(100.0, rel=1e-3)

    def test_ema_reacts_faster_than_sma_on_spike(self, spike_prices):
        """EMA should be closer to spike than SMA (more recent-weighted)."""
        _sma = sma(spike_prices, 20)
        _ema = ema(spike_prices, 20)
        assert _sma is not None and _ema is not None
        assert abs(_ema - spike_prices[-1]) <= abs(_sma - spike_prices[-1])

    def test_rising_prices_ema_above_sma(self, rising_prices):
        """For rising prices, EMA should be above SMA (weights recent higher prices more)."""
        _sma = sma(rising_prices, 20)
        _ema = ema(rising_prices, 20)
        assert _sma is not None and _ema is not None
        assert _ema >= _sma


# ── Volatility tests ──────────────────────────────────────────────────────────

class TestVolatility:
    def test_zero_variance_flat(self, flat_prices):
        result = volatility(flat_prices, window=20)
        assert result == pytest.approx(0.0, abs=1e-9)

    def test_positive_for_variable_prices(self, rising_prices):
        result = volatility(rising_prices, window=20)
        assert result > 0

    def test_spike_increases_volatility(self, flat_prices, spike_prices):
        vol_flat = volatility(flat_prices, window=20)
        vol_spike = volatility(spike_prices, window=20)
        assert vol_spike > vol_flat

    def test_single_element(self):
        result = volatility([100.0])
        assert result == pytest.approx(0.0)

    def test_two_elements(self):
        result = volatility([100.0, 110.0])
        assert result > 0


# ── Z-score tests ─────────────────────────────────────────────────────────────

class TestZScore:
    def test_returns_none_when_insufficient_data(self):
        assert z_score(100, [100, 200], window=30) is None

    def test_zero_for_mean_price(self, flat_prices):
        result = z_score(100.0, flat_prices, window=20)
        assert result == pytest.approx(0.0, abs=1e-9)

    def test_spike_has_high_z_score(self, spike_prices):
        result = z_score(spike_prices[-1], spike_prices[:-1], window=30)
        assert result is not None
        assert result > 2.5

    def test_negative_z_for_price_below_mean(self):
        prices = [100.0 + (i % 5) for i in range(35)]
        result = z_score(50.0, prices, window=30)
        assert result is not None
        assert result < 0


# ── Anomaly detection tests ───────────────────────────────────────────────────

class TestAnomalyDetection:
    def test_no_anomaly_for_none_z(self):
        assert is_anomaly(None) is False

    def test_no_anomaly_within_threshold(self):
        assert is_anomaly(2.0, threshold=2.5) is False

    def test_anomaly_above_threshold(self):
        assert is_anomaly(3.0, threshold=2.5) is True

    def test_anomaly_negative_direction(self):
        assert is_anomaly(-3.0, threshold=2.5) is True

    def test_boundary_value_not_anomaly(self):
        assert is_anomaly(2.5, threshold=2.5) is False

    def test_spike_detected_end_to_end(self, spike_prices):
        z = z_score(spike_prices[-1], spike_prices[:-1], window=30)
        assert is_anomaly(z, threshold=2.5) is True


# ── Rate of change tests ──────────────────────────────────────────────────────

class TestROC:
    def test_returns_none_when_insufficient(self):
        assert rate_of_change([100, 200], period=10) is None

    def test_flat_prices_zero_roc(self, flat_prices):
        result = rate_of_change(flat_prices, period=10)
        assert result == pytest.approx(0.0, abs=1e-9)

    def test_positive_roc_for_rising(self, rising_prices):
        result = rate_of_change(rising_prices, period=10)
        assert result is not None
        assert result > 0

    def test_roc_is_percentage(self):
        prices = [100.0] * 10 + [110.0]
        result = rate_of_change(prices, period=10)
        assert result == pytest.approx(10.0, rel=1e-3)


# ── Market stability tests ────────────────────────────────────────────────────

class TestMarketStability:
    def test_stable_low_vol(self):
        assert "Stable" in market_stability(50)

    def test_moderate_mid_vol(self):
        assert "Moderate" in market_stability(200)

    def test_volatile_high_vol(self):
        assert "Volatile" in market_stability(400)

    def test_highly_volatile_extreme(self):
        assert "Highly Volatile" in market_stability(700)
