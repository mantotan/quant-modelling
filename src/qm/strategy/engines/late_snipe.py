"""Late-bar snipe strategy — only trade after t=0.80 when model accuracy peaks.

Edge source: model accuracy is ~74% at t=0.80 (vs ~51% early bar).
Risk: fewer trades, but higher conviction per trade.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from qm.strategy.dutch.engine import DutchBarSummary, DutchInventory, DutchOrder
from qm.strategy.edge import compute_edge
from qm.strategy.sizing.kelly import KellySizer

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LateSnipeConfig:
    bar_budget: float = 200.0
    bar_seconds: float = 900.0
    order_size: float = 10.0           # bigger bets, fewer of them
    min_order_usd: float = 1.0

    min_time_pct: float = 0.80         # only trade after this
    prob_threshold: float = 0.55
    kelly_fraction: float = 0.35       # higher (model more accurate late)
    max_bet_pct: float = 0.15
    spread_offset: float = 0.01
    max_orders: int = 3                # limited orders in remaining time
    max_loss_pct: float = 0.30


class LateSnipeEngine:
    """Only trade in the last portion of bar when model is most accurate."""

    def __init__(self, config: LateSnipeConfig) -> None:
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
        self._committed_spend: float = 0.0

        self._orders_log: list[dict] = []
        self._decision_log: list[str] = []
        self._probs: list[float] = []

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
        self._committed_spend = 0.0
        self._orders_log = []
        self._decision_log = []
        self._probs = []
        self.flip_killed = False

    def on_tick(self, time_pct: float, cal_prob: float, book_up: object, book_dn: object) -> list[DutchOrder]:
        self._probs.append(cal_prob)

        # Core gate: only trade late in bar
        if time_pct < self._config.min_time_pct:
            return []

        # Order limit
        if self._order_count >= self._config.max_orders:
            return []

        # Determine side
        if cal_prob > self._config.prob_threshold:
            side = "UP"
        elif cal_prob < (1.0 - self._config.prob_threshold):
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

        # Budget
        budget_remaining = self._config.bar_budget - self._total_spent - self._committed_spend
        max_risk = self._config.bar_budget * self._config.max_loss_pct
        risk_remaining = max_risk - self._total_spent - self._committed_spend
        available = min(budget_remaining, risk_remaining)
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
            reason=f"snipe_{side.lower()}_t={time_pct:.2f}_edge={edge:.3f}",
            action="BUY",
        )

        self._order_count += 1
        self._committed_spend += bet_usd
        self._decision_log.append(
            f"SNIPE {side} {shares:.1f}sh @ {limit_price:.3f} t={time_pct:.2f} edge={edge:.3f}"
        )

        return [order]

    def on_fill(self, order: DutchOrder, fill_price: float, filled_shares: float) -> None:
        cost = filled_shares * fill_price
        if order.side == "UP":
            self._inventory.shares_up += filled_shares
            self._inventory.cost_up += cost
        else:
            self._inventory.shares_dn += filled_shares
            self._inventory.cost_dn += cost
        self._total_spent += cost
        self._committed_spend = max(0, self._committed_spend - order.dollars)

        self._orders_log.append({
            "side": order.side,
            "action": order.action,
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
                "unmatched_up": round(max(0, inv.net_shares_up - inv.net_shares_dn), 4),
                "unmatched_dn": round(max(0, inv.net_shares_dn - inv.net_shares_up), 4),
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
