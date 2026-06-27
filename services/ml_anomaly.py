"""
services/ml_anomaly.py
ML-based anomaly detection — upgrades the statistical Z-score detector with
three model-driven approaches:

1. Isolation Forest   — unsupervised tree ensemble, flags outlier price/volume/
                         volatility feature vectors. Fast, no training data needed
                         up-front (re-fits on a rolling window).
2. Prophet            — Facebook/Meta's additive time-series model. Forecasts an
                         expected price band; anything outside the band is an
                         anomaly. Good for seasonal/trend-aware detection.
3. LSTM Autoencoder   — deep learning sequence model (PyTorch). Learns to
                         reconstruct "normal" price sequences; large
                         reconstruction error => anomaly. Heaviest model, used
                         as the most sophisticated detector.

All detectors share a common interface:
    fit(prices: list[float]) -> None
    score(prices: list[float]) -> AnomalyResult

Each is intentionally defensive: if the optional dependency isn't installed,
the detector degrades gracefully and reports `available=False` so the UI can
explain that the package isn't installed rather than crashing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


# ── Shared result type ──────────────────────────────────────────────────────

@dataclass
class AnomalyResult:
    is_anomaly: bool
    score: float
    method: str
    available: bool = True
    detail: dict = field(default_factory=dict)
    error: Optional[str] = None


# ── 1. Isolation Forest ─────────────────────────────────────────────────────

class IsolationForestDetector:
    """
    Unsupervised anomaly detection using scikit-learn's Isolation Forest.

    Feature vector per tick: [price, return_pct, rolling_volatility]
    The model is refit periodically on the rolling window so it adapts to
    regime changes without ever needing labelled training data.
    """

    def __init__(self, window: int = 120, contamination: float = 0.03,
                 refit_every: int = 10, random_state: int = 42):
        self.window = window
        self.contamination = contamination
        self.refit_every = refit_every
        self.random_state = random_state
        self._model = None
        self._ticks_since_fit = 0
        self._available = self._check_dependency()

    @staticmethod
    def _check_dependency() -> bool:
        try:
            import sklearn  # noqa: F401
            return True
        except ImportError:
            return False

    def _features(self, prices: list[float]) -> np.ndarray:
        prices_arr = np.asarray(prices, dtype=float)
        returns = np.diff(prices_arr) / prices_arr[:-1]
        returns = np.concatenate([[0.0], returns])

        roll_vol = np.zeros_like(prices_arr)
        win = min(20, len(prices_arr))
        for i in range(len(prices_arr)):
            lo = max(0, i - win + 1)
            roll_vol[i] = prices_arr[lo:i + 1].std()

        return np.column_stack([prices_arr, returns, roll_vol])

    def score(self, prices: list[float]) -> AnomalyResult:
        if not self._available:
            return AnomalyResult(
                is_anomaly=False, score=0.0, method="isolation_forest",
                available=False,
                error="scikit-learn not installed — run `pip install scikit-learn`",
            )

        if len(prices) < max(30, self.window // 4):
            return AnomalyResult(
                is_anomaly=False, score=0.0, method="isolation_forest",
                detail={"reason": "insufficient_data", "have": len(prices)},
            )

        from sklearn.ensemble import IsolationForest

        subset = prices[-self.window:] if len(prices) >= self.window else prices
        X = self._features(subset)

        try:
            if self._model is None or self._ticks_since_fit >= self.refit_every:
                self._model = IsolationForest(
                    n_estimators=100,
                    contamination=self.contamination,
                    random_state=self.random_state,
                )
                self._model.fit(X[:-1] if len(X) > 1 else X)
                self._ticks_since_fit = 0
            self._ticks_since_fit += 1

            latest = X[-1].reshape(1, -1)
            raw_score = float(self._model.score_samples(latest)[0])
            prediction = int(self._model.predict(latest)[0])  # -1 = anomaly

            # Normalise raw decision score (~[-0.5, 0.5]) to an intuitive 0-1
            # "anomaly strength" where higher = more anomalous.
            normalised = float(np.clip(-raw_score * 2 + 0.5, 0.0, 1.0))

            return AnomalyResult(
                is_anomaly=(prediction == -1),
                score=normalised,
                method="isolation_forest",
                detail={
                    "raw_decision_score": raw_score,
                    "features": {
                        "price": float(X[-1, 0]),
                        "return_pct": float(X[-1, 1] * 100),
                        "rolling_volatility": float(X[-1, 2]),
                    },
                },
            )
        except Exception as e:
            logger.error("IsolationForest scoring error: %s", e)
            return AnomalyResult(
                is_anomaly=False, score=0.0, method="isolation_forest",
                error=str(e),
            )


# ── 2. Prophet (forecast-band anomaly detection) ────────────────────────────

class ProphetDetector:
    """
    Uses Meta's Prophet to forecast an expected price range. A live price
    falling outside the forecast's [yhat_lower, yhat_upper] band is flagged
    as an anomaly. Prophet is refit periodically since it's relatively
    expensive — it's designed for trend/seasonality-aware detection rather
    than tick-by-tick reactivity.
    """

    def __init__(self, window: int = 200, refit_every: int = 30,
                 interval_width: float = 0.95):
        self.window = window
        self.refit_every = refit_every
        self.interval_width = interval_width
        self._model = None
        self._ticks_since_fit = 0
        self._last_forecast = None
        self._available = self._check_dependency()

    @staticmethod
    def _check_dependency() -> bool:
        try:
            import prophet  # noqa: F401
            return True
        except ImportError:
            try:
                import fbprophet  # noqa: F401
                return True
            except ImportError:
                return False

    def score(self, prices: list[float]) -> AnomalyResult:
        if not self._available:
            return AnomalyResult(
                is_anomaly=False, score=0.0, method="prophet",
                available=False,
                error="prophet not installed — run `pip install prophet`",
            )

        if len(prices) < max(40, self.window // 4):
            return AnomalyResult(
                is_anomaly=False, score=0.0, method="prophet",
                detail={"reason": "insufficient_data", "have": len(prices)},
            )

        try:
            from prophet import Prophet
        except ImportError:
            from fbprophet import Prophet

        import pandas as pd
        import logging as _logging
        _logging.getLogger("cmdstanpy").setLevel(_logging.WARNING)
        _logging.getLogger("prophet").setLevel(_logging.WARNING)

        subset = prices[-self.window:] if len(prices) >= self.window else prices

        try:
            if self._model is None or self._ticks_since_fit >= self.refit_every:
                df = pd.DataFrame({
                    "ds": pd.date_range(end=pd.Timestamp.utcnow(), periods=len(subset), freq="s"),
                    "y": subset,
                })
                model = Prophet(
                    interval_width=self.interval_width,
                    changepoint_prior_scale=0.5,
                    daily_seasonality=False,
                    weekly_seasonality=False,
                    yearly_seasonality=False,
                )
                model.fit(df)

                future = model.make_future_dataframe(periods=1, freq="s")
                forecast = model.predict(future)

                self._model = model
                self._last_forecast = forecast.iloc[-1]
                self._ticks_since_fit = 0
            self._ticks_since_fit += 1

            current_price = prices[-1]
            row = self._last_forecast
            lower, upper, yhat = row["yhat_lower"], row["yhat_upper"], row["yhat"]

            band_width = max(upper - lower, 1e-9)
            # Distance outside the band, normalised by band width
            if current_price > upper:
                deviation = (current_price - upper) / band_width
            elif current_price < lower:
                deviation = (lower - current_price) / band_width
            else:
                deviation = 0.0

            anomaly = deviation > 0

            return AnomalyResult(
                is_anomaly=anomaly,
                score=float(np.clip(deviation, 0.0, 1.0)),
                method="prophet",
                detail={
                    "yhat": float(yhat),
                    "yhat_lower": float(lower),
                    "yhat_upper": float(upper),
                    "current_price": float(current_price),
                    "deviation_ratio": float(deviation),
                },
            )
        except Exception as e:
            logger.error("Prophet scoring error: %s", e)
            return AnomalyResult(
                is_anomaly=False, score=0.0, method="prophet",
                error=str(e),
            )


# ── 3. LSTM Autoencoder ──────────────────────────────────────────────────────

class LSTMAnomalyDetector:
    """
    Sequence-reconstruction anomaly detector using a small LSTM autoencoder
    (PyTorch). The model learns to reconstruct short windows of normalised
    price sequences seen so far; a high reconstruction error on the latest
    window indicates the recent price action deviates from learned "normal"
    patterns (regime shifts, flash crashes, pump-and-dumps, etc.)

    Training happens incrementally / periodically on the in-memory buffer —
    no external dataset required, matching the rest of the live pipeline.
    """

    def __init__(self, seq_len: int = 20, hidden_size: int = 16,
                 retrain_every: int = 50, epochs: int = 5):
        self.seq_len = seq_len
        self.hidden_size = hidden_size
        self.retrain_every = retrain_every
        self.epochs = epochs
        self._model = None
        self._scaler_mean = 0.0
        self._scaler_std = 1.0
        self._ticks_since_train = 0
        self._error_history: list[float] = []
        self._available = self._check_dependency()

    @staticmethod
    def _check_dependency() -> bool:
        try:
            import torch  # noqa: F401
            return True
        except ImportError:
            return False

    def _build_model(self):
        import torch
        import torch.nn as nn

        class LSTMAutoencoder(nn.Module):
            def __init__(self, seq_len: int, hidden_size: int):
                super().__init__()
                self.encoder = nn.LSTM(1, hidden_size, batch_first=True)
                self.decoder = nn.LSTM(hidden_size, hidden_size, batch_first=True)
                self.output = nn.Linear(hidden_size, 1)
                self.seq_len = seq_len
                self.hidden_size = hidden_size

            def forward(self, x):
                _, (h, c) = self.encoder(x)
                h_rep = h.permute(1, 0, 2).repeat(1, self.seq_len, 1)
                dec_out, _ = self.decoder(h_rep)
                return self.output(dec_out)

        return LSTMAutoencoder(self.seq_len, self.hidden_size)

    def _make_windows(self, prices: np.ndarray) -> np.ndarray:
        n = len(prices) - self.seq_len + 1
        if n <= 0:
            return np.empty((0, self.seq_len))
        return np.stack([prices[i:i + self.seq_len] for i in range(n)])

    def score(self, prices: list[float]) -> AnomalyResult:
        if not self._available:
            return AnomalyResult(
                is_anomaly=False, score=0.0, method="lstm_autoencoder",
                available=False,
                error="torch not installed — run `pip install torch`",
            )

        min_needed = self.seq_len * 3
        if len(prices) < min_needed:
            return AnomalyResult(
                is_anomaly=False, score=0.0, method="lstm_autoencoder",
                detail={"reason": "insufficient_data", "have": len(prices), "need": min_needed},
            )

        import torch
        import torch.nn as nn

        prices_arr = np.asarray(prices, dtype=float)

        try:
            if self._model is None or self._ticks_since_train >= self.retrain_every:
                self._scaler_mean = float(prices_arr.mean())
                self._scaler_std = float(prices_arr.std() or 1.0)

                normed = (prices_arr - self._scaler_mean) / self._scaler_std
                windows = self._make_windows(normed[:-1])  # train on history, not the live tick

                if len(windows) >= 2:
                    self._model = self._build_model()
                    optimizer = torch.optim.Adam(self._model.parameters(), lr=1e-2)
                    loss_fn = nn.MSELoss()

                    X = torch.tensor(windows, dtype=torch.float32).unsqueeze(-1)
                    self._model.train()
                    for _ in range(self.epochs):
                        optimizer.zero_grad()
                        recon = self._model(X)
                        loss = loss_fn(recon, X)
                        loss.backward()
                        optimizer.step()

                    self._ticks_since_train = 0

            self._ticks_since_train += 1

            if self._model is None:
                return AnomalyResult(
                    is_anomaly=False, score=0.0, method="lstm_autoencoder",
                    detail={"reason": "model_not_yet_trained"},
                )

            normed = (prices_arr - self._scaler_mean) / self._scaler_std
            latest_window = normed[-self.seq_len:]
            X_latest = torch.tensor(latest_window, dtype=torch.float32).reshape(1, self.seq_len, 1)

            self._model.eval()
            with torch.no_grad():
                recon = self._model(X_latest)
                error = float(torch.mean((recon - X_latest) ** 2).item())

            self._error_history.append(error)
            if len(self._error_history) > 200:
                self._error_history.pop(0)

            errs = np.asarray(self._error_history)
            err_mean, err_std = errs.mean(), (errs.std() or 1e-6)
            threshold = err_mean + 2.5 * err_std

            anomaly = error > threshold and len(self._error_history) > 10
            normalised_score = float(np.clip(error / (threshold or 1e-6), 0.0, 2.0) / 2.0)

            return AnomalyResult(
                is_anomaly=bool(anomaly),
                score=normalised_score,
                method="lstm_autoencoder",
                detail={
                    "reconstruction_error": error,
                    "threshold": float(threshold),
                    "rolling_mean_error": float(err_mean),
                },
            )
        except Exception as e:
            logger.error("LSTM autoencoder scoring error: %s", e)
            return AnomalyResult(
                is_anomaly=False, score=0.0, method="lstm_autoencoder",
                error=str(e),
            )


# ── Ensemble facade ──────────────────────────────────────────────────────────

class MLAnomalyEnsemble:
    """
    Convenience wrapper holding one instance of each detector. Stateful per
    symbol so each asset gets its own model. Used by the Streamlit page to
    compute and display all three methods side-by-side, plus a simple
    majority-vote ensemble flag.
    """

    def __init__(self):
        self._detectors: dict[str, dict[str, object]] = {}

    def _get(self, symbol: str) -> dict[str, object]:
        if symbol not in self._detectors:
            self._detectors[symbol] = {
                "isolation_forest": IsolationForestDetector(),
                "prophet": ProphetDetector(),
                "lstm_autoencoder": LSTMAnomalyDetector(),
            }
        return self._detectors[symbol]

    def score_all(self, symbol: str, prices: list[float]) -> dict[str, AnomalyResult]:
        detectors = self._get(symbol)
        return {name: det.score(prices) for name, det in detectors.items()}

    @staticmethod
    def ensemble_vote(results: dict[str, AnomalyResult]) -> dict:
        usable = [r for r in results.values() if r.available and r.error is None]
        if not usable:
            return {"anomaly": False, "votes": 0, "of": 0, "avg_score": 0.0}
        votes = sum(1 for r in usable if r.is_anomaly)
        avg_score = float(np.mean([r.score for r in usable]))
        return {
            "anomaly": votes >= max(1, (len(usable) // 2) + 1) if len(usable) > 1 else votes >= 1,
            "votes": votes,
            "of": len(usable),
            "avg_score": avg_score,
        }


# Module-level singleton — keeps trained models warm across Streamlit reruns
_ensemble: Optional[MLAnomalyEnsemble] = None


def get_ml_ensemble() -> MLAnomalyEnsemble:
    global _ensemble
    if _ensemble is None:
        _ensemble = MLAnomalyEnsemble()
    return _ensemble
