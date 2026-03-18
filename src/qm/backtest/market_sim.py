"""Simulates Polymarket odds evolution during a bar.

Uses Black-Scholes binary option pricing: a market maker prices
P(close >= open) using current distance from open, implied volatility,
and time remaining.

At t=0: distance=0, z=0, Phi(0)=0.50 (maximum uncertainty)
At t=295s: huge z, market_prob near 0 or 1 (converged)
"""

from __future__ import annotations

import math

import numpy as np

from qm.core.constants import TIMEFRAME_MINUTES
from qm.core.types import Timeframe


def _norm_cdf_scalar(z: float) -> float:
    """Normal CDF via math.erfc. <0.01ms for single value."""
    return 0.5 * math.erfc(-z / math.sqrt(2))


class MarketOddsSimulator:
    """Simulates Polymarket odds evolution during a bar.

    Args:
        efficiency: How closely market tracks theoretical fair value.
            0.0 = market always stays at 0.50 (completely uninformed).
            0.3 = market incorporates 30% of fair value (thin 5m markets).
            1.0 = perfectly efficient (no edge possible).
        timeframe: Bar timeframe for total_seconds calculation.
    """

    def __init__(
        self,
        efficiency: float = 0.75,
        timeframe: Timeframe = Timeframe.M5,
    ) -> None:
        if not 0.0 <= efficiency <= 1.0:
            msg = f"efficiency must be in [0, 1], got {efficiency}"
            raise ValueError(msg)
        self.efficiency = efficiency
        self.total_seconds = float(TIMEFRAME_MINUTES[timeframe] * 60)

    def market_prob(
        self,
        open_price: float,
        current_price: float,
        realized_vol: float,
        elapsed_seconds: float,
    ) -> float:
        """Compute simulated market P(close >= open) at a point within the bar.

        Uses Black-Scholes binary option pricing with efficiency parameter.

        Args:
            open_price: Bar open price.
            current_price: Current (partial) price.
            realized_vol: Recent realized volatility (e.g. 10-bar std of log returns).
            elapsed_seconds: Seconds since bar opened.

        Returns:
            Simulated market probability, clamped to [0.02, 0.98].
        """
        distance = (current_price - open_price) / (open_price + 1e-10)
        time_remaining_frac = max(
            (self.total_seconds - elapsed_seconds) / self.total_seconds, 1e-6
        )
        sigma_remaining = realized_vol * math.sqrt(time_remaining_frac) + 1e-10
        z = distance / sigma_remaining
        raw = _norm_cdf_scalar(z)
        blended = 0.5 + self.efficiency * (raw - 0.5)
        return max(0.02, min(0.98, blended))

    def market_prob_batch(
        self,
        opens: np.ndarray,
        currents: np.ndarray,
        vols: np.ndarray,
        elapsed: np.ndarray,
    ) -> np.ndarray:
        """Vectorized version for backtest speed.

        Args:
            opens: Bar open prices, shape (n,).
            currents: Current prices at each snapshot, shape (n,).
            vols: Realized volatilities, shape (n,).
            elapsed: Elapsed seconds at each snapshot, shape (n,).

        Returns:
            Simulated market probabilities, shape (n,), clamped to [0.02, 0.98].
        """
        distance = (currents - opens) / (opens + 1e-10)
        time_remaining_frac = np.clip(
            (self.total_seconds - elapsed) / self.total_seconds, 1e-6, 1.0
        )
        sigma_remaining = vols * np.sqrt(time_remaining_frac) + 1e-10
        z = distance / sigma_remaining
        # Vectorized norm CDF via erfc
        raw = 0.5 * _erfc_batch(-z / math.sqrt(2))
        blended = 0.5 + self.efficiency * (raw - 0.5)
        return np.clip(blended, 0.02, 0.98)


def _erfc_batch(x: np.ndarray) -> np.ndarray:
    """Vectorized complementary error function using scipy (batch-safe)."""
    from scipy.special import erfc

    return erfc(x)
