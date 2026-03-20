"""Dutch accumulation engine V2 — buy both sides throughout a bar.

Core state machine that tracks one bar's lifecycle:
  - Holds bilateral inventory (shares_up, shares_dn, cost_up, cost_dn)
  - PnL-aware balancing (only urgently balance when worst-case outcome loses)
  - 3-tier buy decision: cheap (underpriced), contra (other side overpriced),
    balance (worst-case PnL negative)
  - Marginal kill switch (stops when next pair costs > threshold)
  - Book health checks (spread, depth)
  - Edge-scaled + PnL-aware order sizing

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

    bar_budget: float = 200.0
    order_size: float = 5.0
    max_orders: int = 20
    cheap_threshold: float = 0.10
    contra_threshold: float = 0.11
    max_pair_cost: float = 0.97
    min_order_usd: float = 1.0
    min_time_remaining: float = 30.0
    emergency_balance_time: float = 120.0
    spread_offset: float = 0.01
    bar_seconds: float = 900.0


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

    @property
    def pnl_if_up(self) -> float:
        """Profit if UP wins: UP shares pay $1 each, minus total cost."""
        return self.shares_up * 1.0 - self.total_cost

    @property
    def pnl_if_dn(self) -> float:
        """Profit if DN wins: DN shares pay $1 each, minus total cost."""
        return self.shares_dn * 1.0 - self.total_cost

    @property
    def worst_case_pnl(self) -> float:
        return min(self.pnl_if_up, self.pnl_if_dn)


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

        matched_payout = matched * 1.0
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
    """Core engine: decides when to buy each side, tracks inventory.

    Buy decision uses 3 tiers:
      Tier 1 (cheap): side is underpriced vs model (edge > threshold)
      Tier 2 (contra): other side is overpriced → this side is value play
      Tier 3 (balance): worst-case PnL is negative, need to hedge
    """

    def __init__(self, config: DutchConfig) -> None:
        self._config = config
        self._inventory = DutchInventory()
        self._orders: list[dict] = []
        self._order_count: int = 0
        self._decision_log: list[str] = []
        self._model_probs: list[float] = []
        self._model_flips: int = 0
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

    @staticmethod
    def _book_is_healthy(book) -> bool:
        """Check if orderbook has enough liquidity to trade."""
        if book is None:
            return False
        if book.spread > 0.10:
            return False
        if book.depth_at_bbo() < 5:
            return False
        return True

    def on_tick(
        self,
        time_pct: float,
        cal_prob: float,
        book_up,
        book_dn,
    ) -> list[DutchOrder]:
        """Core decision logic. Called on every book update.

        Returns 0, 1, or 2 DutchOrder objects to place.
        book_up/book_dn are TokenBook | None.
        """
        if self._stopped:
            return []

        # Track model stats (incremental flip counting)
        if self._model_probs:
            prev = self._model_probs[-1]
            if (prev - 0.5) * (cal_prob - 0.5) < 0:
                self._model_flips += 1
        self._model_probs.append(cal_prob)

        # Guard: need both books and both healthy
        if book_up is None or book_dn is None:
            return []
        if not self._book_is_healthy(book_up) or not self._book_is_healthy(book_dn):
            return []

        # Skip if book is empty (ask=1.0, bid=0.0 = no real data)
        if book_up.best_bid <= 0 or book_up.best_ask >= 1.0:
            return []
        if book_dn.best_bid <= 0 or book_dn.best_ask >= 1.0:
            return []

        # Track market stats
        self._mid_range_up.append(book_up.mid)
        self._spreads_up.append(book_up.spread)
        self._spreads_dn.append(book_dn.spread)

        # Kill switch: only after we have matched inventory AND avg cost is bad.
        # Don't kill on marginal cost alone — the whole strategy is buying sides
        # at DIFFERENT times. A 1.01 marginal at one moment doesn't mean the
        # pair will cost 1.01 (prices oscillate within the bar).
        if self._inventory.matched > 0:
            avg_pc = self._inventory.avg_pair_cost
            if avg_pc > self._config.max_pair_cost:
                if not self._stopped:
                    self._decision_log.append(
                        f"t={time_pct:.2f}: KILL avg_pair_cost={avg_pc:.4f}"
                    )
                    self._stopped = True
                return []

        # Budget + order count check
        budget_remaining = self._config.bar_budget - self._inventory.total_cost
        if budget_remaining < self._config.min_order_usd:
            return []
        if self._order_count >= self._config.max_orders:
            return []

        remaining_s = (1.0 - time_pct) * self._config.bar_seconds

        # PnL-aware balance state (computed once, used per-side)
        pnl_up = self._inventory.pnl_if_up
        pnl_dn = self._inventory.pnl_if_dn
        worst = min(pnl_up, pnl_dn)
        if worst >= 0:
            needs_balance = False
            need_side: str | None = None
        else:
            needs_balance = True
            need_side = "DN" if pnl_up > pnl_dn else "UP"

        # Compute cheap scores for both sides BEFORE the loop
        cheap_up = cal_prob - book_up.best_ask
        cheap_dn = (1.0 - cal_prob) - book_dn.best_ask

        # TUNING: time_factor ramps cheap_threshold from 100% at t=0 to 50% at t=0.85
        # Coefficients to be refined from JSONL bar data after live observation
        time_factor = max(0.5, 1.0 - 0.588 * min(time_pct / 0.85, 1.0))
        adjusted_threshold = self._config.cheap_threshold * time_factor

        orders: list[DutchOrder] = []

        for side in ("UP", "DN"):
            if side == "UP":
                bid = book_up.best_bid
                ask = book_up.best_ask
                my_cheap = cheap_up
                other_cheap = cheap_dn
            else:
                bid = book_dn.best_bid
                ask = book_dn.best_ask
                my_cheap = cheap_dn
                other_cheap = cheap_up

            # Contra-signal: positive when OTHER side is overpriced
            # (meaning THIS side is the value play)
            contra_signal = -other_cheap

            can_buy = False
            reason = ""

            if remaining_s <= self._config.min_time_remaining:
                # Last 30s: emergency balance only (if book still healthy)
                if needs_balance and need_side == side and remaining_s > 10:
                    if my_cheap > -0.02:
                        can_buy = True
                        reason = f"emergency worst_pnl={worst:.2f}"
            elif remaining_s <= self._config.emergency_balance_time:
                # 30-120s: urgent balance + normal buys
                # Tier 1: direct cheap
                if my_cheap > adjusted_threshold:
                    can_buy = True
                    reason = f"cheap={my_cheap:.3f}"
                # Tier 3: urgent balance
                elif needs_balance and need_side == side and my_cheap > 0:
                    can_buy = True
                    reason = f"urgent_balance worst_pnl={worst:.2f}"
            else:
                # Normal window: all 3 tiers
                # Tier 1: direct underpricing
                if my_cheap > adjusted_threshold:
                    can_buy = True
                    reason = f"cheap={my_cheap:.3f}"
                # Tier 2: contra-signal (other side overpriced, this side is value)
                # Guards: this side must be cheap (my_cheap > 0) + enough time
                elif (
                    contra_signal > self._config.contra_threshold
                    and my_cheap > 0
                    and remaining_s > 180
                ):
                    can_buy = True
                    reason = f"contra={contra_signal:.3f}"
                # Tier 3: PnL-aware balance
                elif needs_balance and need_side == side and my_cheap > 0:
                    can_buy = True
                    reason = f"balance worst_pnl={worst:.2f}"

            if can_buy:
                limit_price = bid + self._config.spread_offset
                if limit_price >= ask:
                    limit_price = ask
                if limit_price <= 0:
                    continue

                # Smart sizing
                if needs_balance and need_side == side:
                    # Balance: buy enough shares to make worst_case_pnl = 0
                    if side == "UP":
                        shares_needed = self._inventory.total_cost - self._inventory.shares_up
                    else:
                        shares_needed = self._inventory.total_cost - self._inventory.shares_dn
                    shares_needed = max(0, shares_needed)
                    dollar_size = min(
                        shares_needed * limit_price,
                        budget_remaining,
                        self._config.order_size * 2,
                    )
                else:
                    # Edge-scaled: bigger edge → bigger order (0.5x to 2x base)
                    edge_for_scale = max(my_cheap, contra_signal if "contra" in reason else 0)
                    edge_scale = min(edge_for_scale / (self._config.cheap_threshold * 2), 2.0)
                    edge_scale = max(0.5, edge_scale)
                    dollar_size = self._config.order_size * edge_scale
                    dollar_size = min(dollar_size, budget_remaining)

                if dollar_size < self._config.min_order_usd:
                    continue

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
                self._order_count += 1
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
                "flips": self._model_flips,
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
        self._order_count = 0
        self._decision_log.clear()
        self._model_probs.clear()
        self._model_flips = 0
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
            "pnl_if_up": round(inv.pnl_if_up, 4),
            "pnl_if_dn": round(inv.pnl_if_dn, 4),
            "worst_case_pnl": round(inv.worst_case_pnl, 4),
            "stopped": self._stopped,
            "orders_count": len(self._orders),
            "last_decisions": self._decision_log[-5:],
        }

