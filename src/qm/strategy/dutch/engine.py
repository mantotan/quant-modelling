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
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DutchConfig:
    """Configuration for dutch accumulation strategy.

    V4: Bilateral grid accumulation (matching trader_a strategy).
    Two-phase: build bilateral base early, model-tilt late.
    """

    bar_budget: float = 200.0
    order_size: float = 5.0
    max_orders: int = 0  # 0 = auto-derive from bar_budget / min_order_usd
    cheap_threshold: float = 0.10
    max_pair_cost: float = 1.05  # V4: relaxed from 0.97, allow convergence
    min_order_usd: float = 1.0
    min_time_remaining: float = 30.0
    emergency_balance_time: float = 120.0
    spread_offset: float = 0.01
    bar_seconds: float = 900.0

    # Pacing: budget envelope urgency bounds (V3)
    pace_urgency_lo: float = 0.5
    pace_urgency_hi: float = 2.0

    # Side discipline: max fraction of budget to one side (balance exempt)
    max_side_fraction: float = 0.65

    # Per-prediction spend cap
    max_per_prediction: float = 100.0

    # Price improvement: wider for bilateral accumulation (V4: 0.10 from 0.02)
    vwap_tolerance: float = 0.10

    # V4: Kill switch delay — don't check before this fraction of bar elapsed
    kill_switch_after: float = 0.60

    # V4: Hedge tier — buy expensive side up to this ask price
    max_hedge_ask: float = 0.80

    # V4: Share match monitor — force rebalance below this ratio
    min_share_match: float = 0.50

    # V4: Narrowed edge scaling (was implicit 0.5-2.0)
    edge_scale_lo: float = 0.8
    edge_scale_hi: float = 1.2

    # V4: Cheap tier ask threshold (buy any side below this, no model gate)
    cheap_ask_max: float = 0.50

    # V4: Rebalance warm-up — don't force share match rebalance until this
    # fraction of bar_budget is spent. Prevents instant bilateral buying.
    rebalance_warmup: float = 0.10


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

        # Pacing: per-side last order time for slot spacing (R2)
        self._last_order_time_pct_up: float = -1.0
        self._last_order_time_pct_dn: float = -1.0

        # Per-prediction spend tracking (R4)
        self._current_cal_prob: float | None = None
        self._prediction_spend: float = 0.0

        # Envelope tracking for snapshot display (R1)
        self._last_allowed_spend: float = 0.0

        # Effective max orders (derived once, reused)
        self._effective_max: int = (
            config.max_orders if config.max_orders > 0
            else int(config.bar_budget / config.min_order_usd)
        )

        # Event callback (optional, for compact event logging)
        self._on_event: Callable[[dict], None] | None = None
        self._last_gate_emitted: dict[str, float] = {}

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

    def set_event_callback(self, cb: Callable[[dict], None]) -> None:
        """Set optional callback for compact event logging."""
        self._on_event = cb

    def _emit(self, event_type: str, **data) -> None:
        """Emit event if callback set. Gate events deduped to 1 per 5% of bar."""
        if not self._on_event:
            return
        if event_type.startswith("gate_"):
            last = self._last_gate_emitted.get(event_type, -1.0)
            t = data.get("time_pct", 0.0)
            if t - last < 0.05:
                return
            self._last_gate_emitted[event_type] = t
        self._on_event({"type": event_type, "bar_id": self._bar_id, **data})

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

        Gate order (checked before the per-side loop):
          R4a  Per-prediction reset (new cal_prob → reset counter)
          E    Kill switch (avg_pair_cost on matched inventory)
          F    Budget remaining
          R4b  Per-prediction spend cap
          R5   Max orders (auto-derived)
          R1   Budget envelope pacing

        Per-side gates (inside the loop, after tier decision):
          R2   Slot-based minimum spacing (balance/emergency exempt)
          R3   Per-side budget cap (balance/emergency exempt)
          R6   Price improvement gate (no prior fills → skipped)
        """
        if self._stopped:
            return []

        # -- B: Track model stats (incremental flip counting) --
        if self._model_probs:
            prev = self._model_probs[-1]
            if (prev - 0.5) * (cal_prob - 0.5) < 0:
                self._model_flips += 1
        self._model_probs.append(cal_prob)

        # -- C: Guard: need both books and both healthy --
        if book_up is None or book_dn is None:
            return []
        if not self._book_is_healthy(book_up) or not self._book_is_healthy(book_dn):
            return []

        # Skip if book is empty (ask=1.0, bid=0.0 = no real data)
        if book_up.best_bid <= 0 or book_up.best_ask >= 1.0:
            return []
        if book_dn.best_bid <= 0 or book_dn.best_ask >= 1.0:
            return []

        # -- D: Track market stats --
        self._mid_range_up.append(book_up.mid)
        self._spreads_up.append(book_up.spread)
        self._spreads_dn.append(book_dn.spread)

        # -- I' (moved up): Compute cheap scores — needed by R1 envelope --
        cheap_up = cal_prob - book_up.best_ask
        cheap_dn = (1.0 - cal_prob) - book_dn.best_ask

        # -- R4a: Per-prediction reset — new model output resets counter --
        if (
            self._current_cal_prob is None
            or abs(cal_prob - self._current_cal_prob) > 1e-6
        ):
            self._current_cal_prob = cal_prob
            self._prediction_spend = 0.0

        # -- E: Kill switch (only on matched inventory, delayed to 60% of bar) --
        if (
            self._inventory.matched > 0
            and time_pct >= self._config.kill_switch_after
        ):
            avg_pc = self._inventory.avg_pair_cost
            if avg_pc > self._config.max_pair_cost:
                if not self._stopped:
                    self._decision_log.append(
                        f"t={time_pct:.2f}: KILL avg_pair_cost={avg_pc:.4f}"
                    )
                    self._emit("kill", time_pct=time_pct, avg_pair_cost=avg_pc)
                    self._stopped = True
                return []

        # -- F: Budget remaining --
        budget_remaining = self._config.bar_budget - self._inventory.total_cost
        if budget_remaining < self._config.min_order_usd:
            return []

        # -- R4b: Per-prediction spend cap --
        if self._prediction_spend >= self._config.max_per_prediction:
            self._emit(
                "gate_prediction", time_pct=time_pct,
                prediction_spend=self._prediction_spend, cal_prob=cal_prob,
            )
            return []

        # -- R5: Max orders (auto-derived safety cap) --
        if self._order_count >= self._effective_max:
            return []

        # -- R1: Budget envelope pacing --
        t_safe = max(time_pct, 0.01)  # floor to avoid 0^x = 0
        edge = max(cheap_up, cheap_dn, 0.01)
        urgency = max(
            self._config.pace_urgency_lo,
            min(
                edge / (2 * self._config.cheap_threshold),
                self._config.pace_urgency_hi,
            ),
        )
        pace_t = min(1.0, t_safe ** urgency)  # V4: back-loaded (convex)
        allowed_spend = self._config.bar_budget * pace_t
        self._last_allowed_spend = allowed_spend
        if self._inventory.total_cost >= allowed_spend:
            self._emit(
                "gate_envelope", time_pct=time_pct,
                total_cost=self._inventory.total_cost, allowed=allowed_spend,
            )
            return []

        # -- G: Time remaining --
        remaining_s = (1.0 - time_pct) * self._config.bar_seconds

        # -- H: PnL-aware balance state (computed once, used per-side) --
        pnl_up = self._inventory.pnl_if_up
        pnl_dn = self._inventory.pnl_if_dn
        worst = min(pnl_up, pnl_dn)
        if worst >= 0:
            needs_balance = False
            need_side: str | None = None
        else:
            needs_balance = True
            need_side = "DN" if pnl_up > pnl_dn else "UP"

        # -- J: Time factor ramps cheap_threshold from 100% at t=0 to 50% at t=0.85 --
        time_factor = max(0.5, 1.0 - 0.588 * min(time_pct / 0.85, 1.0))
        adjusted_threshold = self._config.cheap_threshold * time_factor

        orders: list[DutchOrder] = []

        # Alternate starting side to avoid UP bias with break
        sides = ("DN", "UP") if self._order_count % 2 else ("UP", "DN")
        for side in sides:
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

            # -- K1: Tier decision (V4: price-first bilateral) --
            can_buy = False
            reason = ""
            is_balance = False

            # -- Share match monitor (highest priority, after warm-up) --
            # Don't force rebalance until enough budget spent to judge
            if self._inventory.total_cost >= self._config.bar_budget * self._config.rebalance_warmup:
                max_sh = max(self._inventory.shares_up, self._inventory.shares_dn)
                min_sh = min(self._inventory.shares_up, self._inventory.shares_dn)
                share_match = min_sh / max_sh if max_sh > 0 else 1.0
                light_side = (
                    "UP" if self._inventory.shares_up < self._inventory.shares_dn
                    else "DN"
                )
                if (
                    share_match < self._config.min_share_match
                    and side == light_side
                    and ask < self._config.max_hedge_ask
                ):
                    can_buy = True
                    is_balance = False  # paced via R2, not burst
                    reason = f"match_rebalance sm={share_match:.0%}"

            # -- Time-windowed tier logic (only if share match didn't fire) --
            if not can_buy:
                if remaining_s <= self._config.min_time_remaining:
                    # Last 30s: emergency balance only
                    if (
                        needs_balance and need_side == side
                        and remaining_s > 10
                        and ask < self._config.max_hedge_ask
                    ):
                        can_buy = True
                        is_balance = True
                        reason = f"emergency worst_pnl={worst:.2f}"
                elif remaining_s <= self._config.emergency_balance_time:
                    # 30-120s: cheap + edge + urgent balance (no hedge)
                    if ask < self._config.cheap_ask_max:
                        can_buy = True
                        reason = f"cheap ask={ask:.3f}"
                    elif my_cheap > adjusted_threshold:
                        can_buy = True
                        reason = f"edge={my_cheap:.3f}"
                    elif (
                        needs_balance and need_side == side
                        and ask < self._config.max_hedge_ask
                    ):
                        can_buy = True
                        is_balance = True
                        reason = f"urgent_balance worst_pnl={worst:.2f}"
                else:
                    # Normal window: 4 tiers (cheap, edge, hedge, balance)
                    # Tier 1: Cheap — ask below fair, buy regardless of model
                    if ask < self._config.cheap_ask_max:
                        can_buy = True
                        reason = f"cheap ask={ask:.3f}"
                    # Tier 2: Model edge — model says underpriced
                    elif my_cheap > adjusted_threshold:
                        can_buy = True
                        reason = f"edge={my_cheap:.3f}"
                    # Tier 3: Hedge — other side has value, buy this side
                    elif (
                        other_cheap > self._config.cheap_threshold
                        and ask < self._config.max_hedge_ask
                    ):
                        can_buy = True
                        reason = f"hedge ask={ask:.3f}"
                    # Tier 4: Balance — worst-case PnL negative
                    elif (
                        needs_balance and need_side == side
                        and ask < self._config.max_hedge_ask
                    ):
                        can_buy = True
                        is_balance = True
                        reason = f"balance worst_pnl={worst:.2f}"

            if not can_buy:
                continue

            # -- R2: Slot-based minimum spacing (only emergency exempt) --
            if "emergency" not in reason:
                last_t = (
                    self._last_order_time_pct_up if side == "UP"
                    else self._last_order_time_pct_dn
                )
                remaining_slots = self._effective_max - self._order_count
                if remaining_slots > 0 and last_t >= 0:
                    min_gap = (1.0 - time_pct) / remaining_slots
                    if (time_pct - last_t) < min_gap:
                        self._emit(
                            "gate_spacing", time_pct=time_pct, side=side,
                            last_t=last_t, min_gap=min_gap,
                        )
                        continue

            # -- R3: Per-side budget cap (only emergency exempt) --
            if "emergency" not in reason:
                side_cost = (
                    self._inventory.cost_up if side == "UP"
                    else self._inventory.cost_dn
                )
                max_side_budget = (
                    self._config.bar_budget * self._config.max_side_fraction
                )
                if side_cost >= max_side_budget:
                    self._emit(
                        "gate_side_cap", time_pct=time_pct, side=side,
                        side_cost=side_cost, max_side_budget=max_side_budget,
                    )
                    continue

            # -- K2: Limit price computation --
            limit_price = bid + self._config.spread_offset
            if limit_price >= ask:
                limit_price = ask
            if limit_price <= 0:
                continue

            # -- R6: Price improvement gate (balance/hedge/rebalance exempt) --
            if is_balance or "hedge" in reason or "match_rebalance" in reason:
                pass  # skip VWAP — these tiers buy at inherently worse prices
            elif side == "UP" and self._inventory.shares_up > 0:
                avg_fill = self._inventory.cost_up / self._inventory.shares_up
                if limit_price > avg_fill * (1 + self._config.vwap_tolerance):
                    self._emit(
                        "gate_vwap", time_pct=time_pct, side=side,
                        limit=limit_price, avg_fill=avg_fill,
                    )
                    continue
            elif side == "DN" and self._inventory.shares_dn > 0:
                avg_fill = self._inventory.cost_dn / self._inventory.shares_dn
                if limit_price > avg_fill * (1 + self._config.vwap_tolerance):
                    self._emit(
                        "gate_vwap", time_pct=time_pct, side=side,
                        limit=limit_price, avg_fill=avg_fill,
                    )
                    continue

            # -- K3: Smart sizing (V4) --
            if "hedge" in reason:
                # Hedge: flat half-size order (limit exposure on expensive side)
                dollar_size = self._config.order_size * 0.5
                dollar_size = min(dollar_size, budget_remaining)
            elif "match_rebalance" in reason or (needs_balance and need_side == side):
                # Balance/rebalance: buy shares to reduce imbalance
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
                # Edge-scaled: narrowed range (V4: 0.8x to 1.2x)
                edge_for_scale = max(my_cheap, 0)
                edge_scale = min(
                    edge_for_scale / (self._config.cheap_threshold * 2),
                    self._config.edge_scale_hi,
                )
                edge_scale = max(self._config.edge_scale_lo, edge_scale)
                dollar_size = self._config.order_size * edge_scale
                dollar_size = min(dollar_size, budget_remaining)

            # Clamp to per-prediction remaining (R4)
            prediction_remaining = (
                self._config.max_per_prediction - self._prediction_spend
            )
            dollar_size = min(dollar_size, prediction_remaining)

            if dollar_size < self._config.min_order_usd:
                continue

            shares = dollar_size / limit_price

            # -- K4: Order creation + bookkeeping --
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
            self._prediction_spend += dollar_size

            # Update per-side last order time (R2)
            if side == "UP":
                self._last_order_time_pct_up = time_pct
            else:
                self._last_order_time_pct_dn = time_pct

            self._decision_log.append(
                f"t={time_pct:.2f}: BUY {side} {reason} "
                f"limit={limit_price:.4f} ${dollar_size:.2f}"
            )
            self._emit(
                "order", time_pct=time_pct, side=side, reason=reason,
                limit=limit_price, dollars=dollar_size,
            )

            # One side per tick — let prices update before buying other side.
            # trader_a median gap between first UP and first DN is 72 seconds.
            break

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

        self._emit(
            "fill", time_pct=order.time_pct, side=order.side,
            fill_price=fill_price, shares=filled_shares,
            cost=round(cost, 4),
            total_cost=round(self._inventory.total_cost, 4),
        )

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

        # Pacing state (R1/R2/R4)
        self._last_order_time_pct_up = -1.0
        self._last_order_time_pct_dn = -1.0
        self._current_cal_prob = None
        self._prediction_spend = 0.0
        self._last_allowed_spend = 0.0
        self._last_gate_emitted.clear()

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
            "allowed_spend": round(self._last_allowed_spend, 2),
            "prediction_spend": round(self._prediction_spend, 2),
            "max_per_prediction": self._config.max_per_prediction,
            "side_cap": round(
                self._config.bar_budget * self._config.max_side_fraction, 2,
            ),
            "avg_fill_up": (
                round(inv.cost_up / inv.shares_up, 4)
                if inv.shares_up > 0 else 0
            ),
            "avg_fill_dn": (
                round(inv.cost_dn / inv.shares_dn, 4)
                if inv.shares_dn > 0 else 0
            ),
            "share_match_pct": round(
                min(inv.shares_up, inv.shares_dn)
                / max(inv.shares_up, inv.shares_dn) * 100, 1,
            ) if max(inv.shares_up, inv.shares_dn) > 0 else 0,
        }

