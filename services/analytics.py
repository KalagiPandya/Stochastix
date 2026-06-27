"""
services/analytics.py
Quantitative analytics engine: SMA, EMA, Volatility, Z-score anomaly detection.
"""

import numpy as np
from typing import Optional


def sma(prices: list[float], window: int = 20) -> Optional[float]:
    """Simple Moving Average."""
    if len(prices) < window:
        return None
    return float(np.mean(prices[-window:]))


def ema(prices: list[float], window: int = 20) -> Optional[float]:
    """
    Exponential Moving Average.
    Reacts faster to recent price movements than SMA.
    """
    if len(prices) < window:
        return None
    k = 2 / (window + 1)
    ema_val = np.mean(prices[:window])
    for price in prices[window:]:
        ema_val = price * k + ema_val * (1 - k)
    return float(ema_val)


def volatility(prices: list[float], window: int = 20) -> float:
    """Rolling standard deviation as volatility measure."""
    if len(prices) < 2:
        return 0.0
    subset = prices[-window:] if len(prices) >= window else prices
    return float(np.std(subset))


def z_score(price: float, prices: list[float], window: int = 30) -> Optional[float]:
    """
    Z-score anomaly detection.
    Measures how many standard deviations the current price is
    from the rolling mean. |z| > 2.5 flags an anomaly.
    """
    if len(prices) < window:
        return None
    subset = np.array(prices[-window:])
    mean = np.mean(subset)
    std = np.std(subset)
    if std == 0:
        return 0.0
    return float((price - mean) / std)


def is_anomaly(z: Optional[float], threshold: float = 2.5) -> bool:
    """Return True if z-score exceeds anomaly threshold."""
    if z is None:
        return False
    return abs(z) > threshold


def rate_of_change(prices: list[float], period: int = 10) -> Optional[float]:
    """Price Rate of Change (ROC) as percentage."""
    if len(prices) < period + 1:
        return None
    old = prices[-(period + 1)]
    if old == 0:
        return None
    return float(((prices[-1] - old) / old) * 100)


def market_stability(vol: float) -> str:
    """Human-readable market stability label from volatility value."""
    if vol < 100:
        return "🟢 Stable"
    elif vol < 300:
        return "🟡 Moderate"
    elif vol < 600:
        return "🟠 Volatile"
    else:
        return "🔴 Highly Volatile"
