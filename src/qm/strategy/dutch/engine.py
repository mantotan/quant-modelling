"""Dutch accumulation engine — buy both sides throughout a bar.

Core state machine that tracks one bar's lifecycle:
  - Holds bilateral inventory (shares_up, shares_dn, cost_up, cost_dn)
  - Decides when to buy each side based on model + market data
  - Resolves at bar end to compute matched-pair PnL

The engine is pure logic — no I/O, no async. It receives TokenBook
snapshots and returns DutchOrder decisions. The fill simulator and
monitor handle the rest.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DutchConfig:
    """Configuration for dutch accumulation strategy."""

    bar_budget: float = 50.0
    order_size: float = 10.0
    cheap_threshold: float = 0.02
    max_pair_cost: float = 0.97
    min_time_remaining: float = 30.0
    emergency_balance_time: float = 120.0
    spread_offset: float = 0.01
    bar_seconds: float = 900.0
    cooldown_s: float = 5.0


@dataclass(frozen=True, slots=True)
class DutchOrder:
    """A limit order decision from the engine."""

    side: str
    limit_price: float
    shares: float
    dollars: float
    time_pct: float
    placed_at: datetime
    reason: str


@dataclass
class DutchInventory:
    """Bilateral inventory tracker — shares and cost for both sides."""

    shares_up: float = 0.0
    shares_dn: float = 0.0
    cost_up: float = 0.0
    cost_dn: float = 0.0

    @property
    def matched(self) -> float:
        return min(self.shares_up, self.shares_dn)

    @property
    def total_cost(self) -> float:
        return self.cost_up + self.cost_dn

    @property
    def avg_pair_cost(self) -> float:
        """Average cost per matched pair. < 1.0 = guaranteed profit."""
        m = self.matched
        if m <= 0:
            return 1.0
        frac_up = m / self.shares_up if self.shares_up > 0 else 0.0
        frac_dn = m / self.shares_dn if self.shares_dn > 0 else 0.0
        return (self.cost_up * frac_up + self.cost_dn * frac_dn) / m

    @property
    def imbalance(self) -> float:
        """Positive = more UP than DN."""
        return self.shares_up - self.shares_dn


@dataclass
class DutchBarSummary:
    """Per-bar summary designed for AI review."""

    bar_id: int = 0
    window_start: str = ""
    window_end: str = ""
    condition_id: str = ""
    outcome: str | None = None
    orders: list[dict] = field(default_factory=list)
    inventory: dict = field(default_factory=dict)
    cost: dict = field(default_factory=dict)
    pnl: dict = field(default_factory=dict)
    market_stats: dict = field(default_factory=dict)
    model_stats: dict = field(default_factory=dict)
    fill_stats: dict = field(default_factory=dict)
    decision_log: list[str] = field(default_factory=list)

    def compute_pnl(self, outcome: str) -> None:
        """Compute PnL once outcome is known."""
        self.outcome = outcome
        inv = self.inventory
        matched = inv.get("matched", 0)
        unmatched_up = inv.get("unmatched_up", 0)
        unmatched_dn = inv.get("unmatched_dn", 0)
        total_cost = self.cost.get("total", 0)

        # Matched pairs always pay $1 per pair
        matched_payout = matched * 1.0

        # Unmatched shares: pay $1 if their side wins, $0 otherwise
        if outcome == "UP":
            unmatched_payout = unmatched_up * 1.0
        else:
            unmatched_payout = unmatched_dn * 1.0

        payout = matched_payout + unmatched_payout
        profit = payout - total_cost
        roi = (profit / total_cost * 100) if total_cost > 0 else 0.0

        self.pnl = {
            "payout": round(payout, 4),
            "profit": round(profit, 4),
            "roi_pct": round(roi, 2),
            "matched_payout": round(matched_payout, 4),
            "unmatched_payout": round(unmatched_payout, 4),
        }

    def to_dict(self) -> dict:
        return {
            "bar_id": self.bar_id,
            "window_start": self.window_start,
            "window_end": self.window_end,
            "condition_id": self.condition_id,
            "outcome": self.outcome,
            "orders": self.orders,
            "inventory": self.inventory,
            "cost": self.cost,
            "pnl": self.pnl,
            "market_stats": self.market_stats,
            "model_stats": self.model_stats,
            "fill_stats": self.fill_stats,
            "decision_log": self.decision_log,
        }


class DutchAccumulationEngine:
    """Core engine: decides when to buy each side, tracks inventory."""

    def __init__(self, config: DutchConfig) -> None:
        self._config = config
        self._inventory = DutchInventory()
        self._orders: list[dict] = []
        self._decision_log: list[str] = []
        self._last_order_time: dict[str, float] = {"UP": -999.0, "DN": -999.0}
        self._model_probs: list[float] = []
        self._mid_range_up: list[float] = []
        self._spreads_up: list[float] = []
        self._spreads_dn: list[float] = []
        self._bar_id: int = 0
        self._condition_id: str = ""
        self._window_start: str = ""
        self._window_end: str = ""
        self._stopped = False

    def set_bar_info(
        self,
        bar_id: int,
        condition_id: str = "",
        window_start: str = "",
        window_end: str = "",
    ) -> None:
        """Set metadata for the current bar."""
        self._bar_id = bar_id
        self._condition_id = condition_id
        self._window_start = window_start
        self._window_end = window_end

    def on_tick(
        self,
        time_pct: float,
        cal_prob: float,
        book_up,
        book_dn,
    ) -> list[DutchOrder]:
        """Core decision logic. Called every ~1s with current state.

        Returns 0, 1, or 2 DutchOrder objects to place.
        book_up/book_dn are TokenBook | None.
        """
        if self._stopped:
            return []

        # Track model stats
        self._model_probs.append(cal_prob)

        # Guard: need both books
        if book_up is None or book_dn is None:
            return []

        # Track market stats
        mid_up = book_up.mid
        self._mid_range_up.append(mid_up)
        self._spreads_up.append(book_up.spread)
        self._spreads_dn.append(book_dn.spread)

        # Kill switch: avg pair cost too high
        if (
            self._inventory.matched > 0
            and self._inventory.avg_pair_cost > self._config.max_pair_cost
        ):
            if not self._stopped:
                self._decision_log.append(
                    f"t={time_pct:.2f}: KILL avg_pair_cost="
                    f"{self._inventory.avg_pair_cost:.4f} > {self._config.max_pair_cost}"
                )
                self._stopped = True
            return []

        # Budget check
        budget_remaining = self._config.bar_budget - self._inventory.total_cost
        if budget_remaining < self._config.order_size * 0.5:
            return []

        remaining_s = (1.0 - time_pct) * self._config.bar_seconds
        orders: list[DutchOrder] = []

        for side in ("UP", "DN"):
            if side == "UP":
                ask = book_up.best_ask
                bid = book_up.best_bid
                model_fair = cal_prob
                my_shares = self._inventory.shares_up
                other_shares = self._inventory.shares_dn
            else:
                ask = book_dn.best_ask
                bid = book_dn.best_bid
                model_fair = 1.0 - cal_prob
                my_shares = self._inventory.shares_dn
                other_shares = self._inventory.shares_up

            # Skip if book is empty (ask=1.0, bid=0.0 = no real data)
            if bid <= 0.0 or ask >= 1.0:
                continue

            cheap_score = model_fair - ask
            need_this_side = other_shares - my_shares  # positive = need

            # Cooldown check
            elapsed_s = time_pct * self._config.bar_seconds
            last_s = self._last_order_time[side] * self._config.bar_seconds
            if elapsed_s - last_s < self._config.cooldown_s:
                continue

            # Time-adaptive threshold: patient early, aggressive late
            # Ramps from 1.0 at t=0 to 0.5 at t=0.85
            time_factor = max(0.5, 1.0 - 0.588 * min(time_pct / 0.85, 1.0))
            adjusted_threshold = self._config.cheap_threshold * time_factor

            can_buy = False
            reason = ""

            if remaining_s <= self._config.min_time_remaining:
                # Last 30s: emergency balance only
                if need_this_side > 0 and remaining_s > 10:
                    can_buy = cheap_score > -0.02
                    reason = "emergency_balance"
            elif remaining_s <= self._config.emergency_balance_time:
                # 30-120s: lower threshold if unbalanced
                if need_this_side > 0 and cheap_score > 0:
                    can_buy = True
                    reason = f"urgent_balance need={need_this_side:.0f}"
                elif cheap_score > adjusted_threshold:
                    can_buy = True
                    reason = f"cheap={cheap_score:.3f}"
            else:
                # Normal window
                if cheap_score > adjusted_threshold:
                    can_buy = True
                    reason = f"cheap={cheap_score:.3f}"
                elif need_this_side > 0 and cheap_score > 0:
                    can_buy = True
                    reason = f"imbalance need={need_this_side:.0f}"

            if can_buy:
                limit_price = bid + self._config.spread_offset
                if limit_price >= ask:
                    limit_price = ask  # don't cross
                if limit_price <= 0:
                    continue

                dollar_size = min(self._config.order_size, budget_remaining)
                shares = dollar_size / limit_price

                order = DutchOrder(
                    side=side,
                    limit_price=round(limit_price, 4),
                    shares=round(shares, 4),
                    dollars=round(dollar_size, 2),
                    time_pct=round(time_pct, 4),
                    placed_at=datetime.now(UTC),
                    reason=reason,
                )
                orders.append(order)
                budget_remaining -= dollar_size
                self._last_order_time[side] = time_pct
                self._decision_log.append(
                    f"t={time_pct:.2f}: BUY {side} {reason} "
                    f"limit={limit_price:.4f} ${dollar_size:.2f}"
                )

        return orders

    def on_fill(
        self,
        order: DutchOrder,
        fill_price: float,
        filled_shares: float,
    ) -> None:
        """Update inventory when a limit order fills."""
        cost = filled_shares * fill_price
        if order.side == "UP":
            self._inventory.shares_up += filled_shares
            self._inventory.cost_up += cost
        else:
            self._inventory.shares_dn += filled_shares
            self._inventory.cost_dn += cost

        self._orders.append({
            "side": order.side,
            "limit_price": order.limit_price,
            "fill_price": fill_price,
            "shares": round(filled_shares, 4),
            "dollars": round(cost, 4),
            "time_pct": order.time_pct,
            "reason": order.reason,
        })

    def resolve(self, outcome: str) -> DutchBarSummary:
        """Compute PnL at bar end and return summary."""
        inv = self._inventory
        matched = inv.matched
        unmatched_up = max(0, inv.shares_up - inv.shares_dn)
        unmatched_dn = max(0, inv.shares_dn - inv.shares_up)

        summary = DutchBarSummary(
            bar_id=self._bar_id,
            window_start=self._window_start,
            window_end=self._window_end,
            condition_id=self._condition_id,
            orders=list(self._orders),
            inventory={
                "up_shares": round(inv.shares_up, 4),
                "dn_shares": round(inv.shares_dn, 4),
                "matched": round(matched, 4),
                "unmatched_up": round(unmatched_up, 4),
                "unmatched_dn": round(unmatched_dn, 4),
            },
            cost={
                "total": round(inv.total_cost, 4),
                "avg_pair_cost": round(inv.avg_pair_cost, 4),
                "cost_up": round(inv.cost_up, 4),
                "cost_dn": round(inv.cost_dn, 4),
            },
            market_stats={
                "mid_range_up": (
                    [round(min(self._mid_range_up), 4), round(max(self._mid_range_up), 4)]
                    if self._mid_range_up
                    else [0, 0]
                ),
                "avg_spread_up": (
                    round(sum(self._spreads_up) / len(self._spreads_up), 4)
                    if self._spreads_up
                    else 0
                ),
                "avg_spread_dn": (
                    round(sum(self._spreads_dn) / len(self._spreads_dn), 4)
                    if self._spreads_dn
                    else 0
                ),
            },
            model_stats={
                "avg_prob": (
                    round(sum(self._model_probs) / len(self._model_probs), 4)
                    if self._model_probs
                    else 0.5
                ),
                "prob_range": (
                    [round(min(self._model_probs), 4), round(max(self._model_probs), 4)]
                    if self._model_probs
                    else [0.5, 0.5]
                ),
                "flips": self._count_flips(),
                "predictions_count": len(self._model_probs),
            },
            decision_log=list(self._decision_log),
        )

        if outcome:
            summary.compute_pnl(outcome)

        return summary

    def reset(self) -> None:
        """Clear all state for next bar."""
        self._inventory = DutchInventory()
        self._orders.clear()
        self._decision_log.clear()
        self._last_order_time = {"UP": -999.0, "DN": -999.0}
        self._model_probs.clear()
        self._mid_range_up.clear()
        self._spreads_up.clear()
        self._spreads_dn.clear()
        self._bar_id = 0
        self._condition_id = ""
        self._window_start = ""
        self._window_end = ""
        self._stopped = False

    def snapshot(self) -> dict:
        """Current state for live display."""
        inv = self._inventory
        matched = inv.matched
        return {
            "shares_up": round(inv.shares_up, 4),
            "shares_dn": round(inv.shares_dn, 4),
            "cost_up": round(inv.cost_up, 4),
            "cost_dn": round(inv.cost_dn, 4),
            "matched": round(matched, 4),
            "avg_pair_cost": round(inv.avg_pair_cost, 4),
            "total_cost": round(inv.total_cost, 4),
            "budget_remaining": round(
                self._config.bar_budget - inv.total_cost, 4,
            ),
            "unmatched_up": round(max(0, inv.shares_up - inv.shares_dn), 4),
            "unmatched_dn": round(max(0, inv.shares_dn - inv.shares_up), 4),
            "stopped": self._stopped,
            "orders_count": len(self._orders),
            "last_decisions": self._decision_log[-5:],
        }

    def _count_flips(self) -> int:
        """Count how many times model crossed 0.5."""
        flips = 0
        for i in range(1, len(self._model_probs)):
            if (self._model_probs[i - 1] - 0.5) * (self._model_probs[i] - 0.5) < 0:
                flips += 1
        return flips
