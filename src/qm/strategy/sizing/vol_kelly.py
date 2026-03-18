"""Vol-scaled fractional Kelly position sizing.

Extends the base KellySizer to dynamically adjust the Kelly fraction
based on realised volatility. In high-vol regimes, positions are
reduced to limit drawdown. In low-vol regimes, positions are increased
to capitalise on calmer conditions.

    effective_fraction = fraction * clip(median_vol / realized_vol, min_scale, max_scale)

This ensures:
- Crisis (vol 3× median) → fraction × 0.33 → much smaller bets
- Low vol (vol 0.5× median) → fraction × 2.0 → larger bets
- Normal vol → fraction × 1.0 → unchanged

The median_vol is updated via ``update_vol()`` as new bars arrive.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class VolScaledKellySizer:
    """Fractional Kelly with vol-scaling for regime-adaptive sizing.

    Args:
        base_fraction: Baseline Kelly fraction (e.g., 0.25 = quarter Kelly).
        max_bet_pct: Maximum bet as fraction of bankroll.
        min_bet_usd: Minimum bet in USDC (below this, skip).
        max_bet_usd: Maximum bet in USDC per trade.
        min_scale: Floor for the vol scaling factor.
        max_scale: Ceiling for the vol scaling factor.
        median_vol: Initial estimate of median volatility. Updated
            as new data arrives via ``update_vol()``.
    """

    def __init__(
        self,
        base_fraction: float = 0.25,
        max_bet_pct: float = 0.05,
        min_bet_usd: float = 5.0,
        max_bet_usd: float = 500.0,
        min_scale: float = 0.25,
        max_scale: float = 2.0,
        median_vol: float = 0.02,
    ) -> None:
        self.base_fraction = base_fraction
        self.max_bet_pct = max_bet_pct
        self.min_bet_usd = min_bet_usd
        self.max_bet_usd = max_bet_usd
        self.min_scale = min_scale
        self.max_scale = max_scale
        self._median_vol = median_vol
        self._current_vol: float | None = None

    @property
    def median_vol(self) -> float:
        """Current median volatility estimate."""
        return self._median_vol

    @property
    def current_vol(self) -> float | None:
        """Most recent realised volatility, or None if not set."""
        return self._current_vol

    def update_vol(self, realized_vol: float, median_vol: float | None = None) -> None:
        """Update the current and optionally the median volatility.

        Called when new bar data arrives with fresh vol estimates.

        Args:
            realized_vol: Current realised volatility (e.g., realized_vol_10).
            median_vol: Updated median vol estimate. If None, keeps previous.
        """
        self._current_vol = realized_vol
        if median_vol is not None:
            self._median_vol = median_vol

    def vol_scale_factor(self) -> float:
        """Compute the vol scaling factor.

        Returns:
            Factor in [min_scale, max_scale]. Returns 1.0 if no vol data.
        """
        if self._current_vol is None or self._current_vol <= 0:
            return 1.0
        if self._median_vol <= 0:
            return 1.0
        raw = self._median_vol / self._current_vol
        return max(self.min_scale, min(raw, self.max_scale))

    def effective_fraction(self) -> float:
        """Kelly fraction after vol scaling."""
        return self.base_fraction * self.vol_scale_factor()

    def size(self, edge: float, market_price: float, bankroll: float) -> float:
        """Calculate vol-adjusted bet size in USDC.

        Args:
            edge: model_prob - market_prob (after spread), positive = edge.
            market_price: Price per share on Polymarket.
            bankroll: Current available bankroll in USDC.

        Returns:
            Bet size in USDC. Returns 0.0 if below minimum.
        """
        if edge <= 0 or bankroll <= 0:
            return 0.0
        if market_price <= 0.01 or market_price >= 0.99:
            return 0.0

        # Kelly fraction: edge / (1 - market_price), scaled by vol
        kelly_f = edge / (1 - market_price)
        fractional = kelly_f * self.effective_fraction()

        # Cap at max percentage of bankroll
        max_by_pct = bankroll * self.max_bet_pct
        bet_usd = min(fractional * bankroll, max_by_pct, self.max_bet_usd)
        bet_usd = max(bet_usd, 0.0)

        if bet_usd < self.min_bet_usd:
            return 0.0

        return round(bet_usd, 2)
