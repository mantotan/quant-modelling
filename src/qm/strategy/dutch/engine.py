"""Dutch accumulation engine V7 — model-aware conviction engine.

Core state machine that tracks one bar's lifecycle:
  - Holds bilateral inventory (shares_up, shares_dn, cost_up, cost_dn)
  - Time-progressive risk budget: worst-case loss capped by quadratic curve
  - Conviction blending: model + market price, time-weighted
  - Adaptive pair cost ceiling: tightens when profitable pairs exist
  - Unmatched cap: buy-side discipline on heavy side
  - Time-aware sell phases: profit-only → conviction-gated loss → dump
  - Book health checks (spread, depth)

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

    V7: Conviction engine — blends model prediction with market price,
    adaptive pair cost ceiling, unmatched cap, time-aware sell phases.
    """

    bar_budget: float = 200.0
    order_size: float = 5.0
    max_orders: int = 0  # 0 = auto-derive from bar_budget / min_order_usd
    cheap_threshold: float = 0.10
    min_order_usd: float = 1.0
    min_time_remaining: float = 30.0
    emergency_balance_time: float = 120.0
    spread_offset: float = 0.01
    bar_seconds: float = 900.0

    # Pacing: budget envelope urgency bounds (V3)
    pace_urgency_lo: float = 0.5
    pace_urgency_hi: float = 2.0

    # Side discipline: max fraction of budget to one side (trailing exempt)
    max_side_fraction: float = 0.65

    # Per-prediction spend cap
    max_per_prediction: float = 100.0

    # Price improvement: wider for bilateral accumulation
    vwap_tolerance: float = 0.10

    # Warm-up: don't sell until this fraction of bar_budget is spent
    rebalance_warmup: float = 0.10

    # Sell limits
    sell_max_fraction: float = 0.50    # sell at most 50% of net shares
    sell_min_shares: float = 10.0      # minimum net shares to consider selling

    # V6: Per-order pair cost guard — block buy if sim avg_pair_cost exceeds this
    # Set above 1.0 because ask-based pair_cost includes vig (~1-2c per side),
    # but actual fill prices (at bid+offset) are lower than ask.
    max_marginal_pair_cost: float = 1.03

    # V6.1: Time-progressive risk budget
    risk_floor: float = 0.05        # 5% of budget at bar start ($10 on $200)
    risk_ceil: float = 0.15         # 15% max at t_end
    risk_t_start: float = 0.10      # risk starts growing here
    risk_t_end: float = 0.80        # risk maxes out here
    risk_exponent: float = 2.0      # quadratic curve

    # V7: Conviction blending (sell-side only)
    conviction_market_start: float = 0.30   # market weight=0 before this
    conviction_market_full: float = 1.00    # market weight=1.0 at bar end

    # V7: Profit protection
    profit_protect_min_pairs: int = 5       # min matched pairs before tightening

    # V7: Unmatched cap (buy-side discipline)
    min_unmatched_shares: float = 20.0      # allow this many before cap
    unmatched_ratio: float = 0.50           # max unmatched = max(min, matched × ratio)

    # V7.1: Conviction-gated buy skip — don't buy the side the model thinks
    # will lose when conviction is strong.  0.0 = disabled (pure bilateral).
    # 0.60 = skip unfavored side when model says < 40% chance of winning.
    conviction_buy_skip: float = 0.0

    # V7.2: Conviction-aware buy sizing — scale order size by model confidence.
    # size_mult = conviction_size_floor + (1 - conviction_size_floor) * model_p_side
    # At P(UP)=0.70: UP gets 0.79x, DN gets 0.51x → biases toward favored side.
    # 0.0 = disabled (equal sizing). 0.3 = recommended (range 0.3x–1.0x).
    conviction_size_floor: float = 0.0

    # V7.3: One-sided cost cap — limit total spend when no matched pairs exist.
    # Prevents $8-9 tail losses on directional bets that go wrong.
    # 0.0 = disabled.  5.0 = max $5 spent before first pair forms.
    max_onesided_cost: float = 0.0

    # V7.5: Flip kill gate — stop buying after N model direction flips.
    # High flip count = whipsaw bar → cancel pending orders, go sell-only.
    # 0 = disabled.  6 = recommended for BTC 15m (validated on 130-bar sweep).
    flip_kill_after: int = 0

    # V7.6: Buy warmup — don't place buy orders before this fraction of bar.
    # Early predictions are noisy; waiting lets the model establish direction.
    # 0.0 = disabled (buy from tick 1).  0.20 = skip first 20% of bar.
    min_buy_time_pct: float = 0.0

    # V7.4: Resting limit orders — place below bid to catch dips.
    # 0.0 = disabled (reactive only, V7.3 behavior).
    resting_discount: float = 0.0
    # If no buy fills by this time_pct, switch to reactive for rest of bar.
    resting_fallback_time: float = 0.40

    # V7: Sell phases
    sell_loss_start: float = 0.70           # allow conviction-gated loss sells
    sell_dump_start: float = 0.90           # sell at any price

    # --- Deprecated fields (kept for backward compat, ignored by V7 on_tick) ---
    edge_decay_start: float = 0.70
    edge_decay_end: float = 0.85
    edge_scale_lo: float = 0.8
    edge_scale_hi: float = 1.2
    sell_profit_only: bool = True
    max_pair_cost: float = 1.05
    kill_switch_after: float = 0.60
    max_hedge_ask: float = 0.80
    min_share_match: float = 0.50
    cheap_ask_max: float = 0.50
    sell_loss_threshold: float = 0.05
    pnl_gap_tolerance: float = 5.0  # dollars
    allow_paired_buys: bool = True


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
    action: str = "BUY"  # V5: "BUY" or "SELL"
    order_mode: str = "reactive"  # V7.4: "reactive" or "resting"


@dataclass
class DutchInventory:
    """Bilateral inventory tracker with sell support (V5).

    All public properties return NET values (buy - sell) so callers
    automatically get sell-adjusted numbers without code changes.
    """

    # Gross buy tracking
    shares_up: float = 0.0
    shares_dn: float = 0.0
    cost_up: float = 0.0
    cost_dn: float = 0.0

    # V5: Sell tracking
    sell_revenue_up: float = 0.0
    sell_revenue_dn: float = 0.0
    sold_shares_up: float = 0.0
    sold_shares_dn: float = 0.0

    @property
    def net_shares_up(self) -> float:
        return self.shares_up - self.sold_shares_up

    @property
    def net_shares_dn(self) -> float:
        return self.shares_dn - self.sold_shares_dn

    @property
    def net_cost_up(self) -> float:
        return self.cost_up - self.sell_revenue_up

    @property
    def net_cost_dn(self) -> float:
        return self.cost_dn - self.sell_revenue_dn

    @property
    def matched(self) -> float:
        return min(self.net_shares_up, self.net_shares_dn)

    @property
    def total_cost(self) -> float:
        """Net cost = buy cost - sell revenue."""
        return self.net_cost_up + self.net_cost_dn

    @property
    def avg_pair_cost(self) -> float:
        """Average cost per matched pair (net). < 1.0 = guaranteed profit."""
        m = self.matched
        if m <= 0:
            return 1.0
        up_avg = self.net_cost_up / self.net_shares_up if self.net_shares_up > 0 else 0.0
        dn_avg = self.net_cost_dn / self.net_shares_dn if self.net_shares_dn > 0 else 0.0
        return up_avg + dn_avg

    @property
    def imbalance(self) -> float:
        """Positive = more UP than DN (net)."""
        return self.net_shares_up - self.net_shares_dn

    @property
    def pnl_if_up(self) -> float:
        """Profit if UP wins: net UP shares pay $1 each, minus net cost."""
        return self.net_shares_up * 1.0 - self.total_cost

    @property
    def pnl_if_dn(self) -> float:
        """Profit if DN wins: net DN shares pay $1 each, minus net cost."""
        return self.net_shares_dn * 1.0 - self.total_cost

    @property
    def worst_case_pnl(self) -> float:
        return min(self.pnl_if_up, self.pnl_if_dn)

    def simulated_avg_pair_cost(
        self, side: str, shares: float, price: float,
    ) -> float:
        """What would avg_pair_cost be if we bought `shares` of `side` at `price`?

        Returns 1.0 if no matched pairs would exist after the simulated buy.
        """
        new_cost = shares * price
        new_up = self.net_shares_up + (shares if side == "UP" else 0)
        new_dn = self.net_shares_dn + (shares if side == "DN" else 0)
        new_cost_up = self.net_cost_up + (new_cost if side == "UP" else 0)
        new_cost_dn = self.net_cost_dn + (new_cost if side == "DN" else 0)
        matched = min(new_up, new_dn)
        if matched <= 0:
            return 1.0
        up_avg = new_cost_up / new_up if new_up > 0 else 0.0
        dn_avg = new_cost_dn / new_dn if new_dn > 0 else 0.0
        return up_avg + dn_avg



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
    """V7 engine: model-aware conviction engine for Dutch accumulation.

    Conviction blending (model + market price), adaptive pair cost ceiling,
    unmatched cap for buy-side discipline, time-aware sell phases
    (profit-only → conviction-gated loss → dump).

    Decision flow:
      Phase A: Pair opportunity detection (ask_up + ask_dn < threshold?)
      Phase B: Risk budget + lighter-side-first ordering
      Per-side: Sizing, unmatched cap, pair cost guard, risk budget gate
      Phase F: Three-phase sell (conviction-influenced)
    """

    def __init__(self, config: DutchConfig) -> None:
        self._config = config
        self._inventory = DutchInventory()
        self._orders: list[dict] = []
        self._order_count: int = 0
        self._decision_log: list[str] = []
        self._model_probs: list[float] = []
        self._model_flips: int = 0
        self._flip_killed: bool = False
        self._mid_range_up: list[float] = []
        self._spreads_up: list[float] = []
        self._spreads_dn: list[float] = []
        self._bar_id: int = 0
        self._condition_id: str = ""
        self._window_start: str = ""
        self._window_end: str = ""

        # Pacing: per-side last order time for slot spacing (R2)
        self._last_order_time_pct_up: float = -1.0
        self._last_order_time_pct_dn: float = -1.0

        # Per-prediction spend tracking (R4)
        self._current_cal_prob: float | None = None
        self._prediction_spend: float = 0.0

        # V6: Track committed (placed but unfilled) spend to prevent budget overshoot
        self._committed_spend: float = 0.0

        # Sell cooldown to prevent rapid-fire sells reading stale inventory
        self._last_sell_time_pct: float = -1.0

        # Track shares committed to pending sell orders (not yet filled)
        self._pending_sell_shares_up: float = 0.0
        self._pending_sell_shares_dn: float = 0.0

        # Envelope tracking for snapshot display (R1)
        self._last_allowed_spend: float = 0.0

        # V6: Stash last asks for snapshot display
        self._last_ask_up: float = 0.0
        self._last_ask_dn: float = 0.0

        # V6.1: Track last time_pct for snapshot risk budget
        self._last_time_pct: float = 0.0

        # V7: Conviction tracking for snapshot
        self._conviction_up: float = 0.5
        self._conviction_dn: float = 0.5

        # Effective max orders (derived once, reused)
        self._effective_max: int = (
            config.max_orders if config.max_orders > 0
            else int(config.bar_budget / config.min_order_usd)
        )

        # Event callback (optional, for compact event logging)
        self._on_event: Callable[[dict], None] | None = None
        self._last_gate_emitted: dict[str, float] = {}

        # V7.4: Resting order tracking
        self._first_buy_filled: bool = False

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

    @property
    def flip_killed(self) -> bool:
        """Whether the flip kill gate has fired for this bar."""
        return self._flip_killed

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

    def _risk_budget(self, time_pct: float) -> float:
        """Max allowed worst-case loss at this point in the bar."""
        cfg = self._config
        if cfg.risk_t_end <= cfg.risk_t_start:
            t_norm = 1.0
        else:
            t_norm = (time_pct - cfg.risk_t_start) / (cfg.risk_t_end - cfg.risk_t_start)
        t_clamped = max(0.0, min(1.0, t_norm))
        risk_pct = cfg.risk_floor + (cfg.risk_ceil - cfg.risk_floor) * (t_clamped ** cfg.risk_exponent)
        return cfg.bar_budget * risk_pct

    def _conviction(self, side: str, cal_prob: float, ask_price: float, time_pct: float) -> float:
        """How confident are we that `side` wins? 0=certain loss, 1=certain win.

        Blends model prediction with market price. Market weight grows with time:
        early bar = trust model, late bar = trust market.
        """
        model_p = cal_prob if side == "UP" else (1.0 - cal_prob)
        market_p = 1.0 - ask_price

        cfg = self._config
        if cfg.conviction_market_full <= cfg.conviction_market_start:
            mw = 1.0
        else:
            mw = (time_pct - cfg.conviction_market_start) / (
                cfg.conviction_market_full - cfg.conviction_market_start
            )
        market_weight = max(0.0, min(1.0, mw))

        return max(0.0, min(1.0,
            (1.0 - market_weight) * model_p + market_weight * market_p
        ))

    def _effective_max_pair_cost(self) -> float:
        """Adaptive pair cost ceiling: tightens when profitable pairs exist."""
        matched = self._inventory.matched
        if matched < self._config.profit_protect_min_pairs:
            return self._config.max_marginal_pair_cost

        pc = self._inventory.avg_pair_cost
        if pc >= 1.0:
            return self._config.max_marginal_pair_cost

        profit = 1.0 - pc
        margin = max(0.02, 0.05 - profit)
        return min(pc + margin, self._config.max_marginal_pair_cost)

    def _is_resting_mode(self, time_pct: float) -> bool:
        """Should orders be placed in resting mode (below bid)?

        V7.4: Resting places at bid - discount to catch dips.
        Fallback: if no fills by resting_fallback_time, switch to reactive.
        """
        if self._config.resting_discount <= 0:
            return False
        # After fallback time with no fills → reactive
        return (
            self._first_buy_filled
            or time_pct < self._config.resting_fallback_time
        )

    def on_tick(
        self,
        time_pct: float,
        cal_prob: float,
        book_up,
        book_dn,
    ) -> list[DutchOrder]:
        """V7 decision logic. Called on every book update.

        Returns 0-3 DutchOrder objects (up to 2 buys + 1 sell).
        book_up/book_dn are TokenBook | None.

        Pre-screening gates: B (model stats), C (book health),
          R4a (prediction reset), F (budget), R4b (per-prediction cap),
          R5 (max orders), R1 (envelope pacing).

        Decision phases: A (pair opportunity), B (risk budget),
          Per-side (sizing, unmatched cap, pair cost, risk gate),
          F (three-phase sell).
        """

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

        # Stash asks for snapshot display
        self._last_ask_up = book_up.best_ask
        self._last_ask_dn = book_dn.best_ask

        # -- R4a: Per-prediction reset — new model output resets counter --
        if (
            self._current_cal_prob is None
            or abs(cal_prob - self._current_cal_prob) > 1e-6
        ):
            self._current_cal_prob = cal_prob
            self._prediction_spend = 0.0

        # -- F: Budget remaining (includes inflight orders not yet filled) --
        budget_remaining = (
            self._config.bar_budget
            - self._inventory.total_cost
            - self._committed_spend
        )
        if budget_remaining < self._config.min_order_usd:
            return []

        # -- V7.3: One-sided cost cap --
        if (
            self._config.max_onesided_cost > 0
            and self._inventory.matched <= 0
            and self._inventory.total_cost + self._committed_spend
                >= self._config.max_onesided_cost
        ):
            self._emit(
                "gate_onesided_cap", time_pct=time_pct,
                cost=round(self._inventory.total_cost + self._committed_spend, 2),
                cap=self._config.max_onesided_cost,
            )
            return self._sell_pass(time_pct, cal_prob, book_up, book_dn, [])

        # -- V7.6: Buy warmup gate — skip early noisy predictions --
        if self._config.min_buy_time_pct > 0 and time_pct < self._config.min_buy_time_pct:
            return self._sell_pass(time_pct, cal_prob, book_up, book_dn, [])

        # -- V7.5: Flip kill gate — too many model flips = whipsaw, sell only --
        if self._config.flip_kill_after > 0 and self._model_flips >= self._config.flip_kill_after:
            if not self._flip_killed:
                self._flip_killed = True
                self._emit(
                    "gate_flip_kill", time_pct=time_pct,
                    flips=self._model_flips,
                    threshold=self._config.flip_kill_after,
                )
            return self._sell_pass(time_pct, cal_prob, book_up, book_dn, [])

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

        # -- R1: Budget envelope pacing (V6: urgency from pair opportunity) --
        t_safe = max(time_pct, 0.01)
        pair_opportunity = max(
            1.0 - (book_up.best_ask + book_dn.best_ask), 0.01,
        )
        urgency = max(
            self._config.pace_urgency_lo,
            min(
                pair_opportunity / (2 * self._config.cheap_threshold),
                self._config.pace_urgency_hi,
            ),
        )
        pace_t = min(1.0, t_safe ** urgency)
        allowed_spend = self._config.bar_budget * pace_t
        self._last_allowed_spend = allowed_spend
        spent = self._inventory.total_cost + self._committed_spend
        if spent >= allowed_spend:
            self._emit(
                "gate_envelope", time_pct=time_pct,
                total_cost=spent, allowed=allowed_spend,
            )
            return []

        # ============================================================
        # Phase A: Pair opportunity detection
        # ============================================================
        pair_cost = book_up.best_ask + book_dn.best_ask
        is_dutch_opportunity = pair_cost < self._config.max_marginal_pair_cost

        # Cheap scores (for display)
        cheap_up = cal_prob - book_up.best_ask
        cheap_dn = (1.0 - cal_prob) - book_dn.best_ask

        # ============================================================
        # Phase B: Risk budget
        # ============================================================
        risk_allowed = self._risk_budget(time_pct)
        self._last_time_pct = time_pct

        # Need Dutch opportunity to trade at all
        if not is_dutch_opportunity:
            return self._sell_pass(time_pct, cal_prob, book_up, book_dn, [])

        # Lighter side first — completes pairs, frees risk room
        if self._inventory.net_shares_up <= self._inventory.net_shares_dn:
            buy_sides = ["UP", "DN"]
        else:
            buy_sides = ["DN", "UP"]

        # Determine heavy side for unmatched cap
        if self._inventory.net_shares_up > self._inventory.net_shares_dn:
            heavy_side: str | None = "UP"
        elif self._inventory.net_shares_dn > self._inventory.net_shares_up:
            heavy_side = "DN"
        else:
            heavy_side = None  # equal = no heavy side

        # Compute conviction for snapshot display
        self._conviction_up = self._conviction("UP", cal_prob, book_up.best_ask, time_pct)
        self._conviction_dn = self._conviction("DN", cal_prob, book_dn.best_ask, time_pct)

        # ============================================================
        # Per-side order construction
        # ============================================================
        remaining_s = (1.0 - time_pct) * self._config.bar_seconds
        orders: list[DutchOrder] = []

        for side in buy_sides:
            book = book_up if side == "UP" else book_dn
            ask = book.best_ask
            bid = book.best_bid

            # -- V7.1: Conviction-gated buy skip --
            # Skip buying the unfavored side when model is confident enough.
            # This prevents accumulating losing-side inventory that becomes
            # worthless unmatched waste.
            if self._config.conviction_buy_skip > 0:
                side_conv = (
                    self._conviction_up if side == "UP"
                    else self._conviction_dn
                )
                if side_conv < (1.0 - self._config.conviction_buy_skip):
                    self._emit(
                        "gate_conviction_skip", time_pct=time_pct,
                        side=side, conviction=round(side_conv, 3),
                        threshold=round(1.0 - self._config.conviction_buy_skip, 3),
                    )
                    continue

            # -- Limit price: resting (V7.4) or reactive --
            if self._is_resting_mode(time_pct):
                limit_price = max(bid - self._config.resting_discount, 0.01)
                limit_price = min(limit_price, ask - 0.01)
                order_mode = "resting"
            else:
                limit_price = min(
                    bid + self._config.spread_offset, ask - 0.01,
                )
                order_mode = "reactive"
            if limit_price <= 0:
                continue

            # -- R2: Slot spacing (no exemptions) --
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

            # -- R3: Side budget cap (no exemptions) --
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

            # -- Sizing: share-based (expensive side sets pace) --
            max_ask = max(book_up.best_ask, book_dn.best_ask, 0.01)
            base_shares = self._config.order_size / max_ask

            # -- V7.2: Conviction-aware sizing --
            # Scale order size by model confidence for this side.
            # Biases accumulation toward the model-favored side.
            if self._config.conviction_size_floor > 0:
                model_p_side = cal_prob if side == "UP" else (1.0 - cal_prob)
                floor = self._config.conviction_size_floor
                size_mult = floor + (1.0 - floor) * model_p_side
                base_shares *= size_mult

            dollar_size = base_shares * limit_price

            dollar_size = min(dollar_size, budget_remaining)

            # Clamp to per-prediction remaining (R4)
            prediction_remaining = (
                self._config.max_per_prediction - self._prediction_spend
            )
            dollar_size = min(dollar_size, prediction_remaining)

            # -- Risk budget clamp --
            # Max ds that keeps worst-case <= risk_allowed for the OTHER outcome.
            # Same formula for both sides — light side naturally gets bigger cap.
            base_cost = (
                self._inventory.total_cost + self._committed_spend
            )
            other_side_shares = (
                self._inventory.net_shares_dn if side == "UP"
                else self._inventory.net_shares_up
            )
            risk_max_ds = risk_allowed - base_cost + other_side_shares
            if risk_max_ds < dollar_size:
                dollar_size = max(0.0, risk_max_ds)
                self._emit(
                    "gate_risk_cap", time_pct=time_pct, side=side,
                    capped_to=round(dollar_size, 2),
                    allowed=round(risk_allowed, 2),
                )

            if dollar_size < self._config.min_order_usd:
                continue

            shares = dollar_size / limit_price

            # -- Unmatched cap (heavy side only) --
            if heavy_side is not None and side == heavy_side:
                unmatched_this = max(0, (
                    self._inventory.net_shares_up if side == "UP"
                    else self._inventory.net_shares_dn
                ) - (
                    self._inventory.net_shares_dn if side == "UP"
                    else self._inventory.net_shares_up
                ))
                max_unmatched = max(
                    self._config.min_unmatched_shares,
                    self._inventory.matched * self._config.unmatched_ratio,
                )
                if unmatched_this >= max_unmatched:
                    self._emit(
                        "gate_unmatched_cap", time_pct=time_pct, side=side,
                        unmatched=round(unmatched_this, 1),
                        cap=round(max_unmatched, 1),
                    )
                    continue

            # -- Phase D: Per-order pair cost guard --
            other_shares = (
                self._inventory.net_shares_dn if side == "UP"
                else self._inventory.net_shares_up
            )
            if other_shares > 0:
                sim_pc = self._inventory.simulated_avg_pair_cost(
                    side, shares, limit_price,
                )
                if sim_pc > self._effective_max_pair_cost():
                    self._emit(
                        "gate_pair_cost", time_pct=time_pct, side=side,
                        sim_pair_cost=round(sim_pc, 4),
                    )
                    continue

            # -- R6: VWAP gate (no exemptions) --
            if side == "UP" and self._inventory.net_shares_up > 0:
                avg_fill = (
                    self._inventory.net_cost_up
                    / self._inventory.net_shares_up
                )
                if limit_price > avg_fill * (1 + self._config.vwap_tolerance):
                    self._emit(
                        "gate_vwap", time_pct=time_pct, side=side,
                        limit=limit_price, avg_fill=avg_fill,
                    )
                    continue
            elif side == "DN" and self._inventory.net_shares_dn > 0:
                avg_fill = (
                    self._inventory.net_cost_dn
                    / self._inventory.net_shares_dn
                )
                if limit_price > avg_fill * (1 + self._config.vwap_tolerance):
                    self._emit(
                        "gate_vwap", time_pct=time_pct, side=side,
                        limit=limit_price, avg_fill=avg_fill,
                    )
                    continue

            # -- Order creation --
            worst_after = max(
                base_cost + dollar_size
                - self._inventory.net_shares_up
                - (shares if side == "UP" else 0),
                base_cost + dollar_size
                - self._inventory.net_shares_dn
                - (shares if side == "DN" else 0),
                0,
            )
            risk_pct = (
                worst_after / self._config.bar_budget * 100
                if self._config.bar_budget > 0
                else 0
            )
            reason = f"dutch pc={pair_cost:.3f} risk={risk_pct:.0f}%"

            order = DutchOrder(
                side=side,
                limit_price=round(limit_price, 4),
                shares=round(shares, 4),
                dollars=round(dollar_size, 2),
                time_pct=round(time_pct, 4),
                placed_at=datetime.now(UTC),
                reason=reason,
                order_mode=order_mode,
            )
            orders.append(order)
            budget_remaining -= dollar_size
            self._order_count += 1
            self._prediction_spend += dollar_size
            self._committed_spend += dollar_size

            if side == "UP":
                self._last_order_time_pct_up = time_pct
            else:
                self._last_order_time_pct_dn = time_pct

            self._decision_log.append(
                f"t={time_pct:.2f}: BUY {side} [{order_mode}] {reason} "
                f"limit={limit_price:.4f} ${dollar_size:.2f}"
            )
            self._emit(
                "order", time_pct=time_pct, side=side, reason=reason,
                limit=limit_price, dollars=dollar_size, mode=order_mode,
            )
            # NO break — both sides can buy per tick

        # ============================================================
        # Phase F: Three-phase sell
        # ============================================================
        return self._sell_pass(time_pct, cal_prob, book_up, book_dn, orders)

    def _sell_pass(
        self,
        time_pct: float,
        cal_prob: float,
        book_up,
        book_dn,
        orders: list[DutchOrder],
    ) -> list[DutchOrder]:
        """V7 sell pass: three phases with conviction-influenced sizing.

        Phase 1 (t < sell_loss_start): profit-only (bid > avg_cost)
        Phase 2 (sell_loss_start <= t < sell_dump_start): loss sells when conviction < 0.50
        Phase 3 (t >= sell_dump_start): sell at any price > $0.01
        """
        buy_side = orders[0].side if orders else None
        warmup_for_sell = (
            self._inventory.total_cost
            >= self._config.bar_budget * self._config.rebalance_warmup
        )
        sell_cooldown = 0.005
        sell_on_cooldown = (
            (time_pct - self._last_sell_time_pct) < sell_cooldown
        )

        if not warmup_for_sell or sell_on_cooldown:
            return orders

        for side in ["UP", "DN"]:
            if side == buy_side:
                continue

            net_shares = (
                self._inventory.net_shares_up if side == "UP"
                else self._inventory.net_shares_dn
            )
            other_shares = (
                self._inventory.net_shares_dn if side == "UP"
                else self._inventory.net_shares_up
            )
            pending = (
                self._pending_sell_shares_up if side == "UP"
                else self._pending_sell_shares_dn
            )
            book = book_up if side == "UP" else book_dn

            available = net_shares - pending
            if available < self._config.sell_min_shares:
                continue

            # Never sell the lighter side
            if net_shares <= other_shares:
                continue

            if net_shares <= 0:
                continue
            avg_cost = (
                self._inventory.net_cost_up / self._inventory.net_shares_up
                if side == "UP"
                else self._inventory.net_cost_dn / self._inventory.net_shares_dn
            )

            # Conviction for this side
            conviction = self._conviction(side, cal_prob, book.best_ask, time_pct)

            # Phase 1: profit-only (t < sell_loss_start)
            if time_pct < self._config.sell_loss_start:
                if avg_cost <= 0 or book.best_bid <= avg_cost:
                    continue

            # Phase 2: conviction-gated loss sell
            elif time_pct < self._config.sell_dump_start:
                if conviction >= 0.50:
                    continue  # model+market still think this side might win
                if book.best_bid < 0.02:
                    continue

            # Phase 3: dump at any price
            else:
                if book.best_bid < 0.01:
                    continue

            # Conviction-influenced sell amount
            imbalance = net_shares - other_shares
            sell_fraction = (1.0 - conviction) * 0.75
            if time_pct >= self._config.sell_dump_start:
                sell_fraction = max(0.25, sell_fraction)
            sell_fraction = min(sell_fraction, 0.50)  # cap at 50%

            max_sellable = max(
                0,
                net_shares * self._config.sell_max_fraction - pending,
            )
            sell_shares = min(imbalance * sell_fraction, max_sellable)
            if sell_shares * book.best_bid < self._config.min_order_usd:
                continue

            is_profit = book.best_bid > avg_cost
            sell_order = DutchOrder(
                side=side,
                limit_price=round(book.best_bid, 4),
                shares=round(sell_shares, 4),
                dollars=round(sell_shares * book.best_bid, 2),
                time_pct=round(time_pct, 4),
                placed_at=datetime.now(UTC),
                reason=(
                    f"sell_{'profit' if is_profit else 'cut'} "
                    f"conv={conviction:.2f}"
                ),
                action="SELL",
            )
            orders.append(sell_order)
            self._decision_log.append(
                f"t={time_pct:.2f}: SELL {side} "
                f"{'profit' if is_profit else 'cut'} conv={conviction:.2f} "
                f"${sell_shares * book.best_bid:.2f}"
            )
            self._emit(
                "order", time_pct=time_pct, side=side,
                reason=sell_order.reason,
                limit=book.best_bid,
                dollars=sell_shares * book.best_bid,
            )
            self._last_sell_time_pct = time_pct
            if side == "UP":
                self._pending_sell_shares_up += sell_shares
            else:
                self._pending_sell_shares_dn += sell_shares
            break  # one sell per tick

        return orders

    def on_fill(
        self,
        order: DutchOrder,
        fill_price: float,
        filled_shares: float,
    ) -> None:
        """Update inventory when a limit order fills."""
        cost = filled_shares * fill_price
        action = getattr(order, "action", "BUY")

        # Release committed spend (order is no longer inflight)
        if action == "BUY":
            self._committed_spend = max(
                0, self._committed_spend - order.dollars,
            )

        if action == "SELL":
            # V5: Sell — track revenue and sold shares
            if order.side == "UP":
                self._inventory.sell_revenue_up += cost
                self._inventory.sold_shares_up += filled_shares
                # Release full reservation (partial fills remove order entirely)
                self._pending_sell_shares_up = max(0, self._pending_sell_shares_up - order.shares)
            else:
                self._inventory.sell_revenue_dn += cost
                self._inventory.sold_shares_dn += filled_shares
                self._pending_sell_shares_dn = max(0, self._pending_sell_shares_dn - order.shares)
        else:
            # Buy — existing logic
            if order.side == "UP":
                self._inventory.shares_up += filled_shares
                self._inventory.cost_up += cost
            else:
                self._inventory.shares_dn += filled_shares
                self._inventory.cost_dn += cost
            # V7.4: Track first buy fill for resting fallback
            if not self._first_buy_filled:
                self._first_buy_filled = True

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

    def on_order_cancelled(self, order: DutchOrder) -> None:
        """Release reservations when order is cancelled/expired."""
        action = getattr(order, "action", "BUY")
        if action == "SELL":
            if order.side == "UP":
                self._pending_sell_shares_up = max(0, self._pending_sell_shares_up - order.shares)
            else:
                self._pending_sell_shares_dn = max(0, self._pending_sell_shares_dn - order.shares)
        else:
            # Release committed buy spend
            self._committed_spend = max(
                0, self._committed_spend - order.dollars,
            )

    def resolve(self, outcome: str) -> DutchBarSummary:
        """Compute PnL at bar end and return summary."""
        inv = self._inventory
        matched = inv.matched
        unmatched_up = max(0, inv.net_shares_up - inv.net_shares_dn)
        unmatched_dn = max(0, inv.net_shares_dn - inv.net_shares_up)

        summary = DutchBarSummary(
            bar_id=self._bar_id,
            window_start=self._window_start,
            window_end=self._window_end,
            condition_id=self._condition_id,
            orders=list(self._orders),
            inventory={
                "up_shares": round(inv.net_shares_up, 4),
                "dn_shares": round(inv.net_shares_dn, 4),
                "matched": round(matched, 4),
                "unmatched_up": round(unmatched_up, 4),
                "unmatched_dn": round(unmatched_dn, 4),
                "sold_up": round(inv.sold_shares_up, 4),
                "sold_dn": round(inv.sold_shares_dn, 4),
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
        self._flip_killed = False
        self._mid_range_up.clear()
        self._spreads_up.clear()
        self._spreads_dn.clear()
        self._bar_id = 0
        self._condition_id = ""
        self._window_start = ""
        self._window_end = ""

        # Pacing state (R1/R2/R4)
        self._last_order_time_pct_up = -1.0
        self._last_order_time_pct_dn = -1.0
        self._current_cal_prob = None
        self._prediction_spend = 0.0
        self._committed_spend = 0.0
        self._last_allowed_spend = 0.0
        self._last_sell_time_pct = -1.0
        self._pending_sell_shares_up = 0.0
        self._pending_sell_shares_dn = 0.0
        self._last_gate_emitted.clear()

        # V6 state
        self._last_ask_up = 0.0
        self._last_ask_dn = 0.0

        # V7.4 state
        self._first_buy_filled = False

        # V6.1 state
        self._last_time_pct = 0.0

        # V7 state
        self._conviction_up = 0.5
        self._conviction_dn = 0.5

    def snapshot(self) -> dict:
        """Current state for live display."""
        inv = self._inventory
        matched = inv.matched
        return {
            "shares_up": round(inv.net_shares_up, 4),
            "shares_dn": round(inv.net_shares_dn, 4),
            "cost_up": round(inv.net_cost_up, 4),
            "cost_dn": round(inv.net_cost_dn, 4),
            "matched": round(matched, 4),
            "avg_pair_cost": round(inv.avg_pair_cost, 4),
            "total_cost": round(inv.total_cost, 4),
            "budget_remaining": round(
                self._config.bar_budget - inv.total_cost, 4,
            ),
            "unmatched_up": round(max(0, inv.net_shares_up - inv.net_shares_dn), 4),
            "unmatched_dn": round(max(0, inv.net_shares_dn - inv.net_shares_up), 4),
            "pnl_if_up": round(inv.pnl_if_up, 4),
            "pnl_if_dn": round(inv.pnl_if_dn, 4),
            "worst_case_pnl": round(inv.worst_case_pnl, 4),
            "risk_budget": round(self._risk_budget(self._last_time_pct), 2),
            "worst_case_loss": round(max(-inv.worst_case_pnl, 0), 2),
            "conviction_up": round(self._conviction_up, 3),
            "conviction_dn": round(self._conviction_dn, 3),
            "effective_max_pc": round(self._effective_max_pair_cost(), 4),
            "pair_cost_live": round(self._last_ask_up + self._last_ask_dn, 4),
            "orders_count": len(self._orders),
            "last_decisions": self._decision_log[-5:],
            "allowed_spend": round(self._last_allowed_spend, 2),
            "prediction_spend": round(self._prediction_spend, 2),
            "max_per_prediction": self._config.max_per_prediction,
            "side_cap": round(
                self._config.bar_budget * self._config.max_side_fraction, 2,
            ),
            "avg_fill_up": (
                round(inv.net_cost_up / inv.net_shares_up, 4)
                if inv.net_shares_up > 0 else 0
            ),
            "avg_fill_dn": (
                round(inv.net_cost_dn / inv.net_shares_dn, 4)
                if inv.net_shares_dn > 0 else 0
            ),
            "sold_up": round(inv.sold_shares_up, 1),
            "sold_dn": round(inv.sold_shares_dn, 1),
            "sell_revenue": round(
                inv.sell_revenue_up + inv.sell_revenue_dn, 2,
            ),
            "share_match_pct": round(
                min(inv.net_shares_up, inv.net_shares_dn)
                / max(inv.net_shares_up, inv.net_shares_dn) * 100, 1,
            ) if max(inv.net_shares_up, inv.net_shares_dn) > 0 else 0,
        }
