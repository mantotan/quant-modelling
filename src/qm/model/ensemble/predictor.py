"""Ensemble predictor: combines Sentinel (bar-level) + Pulse (intra-bar) models.

Sentinel predicts P(close >= open) from completed bar history.
Pulse predicts P(close >= open) from live tick data during the bar.

Critical design: Pulse shares 15 historical features with Sentinel.
Naive probability multiplication double-counts this shared signal.
The Bayesian update strategy extracts only the INCREMENTAL information
from Pulse's 8 tick features via a likelihood ratio that cancels
the shared component.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol, runtime_checkable

import lightgbm as lgb
import numpy as np

from qm.model.calibration.calibrator import IsotonicCalibrator

logger = logging.getLogger(__name__)


@runtime_checkable
class CombinationStrategy(Protocol):
    """Interface for combining Sentinel and Pulse predictions."""

    def combine(
        self,
        sentinel_prob: float,
        pulse_prob: float | None,
        time_elapsed_pct: float,
        market_prob: float,
    ) -> float:
        """Combine model predictions into a single probability.

        Args:
            sentinel_prob: Calibrated P(Up) from Sentinel (bar-level).
            pulse_prob: Calibrated P(Up) from Pulse (intra-bar), None if no ticks.
            time_elapsed_pct: Fraction of bar elapsed (0.0 to 1.0).
            market_prob: Market-implied P(Up) from Polymarket.

        Returns:
            Combined P(Up), clipped to [0.01, 0.99].
        """
        ...


class BayesianUpdateStrategy:
    """Sentinel sets prior, Pulse updates via incremental likelihood ratio.

    At bar start (t=0), combined = sentinel_prob (no tick evidence).
    As ticks arrive, Pulse refines the estimate. The incremental LR
    divides out the shared historical signal to avoid double-counting.

    The LR cancellation is approximate since both models learned
    different mappings from shared features. The ensemble calibrator
    absorbs residual miscalibration.
    """

    def __init__(self, ramp_pct: float = 0.10) -> None:
        self._ramp_pct = ramp_pct

    def combine(
        self,
        sentinel_prob: float,
        pulse_prob: float | None,
        time_elapsed_pct: float,
        market_prob: float,
    ) -> float:
        # No Pulse data -> return Sentinel prior
        if pulse_prob is None:
            return _clip(sentinel_prob)

        # Sentinel odds (prior)
        s = _clip(sentinel_prob)
        odds_s = s / (1.0 - s)

        # Pulse odds
        p = _clip(pulse_prob)
        odds_p = p / (1.0 - p)

        # Incremental LR: removes shared historical signal
        # If Pulse agrees with Sentinel exactly, lr = 1.0 (no update)
        lr = odds_p / odds_s

        # Time dampening: ramp from 0 to 1 over first ramp_pct of bar
        # At t=0, Pulse has no tick data, so its prediction is entirely
        # from shared historical features -> lr should be 1.0 (no update)
        alpha = min(time_elapsed_pct / self._ramp_pct, 1.0) if self._ramp_pct > 0 else 1.0
        lr_dampened = 1.0 + alpha * (lr - 1.0)

        # Posterior odds
        posterior_odds = odds_s * lr_dampened
        combined = posterior_odds / (1.0 + posterior_odds)

        return _clip(combined)


class TimeWeightedStrategy:
    """Simple time-dependent weighted average of Sentinel and Pulse.

    At bar start, weight is mostly Sentinel. As ticks accumulate,
    weight shifts toward Pulse. Sentinel always retains a minimum
    weight (default 20%) as a regularizer.

    Makes no independence assumption -- just interpolates.
    """

    def __init__(self, min_sentinel_weight: float = 0.20) -> None:
        self._min_w = min_sentinel_weight

    def combine(
        self,
        sentinel_prob: float,
        pulse_prob: float | None,
        time_elapsed_pct: float,
        market_prob: float,
    ) -> float:
        if pulse_prob is None:
            return _clip(sentinel_prob)

        # Sentinel weight decreases linearly with time, floored at min_w
        w = max(self._min_w, 1.0 - time_elapsed_pct)
        combined = w * sentinel_prob + (1.0 - w) * pulse_prob
        return _clip(combined)


class EnsemblePredictor:
    """Loads both Sentinel and Pulse models, combines predictions.

    Usage:
        predictor = EnsemblePredictor(
            sentinel_model_path=Path("data/models/BTC_5m_v3/model.txt"),
            sentinel_cal_path=Path("data/models/BTC_5m_v3/calibrator.pkl"),
            pulse_model_path=Path("data/models/pulse_v2/BTC_5m/model.lgb"),
            pulse_cal_path=Path("data/models/pulse_v2/BTC_5m/calibrator.pkl"),
        )
        # At bar start:
        sentinel_prob = predictor.predict_sentinel(bar_features)
        # During bar, on each tick:
        combined = predictor.predict_combined(sentinel_prob, pulse_features, t_pct, mkt)
    """

    def __init__(
        self,
        sentinel_model_path: Path,
        sentinel_cal_path: Path,
        pulse_model_path: Path,
        pulse_cal_path: Path,
        strategy: CombinationStrategy | None = None,
    ) -> None:
        # Load Sentinel
        self._sentinel = lgb.Booster(model_file=str(sentinel_model_path))
        self._sentinel_cal = IsotonicCalibrator()
        self._sentinel_cal.load(sentinel_cal_path)

        # Load Pulse
        self._pulse = lgb.Booster(model_file=str(pulse_model_path))
        self._pulse_cal = IsotonicCalibrator()
        self._pulse_cal.load(pulse_cal_path)

        self._strategy = strategy or BayesianUpdateStrategy()

        logger.info(
            "EnsemblePredictor loaded: sentinel=%s, pulse=%s, strategy=%s",
            sentinel_model_path.name,
            pulse_model_path.name,
            type(self._strategy).__name__,
        )

    def predict_sentinel(self, features: np.ndarray) -> float:
        """Predict bar-level P(Up). Called once per bar completion."""
        raw = self._sentinel.predict(features.reshape(1, -1))[0]
        return float(self._sentinel_cal.transform(np.array([raw]))[0])

    def predict_pulse(self, features: np.ndarray) -> float:
        """Predict intra-bar P(Up). Called on each tick snapshot."""
        raw = self._pulse.predict(features.reshape(1, -1))[0]
        return float(self._pulse_cal.transform(np.array([raw]))[0])

    def predict_combined(
        self,
        sentinel_prob: float,
        pulse_features: np.ndarray | None,
        time_elapsed_pct: float,
        market_prob: float,
    ) -> float:
        """Combined prediction. Sentinel prob is cached; Pulse computed live.

        Args:
            sentinel_prob: Pre-computed Sentinel P(Up) for this bar.
            pulse_features: Pulse feature vector, None if no ticks yet.
            time_elapsed_pct: Fraction of bar elapsed (0.0 to 1.0).
            market_prob: Market-implied P(Up).

        Returns:
            Combined P(Up).
        """
        pulse_prob = None
        if pulse_features is not None:
            pulse_prob = self.predict_pulse(pulse_features)
        return self._strategy.combine(
            sentinel_prob, pulse_prob, time_elapsed_pct, market_prob,
        )

    def predict_combined_from_probs(
        self,
        sentinel_prob: float,
        pulse_prob: float | None,
        time_elapsed_pct: float,
        market_prob: float,
    ) -> float:
        """Combined prediction from pre-computed probabilities (for backtesting)."""
        return self._strategy.combine(
            sentinel_prob, pulse_prob, time_elapsed_pct, market_prob,
        )

    @property
    def strategy(self) -> CombinationStrategy:
        return self._strategy

    @strategy.setter
    def strategy(self, value: CombinationStrategy) -> None:
        self._strategy = value


def combine_predictions_batch(
    sentinel_probs: np.ndarray,
    pulse_probs: np.ndarray,
    time_pcts: np.ndarray,
    bar_indices: np.ndarray,
    market_probs: np.ndarray,
    strategy: CombinationStrategy,
) -> np.ndarray:
    """Vectorized batch combination for backtesting.

    Args:
        sentinel_probs: (n_bars,) calibrated Sentinel predictions.
        pulse_probs: (n_samples,) calibrated Pulse predictions.
        time_pcts: (n_samples,) elapsed fraction per sample.
        bar_indices: (n_samples,) bar index for each sample.
        market_probs: (n_samples,) market odds per sample.
        strategy: Combination strategy to use.

    Returns:
        (n_samples,) combined predictions.
    """
    n_samples = len(pulse_probs)
    combined = np.empty(n_samples, dtype=np.float64)

    for i in range(n_samples):
        bar_idx = bar_indices[i]
        s_prob = float(sentinel_probs[bar_idx]) if bar_idx < len(sentinel_probs) else 0.5
        combined[i] = strategy.combine(
            s_prob, float(pulse_probs[i]),
            float(time_pcts[i]), float(market_probs[i]),
        )

    return combined


def _clip(prob: float, lo: float = 0.01, hi: float = 0.99) -> float:
    """Clip probability to avoid log(0) in odds computation."""
    if prob < lo:
        return lo
    if prob > hi:
        return hi
    return prob
