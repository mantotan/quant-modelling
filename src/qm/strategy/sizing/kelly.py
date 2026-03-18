"""Fractional Kelly criterion for Polymarket bet sizing.

For binary Polymarket markets:
- We pay `price` per share to win $1 if correct
- Kelly fraction f* = (p*b - q) / b where:
    p = model probability of winning
    b = net odds = (1/price) - 1
    q = 1 - p

Simplified: f* = edge / (1 - price)

We use fractional Kelly (default 0.25x) because:
1. Model probabilities have estimation error
2. Market microstructure costs erode edge
3. Drawdown tolerance is finite
"""

from __future__ import annotations


class KellySizer:
    """Fractional Kelly position sizing for Polymarket bets.

    Args:
        fraction: Kelly fraction (0.25 = quarter Kelly).
        max_bet_pct: Maximum bet as fraction of bankroll.
        min_bet_usd: Minimum bet in USDC (below this, skip).
        max_bet_usd: Maximum bet in USDC per trade.
    """

    def __init__(
        self,
        fraction: float = 0.25,
        max_bet_pct: float = 0.05,
        min_bet_usd: float = 5.0,
        max_bet_usd: float = 500.0,
    ) -> None:
        self.fraction = fraction
        self.max_bet_pct = max_bet_pct
        self.min_bet_usd = min_bet_usd
        self.max_bet_usd = max_bet_usd

    def size(self, edge: float, market_price: float, bankroll: float) -> float:
        """Calculate bet size in USDC.

        Args:
            edge: model_prob - market_prob (after spread), positive = we have edge
            market_price: price we'd pay per share (the Polymarket probability)
            bankroll: current available bankroll in USDC

        Returns:
            Bet size in USDC. Returns 0.0 if bet is below minimum.
        """
        if edge <= 0 or bankroll <= 0:
            return 0.0

        if market_price <= 0.01 or market_price >= 0.99:
            return 0.0

        # Kelly fraction: edge / (1 - market_price)
        kelly_f = edge / (1 - market_price)
        fractional = kelly_f * self.fraction

        # Cap at max percentage of bankroll
        max_by_pct = bankroll * self.max_bet_pct
        bet_usd = min(fractional * bankroll, max_by_pct, self.max_bet_usd)
        bet_usd = max(bet_usd, 0.0)

        if bet_usd < self.min_bet_usd:
            return 0.0

        return round(bet_usd, 2)

    def size_multiple(
        self,
        edges: list[float],
        market_prices: list[float],
        bankroll: float,
    ) -> list[float]:
        """Size multiple concurrent bets, respecting total exposure."""
        sizes = []
        remaining = bankroll
        for edge, price in zip(edges, market_prices):
            sz = self.size(edge, price, remaining)
            sizes.append(sz)
            remaining -= sz
        return sizes
