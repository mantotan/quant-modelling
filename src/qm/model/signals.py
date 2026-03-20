"""Signal generation: converts calibrated model probabilities into trading signals.

Compares calibrated P(Up) against Polymarket market-implied P(Up).
Only generates a signal when edge exceeds minimum threshold after spread.
"""

from __future__ import annotations

import logging
from datetime import datetime

import numpy as np

from qm.core.types import Asset, MarketType, Outcome, Signal

logger = logging.getLogger(__name__)


class SignalGenerator:
    """Generates trading signals by comparing model vs market probabilities.

    For binary Polymarket markets:
    - edge_up = cal_prob - market_prob - spread/2
    - edge_down = (1 - cal_prob) - (1 - market_prob) - spread/2 = market_prob - cal_prob - spread/2
    - Trade the side with the larger edge, if it exceeds min_edge.
    """

    def __init__(
        self,
        min_edge: float = 0.05,
        min_confidence: float = 0.02,
    ) -> None:
        self.min_edge = min_edge
        self.min_confidence = min_confidence

    def generate(
        self,
        timestamp: datetime,
        asset: Asset,
        market_type: MarketType,
        model_prob_up: float,
        market_prob_up: float,
        market_spread: float,
    ) -> Signal | None:
        """Generate a signal for a specific Polymarket market.

        Args:
            timestamp: Current bar timestamp.
            asset: Asset being predicted.
            market_type: Polymarket market type (5m, 15m, etc.)
            model_prob_up: Calibrated P(Up) from model.
            market_prob_up: Polymarket implied P(Up) (mid price).
            market_spread: Polymarket bid-ask spread.

        Returns:
            Signal if actionable edge found, None otherwise.
        """
        # Edge for each side (after half-spread cost)
        half_spread = market_spread / 2
        edge_up = model_prob_up - market_prob_up - half_spread
        edge_down = market_prob_up - model_prob_up - half_spread

        # Pick best side
        if edge_up > edge_down:
            edge = edge_up
            side = Outcome.UP
        else:
            edge = edge_down
            side = Outcome.DOWN

        # Filter: minimum edge threshold
        if edge < self.min_edge:
            return None

        # Confidence = how far from 50% the model is (higher = more certain)
        confidence = abs(model_prob_up - 0.5) * 2  # 0 at 50%, 1 at 0% or 100%

        if confidence < self.min_confidence:
            return None

        return Signal(
            timestamp=timestamp,
            asset=asset,
            market_type=market_type,
            model_prob_up=model_prob_up,
            market_prob_up=market_prob_up,
            edge=edge,
            confidence=confidence,
            recommended_side=side,
            recommended_size=0.0,  # filled in by Kelly sizer
        )

    def check_model_agreement(
        self,
        sentinel_prob: float,
        pulse_prob: float,
        time_elapsed_pct: float,
    ) -> tuple[bool, float]:
        """Check if Sentinel and Pulse agree enough to trust the ensemble.

        At early bar (t~0), Pulse has no tick data, so disagreement is
        expected and allowed. At late bar (t~0.80), both models have
        strong evidence, so less disagreement is tolerated.

        Args:
            sentinel_prob: Calibrated P(Up) from Sentinel.
            pulse_prob: Calibrated P(Up) from Pulse.
            time_elapsed_pct: Fraction of bar elapsed (0.0 to 1.0).

        Returns:
            (ok, disagreement): ok=True if trade should proceed.
        """
        disagreement = abs(sentinel_prob - pulse_prob)
        # Linear ramp: 0.40 at t=0 -> 0.15 at t=0.80
        max_allowed = max(0.15, 0.40 - 0.3125 * time_elapsed_pct)
        return disagreement <= max_allowed, disagreement

    def generate_batch(
        self,
        timestamps: np.ndarray,
        asset: Asset,
        market_type: MarketType,
        model_probs: np.ndarray,
        market_probs: np.ndarray,
        spreads: np.ndarray | float = 0.02,
    ) -> list[Signal]:
        """Generate signals for a batch of predictions."""
        if isinstance(spreads, (int, float)):
            spreads_arr = np.full(len(model_probs), spreads)
        else:
            spreads_arr = spreads

        signals: list[Signal] = []
        for i in range(len(model_probs)):
            sig = self.generate(
                timestamp=timestamps[i],
                asset=asset,
                market_type=market_type,
                model_prob_up=float(model_probs[i]),
                market_prob_up=float(market_probs[i]),
                market_spread=float(spreads_arr[i]),
            )
            if sig is not None:
                signals.append(sig)

        return signals
