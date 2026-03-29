"""Hybrid Dutch + Directional strategy.

Dutch accumulation early (t < switch_time) for cheap paired fills,
then switch to directional late (t > switch_time) when model is more accurate.

Combines bilateral safety with directional upside.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from qm.strategy.dutch.engine import (
    DutchAccumulationEngine,
    DutchBarSummary,
    DutchConfig,
    DutchInventory,
    DutchOrder,
)
from qm.strategy.edge import compute_edge
from qm.strategy.sizing.kelly import KellySizer

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HybridConfig:
    bar_budget: float = 200.0
    bar_seconds: float = 900.0
    order_size: float = 5.0
    min_order_usd: float = 1.0

    # Dutch phase
    max_marginal_pair_cost: float = 1.02
    spread_offset: float = 0.01

    # Switch point
    switch_time_pct: float = 0.70

    # Directional phase
    directional_prob_threshold: float = 0.55
    directional_kelly_fraction: float = 0.30
    directional_max_bet_pct: float = 0.15
    directional_max_orders: int = 5


class HybridEngine:
    """Dutch early, directional late. Shared inventory."""

    def __init__(self, config: HybridConfig) -> None:
        self._config = config

        # Build Dutch engine for early phase
        dutch_config = DutchConfig(
            bar_budget=config.bar_budget,
            bar_seconds=config.bar_seconds,
            order_size=config.order_size,
            min_order_usd=config.min_order_usd,
            max_marginal_pair_cost=config.max_marginal_pair_cost,
            spread_offset=config.spread_offset,
            risk_ceil=0.25,
            risk_t_start=0.05,
            max_onesided_cost=20.0,
            min_unmatched_shares=8.0,
            unmatched_ratio=0.20,
        )
        self._dutch = DutchAccumulationEngine(dutch_config)

        self._sizer = KellySizer(
            fraction=config.directional_kelly_fraction,
            max_bet_pct=config.directional_max_bet_pct,
            min_bet_usd=config.min_order_usd,
            max_bet_usd=config.order_size * 5,
        )

        self._bar_id: int = 0
        self._condition_id: str = ""
        self._window_start: str = ""
        self._window_end: str = ""

        self._directional_orders: int = 0
        self._directional_log: list[str] = []
        self._in_directional_phase: bool = False

        self.flip_killed: bool = False

    def set_bar_info(self, bar_id: int, condition_id: str, window_start: str, window_end: str) -> None:
        self._bar_id = bar_id
        self._condition_id = condition_id
        self._window_start = window_start
        self._window_end = window_end
        self._dutch.set_bar_info(bar_id, condition_id, window_start, window_end)

    def reset(self) -> None:
        self._dutch.reset()
        self._directional_orders = 0
        self._directional_log = []
        self._in_directional_phase = False
        self.flip_killed = False

    def on_tick(self, time_pct: float, cal_prob: float, book_up: object, book_dn: object) -> list[DutchOrder]:
        # Phase 1: Dutch accumulation
        if time_pct < self._config.switch_time_pct:
            self._in_directional_phase = False
            self.flip_killed = self._dutch.flip_killed
            return self._dutch.on_tick(time_pct, cal_prob, book_up, book_dn)

        # Phase 2: Directional
        self._in_directional_phase = True

        if self._directional_orders >= self._config.directional_max_orders:
            return []

        # Determine side
        if cal_prob > self._config.directional_prob_threshold:
            side = "UP"
        elif cal_prob < (1.0 - self._config.directional_prob_threshold):
            side = "DN"
        else:
            return []

        ask_up = getattr(book_up, "best_ask", 0.99)
        bid_up = getattr(book_up, "best_bid", 0.01)
        ask_dn = getattr(book_dn, "best_ask", 0.99)
        bid_dn = getattr(book_dn, "best_bid", 0.01)

        if ask_up <= 0.01 or ask_up >= 1.0 or ask_dn <= 0.01 or ask_dn >= 1.0:
            return []

        spread = (ask_up - bid_up + ask_dn - bid_dn) / 2
        market_prob_up = (bid_up + ask_up) / 2
        edge, _ = compute_edge(cal_prob, market_prob_up, spread)

        if edge <= 0:
            return []

        # Budget from Dutch phase's remaining
        inv = self._dutch._inventory  # noqa: SLF001
        spent = inv.total_cost
        available = self._config.bar_budget * 0.3 - (self._directional_orders * self._config.order_size)
        if available < self._config.min_order_usd:
            return []

        buy_book = book_up if side == "UP" else book_dn
        ask_price = getattr(buy_book, "best_ask", 0.99)
        bid_price = getattr(buy_book, "best_bid", 0.01)

        bet_usd = self._sizer.size(edge, ask_price, available)
        if bet_usd < self._config.min_order_usd:
            bet_usd = min(self._config.order_size, available)
            if bet_usd < self._config.min_order_usd:
                return []

        limit_price = min(bid_price + self._config.spread_offset, ask_price - 0.01)
        limit_price = max(limit_price, 0.01)
        shares = bet_usd / limit_price if limit_price > 0 else 0
        if shares <= 0:
            return []

        order = DutchOrder(
            side=side,
            limit_price=round(limit_price, 4),
            shares=round(shares, 4),
            dollars=round(bet_usd, 4),
            time_pct=time_pct,
            placed_at=datetime.now(UTC),
            reason=f"hybrid_dir_{side.lower()}_edge={edge:.3f}",
            action="BUY",
        )

        self._directional_orders += 1
        self._directional_log.append(
            f"DIR {side} {shares:.1f}sh @ {limit_price:.3f} t={time_pct:.2f}"
        )

        return [order]

    def on_fill(self, order: DutchOrder, fill_price: float, filled_shares: float) -> None:
        # All fills go through the Dutch engine's inventory tracker
        self._dutch.on_fill(order, fill_price, filled_shares)

    def on_order_cancelled(self, order: DutchOrder) -> None:
        self._dutch.on_order_cancelled(order)

    def resolve(self, outcome: str) -> DutchBarSummary:
        summary = self._dutch.resolve(outcome)
        # Append directional decisions to log
        summary.decision_log.extend(self._directional_log)
        return summary
