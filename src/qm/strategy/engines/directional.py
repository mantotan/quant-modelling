"""Directional strategy engine — buy only the model-favored side.

Covers both Pure Directional (magnitude_threshold=0) and
Selective Directional (magnitude_threshold>0).

Edge source: model accuracy > breakeven rate (ask_price).
Risk: 100% loss on wrong calls, mitigated by Kelly sizing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from qm.strategy.dutch.engine import DutchBarSummary, DutchInventory, DutchOrder
from qm.strategy.edge import compute_edge
from qm.strategy.sizing.kelly import KellySizer

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DirectionalConfig:
    bar_budget: float = 200.0
    bar_seconds: float = 900.0
    order_size: float = 5.0
    min_order_usd: float = 1.0

    # Directional thresholds
    prob_threshold: float = 0.55        # buy UP when cal_prob > this
    magnitude_threshold: float = 0.0    # 0 = disabled, 0.08 = selective mode

    # Sizing
    kelly_fraction: float = 0.25
    max_bet_pct: float = 0.10

    # Price
    spread_offset: float = 0.01

    # Behavior
    allow_early_exit: bool = True       # sell if conviction flips
    max_orders_per_bar: int = 20
    min_time_between_orders: float = 0.03  # min time_pct gap between orders

    # Risk
    max_loss_pct: float = 0.25         # max % of budget at risk


class DirectionalEngine:
    """Buy only the model-favored side. Optionally exit on conviction flip."""

    def __init__(self, config: DirectionalConfig) -> None:
        self._config = config
        self._inventory = DutchInventory()
        self._sizer = KellySizer(
            fraction=config.kelly_fraction,
            max_bet_pct=config.max_bet_pct,
            min_bet_usd=config.min_order_usd,
            max_bet_usd=config.order_size * 5,
        )

        self._bar_id: int = 0
        self._condition_id: str = ""
        self._window_start: str = ""
        self._window_end: str = ""

        self._order_count: int = 0
        self._total_spent: float = 0.0
        self._last_order_time: float = -1.0
        self._current_side: str | None = None
        self._committed_spend: float = 0.0

        self._orders_log: list[dict] = []
        self._decision_log: list[str] = []
        self._probs: list[float] = []

        # Event callback (for logging compatibility)
        self._on_event: object = None
        self.flip_killed: bool = False

    def set_bar_info(self, bar_id: int, condition_id: str, window_start: str, window_end: str) -> None:
        self._bar_id = bar_id
        self._condition_id = condition_id
        self._window_start = window_start
        self._window_end = window_end

    def reset(self) -> None:
        self._inventory = DutchInventory()
        self._order_count = 0
        self._total_spent = 0.0
        self._last_order_time = -1.0
        self._current_side = None
        self._committed_spend = 0.0
        self._orders_log = []
        self._decision_log = []
        self._probs = []
        self.flip_killed = False

    def on_tick(self, time_pct: float, cal_prob: float, book_up: object, book_dn: object) -> list[DutchOrder]:
        self._probs.append(cal_prob)
        orders: list[DutchOrder] = []

        # Magnitude filter (selective mode)
        magnitude = abs(cal_prob - 0.5)
        if magnitude < self._config.magnitude_threshold:
            return orders

        # Determine favored side
        if cal_prob > self._config.prob_threshold:
            favored = "UP"
        elif cal_prob < (1.0 - self._config.prob_threshold):
            favored = "DN"
        else:
            return orders  # model not confident enough

        # Get book prices
        ask_up = getattr(book_up, "best_ask", 0.99)
        bid_up = getattr(book_up, "best_bid", 0.01)
        ask_dn = getattr(book_dn, "best_ask", 0.99)
        bid_dn = getattr(book_dn, "best_bid", 0.01)

        # Book health check
        if ask_up <= 0.01 or ask_up >= 1.0 or ask_dn <= 0.01 or ask_dn >= 1.0:
            return orders

        # Compute edge
        spread = (ask_up - bid_up + ask_dn - bid_dn) / 2
        market_prob_up = (bid_up + ask_up) / 2  # mid price ≈ implied prob
        edge, _ = compute_edge(cal_prob, market_prob_up, spread)

        if edge <= 0:
            return orders

        # Budget check
        budget_remaining = self._config.bar_budget - self._total_spent - self._committed_spend
        max_risk = self._config.bar_budget * self._config.max_loss_pct
        risk_remaining = max_risk - self._total_spent - self._committed_spend
        available = min(budget_remaining, risk_remaining)
        if available < self._config.min_order_usd:
            return orders

        # Order limit
        if self._order_count >= self._config.max_orders_per_bar:
            return orders

        # Spacing
        if time_pct - self._last_order_time < self._config.min_time_between_orders:
            return orders

        # Early exit: sell opposite side if conviction flipped
        if self._config.allow_early_exit and self._current_side and self._current_side != favored:
            sell_side = self._current_side
            sell_book = book_up if sell_side == "UP" else book_dn
            sell_bid = getattr(sell_book, "best_bid", 0.01)
            sell_shares = (
                self._inventory.net_shares_up if sell_side == "UP"
                else self._inventory.net_shares_dn
            )
            if sell_shares > 0 and sell_bid > 0.01:
                sell_dollars = sell_shares * sell_bid
                sell_order = DutchOrder(
                    side=sell_side,
                    limit_price=sell_bid,
                    shares=round(sell_shares, 4),
                    dollars=round(sell_dollars, 4),
                    time_pct=time_pct,
                    placed_at=datetime.now(UTC),
                    reason=f"exit_flip_{sell_side.lower()}",
                    action="SELL",
                )
                orders.append(sell_order)
                self._decision_log.append(
                    f"SELL {sell_side} {sell_shares:.1f}sh @ {sell_bid:.3f} (flip to {favored})"
                )

        # Size the buy
        buy_book = book_up if favored == "UP" else book_dn
        ask_price = getattr(buy_book, "best_ask", 0.99)
        bid_price = getattr(buy_book, "best_bid", 0.01)

        # Kelly sizing
        bet_usd = self._sizer.size(edge, ask_price, available)
        if bet_usd < self._config.min_order_usd:
            # Fall back to fixed order_size
            bet_usd = min(self._config.order_size, available)
            if bet_usd < self._config.min_order_usd:
                return orders

        # Limit price: bid + offset (maker order)
        limit_price = min(bid_price + self._config.spread_offset, ask_price - 0.01)
        limit_price = max(limit_price, 0.01)

        shares = bet_usd / limit_price if limit_price > 0 else 0
        if shares <= 0:
            return orders

        buy_order = DutchOrder(
            side=favored,
            limit_price=round(limit_price, 4),
            shares=round(shares, 4),
            dollars=round(bet_usd, 4),
            time_pct=time_pct,
            placed_at=datetime.now(UTC),
            reason=f"directional_{favored.lower()}_edge={edge:.3f}",
            action="BUY",
        )
        orders.append(buy_order)

        self._order_count += 1
        self._committed_spend += bet_usd
        self._last_order_time = time_pct
        self._current_side = favored

        self._decision_log.append(
            f"BUY {favored} {shares:.1f}sh @ {limit_price:.3f} edge={edge:.3f} cal={cal_prob:.3f}"
        )

        return orders

    def on_fill(self, order: DutchOrder, fill_price: float, filled_shares: float) -> None:
        cost = filled_shares * fill_price
        if order.action == "BUY":
            if order.side == "UP":
                self._inventory.shares_up += filled_shares
                self._inventory.cost_up += cost
            else:
                self._inventory.shares_dn += filled_shares
                self._inventory.cost_dn += cost
            self._total_spent += cost
            self._committed_spend = max(0, self._committed_spend - order.dollars)
        elif order.action == "SELL":
            if order.side == "UP":
                self._inventory.sold_shares_up += filled_shares
                self._inventory.sell_revenue_up += cost
            else:
                self._inventory.sold_shares_dn += filled_shares
                self._inventory.sell_revenue_dn += cost

        self._orders_log.append({
            "side": order.side,
            "action": order.action,
            "limit_price": order.limit_price,
            "fill_price": fill_price,
            "shares": filled_shares,
            "dollars": round(cost, 4),
            "time_pct": order.time_pct,
            "reason": order.reason,
        })

    def on_order_cancelled(self, order: DutchOrder) -> None:
        self._committed_spend = max(0, self._committed_spend - order.dollars)

    def resolve(self, outcome: str) -> DutchBarSummary:
        inv = self._inventory
        unmatched_up = max(0, inv.net_shares_up - inv.net_shares_dn)
        unmatched_dn = max(0, inv.net_shares_dn - inv.net_shares_up)

        summary = DutchBarSummary(
            bar_id=self._bar_id,
            window_start=self._window_start,
            window_end=self._window_end,
            condition_id=self._condition_id,
            orders=self._orders_log,
            inventory={
                "up_shares": round(inv.net_shares_up, 4),
                "dn_shares": round(inv.net_shares_dn, 4),
                "matched": round(inv.matched, 4),
                "unmatched_up": round(unmatched_up, 4),
                "unmatched_dn": round(unmatched_dn, 4),
                "sold_up": round(inv.sold_shares_up, 4),
                "sold_dn": round(inv.sold_shares_dn, 4),
            },
            cost={
                "total": round(inv.total_cost, 4),
                "cost_up": round(inv.net_cost_up, 4),
                "cost_dn": round(inv.net_cost_dn, 4),
                "avg_pair_cost": round(inv.avg_pair_cost, 4),
            },
            model_stats={
                "avg_prob": round(sum(self._probs) / len(self._probs), 4) if self._probs else 0.5,
                "predictions_count": len(self._probs),
            },
            fill_stats={
                "orders_placed": self._order_count,
                "orders_filled": len(self._orders_log),
            },
            decision_log=self._decision_log,
        )

        if outcome:
            summary.compute_pnl(outcome)

        return summary
