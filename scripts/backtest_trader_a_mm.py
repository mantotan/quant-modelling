#!/usr/bin/env python
"""Backtest trader_a-style market maker on BTC 5m Polymarket.

Replays tick data and simulates a bilateral maker strategy that:
  1. Posts limit bids on BOTH Up and Down books (never crosses spread)
  2. Uses Pulse model to set fair value and derive limit prices
  3. Buys the contrarian side: Up when spot dips, Down when spot rallies
  4. Goal: combined cost basis < $1.00 per share pair = guaranteed profit
  5. Stops quoting after 70% of bar elapsed
  6. Rebalances via sells when one side gets too heavy

Based on dutch_backtest.py replay loop, but replaces the DutchAccumulationEngine
with a simpler market-maker logic that matches trader_a's observed behavior.

Usage:
    uv run python scripts/backtest_trader_a_mm.py --verbose
    uv run python scripts/backtest_trader_a_mm.py --date 2026-03-22
    uv run python scripts/backtest_trader_a_mm.py --output data/analysis/trader_a/mm_backtest.csv
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, date as date_type, datetime, timezone
from pathlib import Path

import lightgbm as lgb
import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from qm.core.types import Asset, PartialBar, Timeframe  # noqa: E402
from qm.data.connectors.polymarket_ws import TokenBook  # noqa: E402
from qm.data.ingestion.bar_builder import BarBuilder  # noqa: E402
from qm.data.storage.parquet import ParquetStore  # noqa: E402
from qm.features.live_cache import LiveFeatureCache  # noqa: E402
from qm.features.pipeline import FeaturePipeline  # noqa: E402
from qm.model.calibration.calibrator import TimeAwareCalibrator  # noqa: E402
from qm.strategy.dutch.engine import DutchOrder  # noqa: E402
from qm.strategy.dutch.fill_simulator import LimitOrderSimulator  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("mm_backtest")

BAR_SECONDS = 300.0  # 5m


# ---------------------------------------------------------------------------
# Market Maker Config
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class MMConfig:
    """trader_a-style market maker configuration."""

    # Budget
    bar_budget: float = 200.0           # max $ per bar
    order_size_usd: float = 2.0         # smaller orders = better inventory control

    # Pricing: market-based (like trader_a — price off the book, not the model)
    # bid = market_bid (join the bid, don't cross the spread)
    # The KEY constraint: bid_up + bid_dn < target_pair_cost
    target_pair_cost: float = 0.94      # target combined cost < 94c (6% profit/pair)
    min_bid_price: float = 0.05         # never bid below 5c
    max_bid_price: float = 0.75         # never bid above 75c

    # Pair cost guard: only place orders if ask_up + ask_dn < this
    max_pair_ask: float = 1.08          # wider: we bid below ask anyway

    # Timing
    max_elapsed_pct: float = 0.72       # stop quoting at 72% (like trader_a)
    min_elapsed_pct: float = 0.005      # start after 0.5% (~1.5s)
    order_interval_sec: float = 1.0     # faster order cadence for tighter control

    # Inventory management
    max_side_pct: float = 0.55          # max 55% of budget on one side
    max_position_shares: float = 400.0  # max shares per side
    max_onesided_cost: float = 5.0      # max $ on one side before ANY matched pair
    max_imbalance_shares: float = 20.0  # tight: max 20 shares difference

    # Sell rebalancing
    sell_imbalance_ratio: float = 1.5   # sell heavy side if > 1.5x the light side
    sell_fraction: float = 0.30         # sell 30% of imbalance
    sell_min_profit: float = 0.00       # sell at cost or better (not profit-only)
    sell_dump_time: float = 0.80        # dump any price after 80%

    # Fill simulator
    fill_ticks: int = 5                 # fast fills (aggressive maker)
    chase_threshold: float = 0.03       # moderate chase
    max_chase: int = 1                  # minimal chasing
    cancel_distance: float = 0.04       # cancel drifted orders quickly
    sweep_threshold: float = 0.01       # instant fill on sweep


# ---------------------------------------------------------------------------
# Market Maker Engine
# ---------------------------------------------------------------------------
@dataclass
class MMInventory:
    """Track bilateral inventory."""

    shares_up: float = 0.0
    shares_dn: float = 0.0
    cost_up: float = 0.0
    cost_dn: float = 0.0
    sold_shares_up: float = 0.0
    sold_shares_dn: float = 0.0
    sell_revenue_up: float = 0.0
    sell_revenue_dn: float = 0.0

    @property
    def net_up(self) -> float:
        return self.shares_up - self.sold_shares_up

    @property
    def net_dn(self) -> float:
        return self.shares_dn - self.sold_shares_dn

    @property
    def net_cost_up(self) -> float:
        return self.cost_up - self.sell_revenue_up

    @property
    def net_cost_dn(self) -> float:
        return self.cost_dn - self.sell_revenue_dn

    @property
    def total_cost(self) -> float:
        return self.net_cost_up + self.net_cost_dn

    @property
    def matched(self) -> float:
        return min(max(0, self.net_up), max(0, self.net_dn))

    @property
    def avg_cost_up(self) -> float:
        return self.cost_up / self.shares_up if self.shares_up > 0 else 0.0

    @property
    def avg_cost_dn(self) -> float:
        return self.cost_dn / self.shares_dn if self.shares_dn > 0 else 0.0

    @property
    def avg_pair_cost(self) -> float:
        if self.matched <= 0:
            return 0.0
        return self.avg_cost_up + self.avg_cost_dn


class MarketMakerEngine:
    """trader_a-style bilateral market maker.

    Core logic:
    1. Compute model fair value P(up)
    2. Derive bid prices: bid_up = fair_up - buffer, bid_dn = fair_dn - buffer
    3. Post limit orders on both sides
    4. Track inventory, rebalance via sells
    5. Stop at max_elapsed_pct
    """

    def __init__(self, config: MMConfig) -> None:
        self.cfg = config
        self.inv = MMInventory()
        self._last_order_time: float = -999.0
        self._orders_placed: int = 0

    def reset(self) -> None:
        self.inv = MMInventory()
        self._last_order_time = -999.0
        self._orders_placed = 0

    def on_tick(
        self,
        time_pct: float,
        cal_prob: float,
        book_up: TokenBook,
        book_dn: TokenBook,
        spot_price: float,
        open_price: float,
    ) -> list[DutchOrder]:
        """Generate limit orders for this tick. Returns list of DutchOrder."""
        orders: list[DutchOrder] = []

        # -- Timing gates --
        if time_pct < self.cfg.min_elapsed_pct:
            return orders
        if time_pct > self.cfg.max_elapsed_pct:
            # After cutoff: only sells (rebalancing)
            return self._maybe_sell(time_pct, cal_prob, book_up, book_dn)

        # -- Order interval pacing --
        elapsed_sec = time_pct * BAR_SECONDS
        if elapsed_sec - self._last_order_time < self.cfg.order_interval_sec:
            return self._maybe_sell(time_pct, cal_prob, book_up, book_dn)

        # -- Budget gate --
        if self.inv.total_cost >= self.cfg.bar_budget:
            return self._maybe_sell(time_pct, cal_prob, book_up, book_dn)

        # -- Pair cost gate --
        ask_up = book_up.best_ask if book_up and book_up.best_ask > 0 else 1.0
        ask_dn = book_dn.best_ask if book_dn and book_dn.best_ask > 0 else 1.0
        pair_ask = ask_up + ask_dn
        if pair_ask > self.cfg.max_pair_ask:
            return self._maybe_sell(time_pct, cal_prob, book_up, book_dn)

        # -- Market-based pricing (trader_a's approach) --
        # Only quote when there's real spread to capture.
        # Place bids BELOW the market bid by a small discount.
        mkt_bid_up = book_up.best_bid if book_up and book_up.best_bid > 0 else 0.0
        mkt_bid_dn = book_dn.best_bid if book_dn and book_dn.best_bid > 0 else 0.0
        mkt_ask_up = book_up.best_ask if book_up and book_up.best_ask > 0 else 1.0
        mkt_ask_dn = book_dn.best_ask if book_dn and book_dn.best_ask > 0 else 1.0

        # Check if there's enough spread to profit
        # If bid_up + bid_dn is already >= target, NO opportunity — skip
        if mkt_bid_up + mkt_bid_dn >= self.cfg.target_pair_cost:
            return self._maybe_sell(time_pct, cal_prob, book_up, book_dn)

        # Place at market bid (join queue for priority)
        bid_up = mkt_bid_up
        bid_dn = mkt_bid_dn

        # Never at or above the ask
        bid_up = min(bid_up, mkt_ask_up - 0.01)
        bid_dn = min(bid_dn, mkt_ask_dn - 0.01)

        # Clamp
        bid_up = max(self.cfg.min_bid_price, min(bid_up, self.cfg.max_bid_price))
        bid_dn = max(self.cfg.min_bid_price, min(bid_dn, self.cfg.max_bid_price))

        # Double-check combined < target after clamping
        combined = bid_up + bid_dn
        if combined >= self.cfg.target_pair_cost:
            scale = (self.cfg.target_pair_cost - 0.02) / combined
            bid_up = round(bid_up * scale, 2)
            bid_dn = round(bid_dn * scale, 2)
        else:
            bid_up = round(bid_up, 2)
            bid_dn = round(bid_dn, 2)

        now = datetime.now(UTC)

        # -- Model-weighted sizing (model for conviction, market for price) --
        fair_up = cal_prob
        fair_dn = 1.0 - cal_prob
        base_shares_up = self.cfg.order_size_usd / max(bid_up, 0.01)
        base_shares_dn = self.cfg.order_size_usd / max(bid_dn, 0.01)

        # Scale by model conviction: favored side gets 1.2x, unfavored gets 0.8x
        up_mult = 0.8 + 0.4 * fair_up   # range: 0.8 (model 0%) to 1.2 (model 100%)
        dn_mult = 0.8 + 0.4 * fair_dn
        shares_up = round(base_shares_up * up_mult, 2)
        shares_dn = round(base_shares_dn * dn_mult, 2)

        # -- Side budget gate + imbalance gate --
        max_cost_per_side = self.cfg.bar_budget * self.cfg.max_side_pct
        net_up = max(0, self.inv.net_up)
        net_dn = max(0, self.inv.net_dn)
        matched = min(net_up, net_dn)

        # One-sided cost cap: stop buying if no matched pairs and cost too high
        onesided_up_block = (matched <= 0 and self.inv.net_cost_up > self.cfg.max_onesided_cost)
        onesided_dn_block = (matched <= 0 and self.inv.net_cost_dn > self.cfg.max_onesided_cost)

        # Imbalance gate: don't buy the heavy side if imbalance is too large
        imbalance_up_block = (net_up - net_dn) > self.cfg.max_imbalance_shares
        imbalance_dn_block = (net_dn - net_up) > self.cfg.max_imbalance_shares

        # Place UP order
        if (
            bid_up >= self.cfg.min_bid_price
            and self.inv.net_cost_up < max_cost_per_side
            and self.inv.net_up < self.cfg.max_position_shares
            and not onesided_up_block
            and not imbalance_up_block
        ):
            dollars_up = round(shares_up * bid_up, 2)
            orders.append(DutchOrder(
                side="UP",
                limit_price=bid_up,
                shares=shares_up,
                dollars=dollars_up,
                time_pct=time_pct,
                placed_at=now,
                reason=f"mm_bid fair={fair_up:.2f}",
                action="BUY",
                order_mode="reactive",
            ))

        # Place DOWN order
        if (
            bid_dn >= self.cfg.min_bid_price
            and self.inv.net_cost_dn < max_cost_per_side
            and self.inv.net_dn < self.cfg.max_position_shares
            and not onesided_dn_block
            and not imbalance_dn_block
        ):
            dollars_dn = round(shares_dn * bid_dn, 2)
            orders.append(DutchOrder(
                side="DN",
                limit_price=bid_dn,
                shares=shares_dn,
                dollars=dollars_dn,
                time_pct=time_pct,
                placed_at=now,
                reason=f"mm_bid fair={fair_dn:.2f}",
                action="BUY",
                order_mode="reactive",
            ))

        if orders:
            self._last_order_time = elapsed_sec
            self._orders_placed += len(orders)

        # Also check for sell opportunities
        sells = self._maybe_sell(time_pct, cal_prob, book_up, book_dn)
        orders.extend(sells)

        return orders

    def _maybe_sell(
        self,
        time_pct: float,
        cal_prob: float,
        book_up: TokenBook,
        book_dn: TokenBook,
    ) -> list[DutchOrder]:
        """Sell heavy side to rebalance or capture profit."""
        orders: list[DutchOrder] = []
        now = datetime.now(UTC)

        net_up = self.inv.net_up
        net_dn = self.inv.net_dn

        if net_up <= 0 and net_dn <= 0:
            return orders

        # Determine heavy/light side
        if net_up > net_dn * self.cfg.sell_imbalance_ratio and net_up > 10:
            # Sell Up to rebalance
            sell_shares = round((net_up - net_dn) * self.cfg.sell_fraction, 2)
            if sell_shares < 5:
                return orders
            bid_up = book_up.best_bid if book_up and book_up.best_bid > 0 else 0.0
            # Only sell for profit unless dumping
            if time_pct >= self.cfg.sell_dump_time or bid_up > self.inv.avg_cost_up + self.cfg.sell_min_profit:
                orders.append(DutchOrder(
                    side="UP",
                    limit_price=round(bid_up, 2),
                    shares=sell_shares,
                    dollars=round(sell_shares * bid_up, 2),
                    time_pct=time_pct,
                    placed_at=now,
                    reason="mm_rebal_sell",
                    action="SELL",
                ))

        elif net_dn > net_up * self.cfg.sell_imbalance_ratio and net_dn > 10:
            # Sell Down to rebalance
            sell_shares = round((net_dn - net_up) * self.cfg.sell_fraction, 2)
            if sell_shares < 5:
                return orders
            bid_dn = book_dn.best_bid if book_dn and book_dn.best_bid > 0 else 0.0
            if time_pct >= self.cfg.sell_dump_time or bid_dn > self.inv.avg_cost_dn + self.cfg.sell_min_profit:
                orders.append(DutchOrder(
                    side="DN",
                    limit_price=round(bid_dn, 2),
                    shares=sell_shares,
                    dollars=round(sell_shares * bid_dn, 2),
                    time_pct=time_pct,
                    placed_at=now,
                    reason="mm_rebal_sell",
                    action="SELL",
                ))

        return orders

    def on_fill(self, order: DutchOrder, fill_price: float, filled_shares: float) -> None:
        """Process a fill from the simulator."""
        is_sell = order.action == "SELL"

        if order.side == "UP":
            if is_sell:
                self.inv.sold_shares_up += filled_shares
                self.inv.sell_revenue_up += filled_shares * fill_price
            else:
                self.inv.shares_up += filled_shares
                self.inv.cost_up += filled_shares * fill_price
        else:
            if is_sell:
                self.inv.sold_shares_dn += filled_shares
                self.inv.sell_revenue_dn += filled_shares * fill_price
            else:
                self.inv.shares_dn += filled_shares
                self.inv.cost_dn += filled_shares * fill_price

    def resolve(self, outcome: str) -> dict:
        """Compute final PnL for this bar."""
        inv = self.inv
        net_up = inv.net_up
        net_dn = inv.net_dn
        total_cost = inv.total_cost

        if outcome == "UP":
            payout = net_up * 1.0  # Up shares pay $1
            # Down shares are worthless
        else:
            payout = net_dn * 1.0  # Down shares pay $1

        profit = payout - total_cost

        return {
            "outcome": outcome,
            "net_up": round(net_up, 2),
            "net_dn": round(net_dn, 2),
            "cost_up": round(inv.net_cost_up, 2),
            "cost_dn": round(inv.net_cost_dn, 2),
            "total_cost": round(total_cost, 2),
            "matched": round(inv.matched, 2),
            "avg_pair_cost": round(inv.avg_pair_cost, 4),
            "payout": round(payout, 2),
            "profit": round(profit, 2),
            "pnl_if_up": round(net_up - total_cost, 2),
            "pnl_if_dn": round(net_dn - total_cost, 2),
            "guaranteed": inv.avg_pair_cost > 0 and inv.avg_pair_cost < 1.0,
            "orders_placed": self._orders_placed,
        }


# ---------------------------------------------------------------------------
# Backtest harness (mirrors dutch_backtest.py replay loop)
# ---------------------------------------------------------------------------

def tick_to_books(row: dict) -> tuple[TokenBook, TokenBook]:
    """Reconstruct TokenBooks from tick BBO data."""
    book_up = TokenBook(token_id="replay_up")
    if row.get("depth_bid_up", 0) > 0:
        book_up.bids = {row["bid_up"]: row["depth_bid_up"]}
    if row.get("depth_ask_up", 0) > 0:
        book_up.asks = {row["ask_up"]: row["depth_ask_up"]}
    book_up.best_bid = row.get("bid_up", 0)
    book_up.best_ask = row.get("ask_up", 0)
    book_up.last_trade = row.get("mid_up", 0.5)

    book_dn = TokenBook(token_id="replay_dn")
    if row.get("depth_bid_dn", 0) > 0:
        book_dn.bids = {row["bid_dn"]: row["depth_bid_dn"]}
    if row.get("depth_ask_dn", 0) > 0:
        book_dn.asks = {row["ask_dn"]: row["depth_ask_dn"]}
    book_dn.best_bid = row.get("bid_dn", 0)
    book_dn.best_ask = row.get("ask_dn", 0)
    book_dn.last_trade = 1.0 - row.get("mid_up", 0.5)

    return book_up, book_dn


def run_backtest(
    ticks_dir: Path,
    model_dir: Path,
    mm_config: MMConfig,
    inference_interval: float,
    filter_date: date_type | None,
    verbose: bool,
) -> list[dict]:
    """Run MM backtest on BTC 5m. Returns list of per-bar results."""
    asset_enum = Asset.BTC
    tf_enum = Timeframe.M5
    asset = "BTC"
    tf_label = "5m"

    # -- Model --
    from qm.model.specialist import load_pulse_model
    sub_dir = model_dir / f"{asset}_{tf_label}"
    model = load_pulse_model(sub_dir)
    calibrator = TimeAwareCalibrator()
    calibrator.load(sub_dir / "calibrator.pkl")
    logger.info("Loaded model: %d trees", model.num_trees())

    # -- Feature cache --
    feat_cache = LiveFeatureCache.from_model_dir(
        sub_dir, asset=asset_enum, timeframe=tf_enum,
    )
    store = ParquetStore(base_dir=Path("data/raw/ohlcv"))
    pipeline = FeaturePipeline()
    bars_df = store.read_bars(asset_enum, tf_enum)
    if not bars_df.is_empty():
        featured = pipeline.compute(bars_df.tail(500))
        last_row = featured.row(-1, named=True)
        cache_dict = {
            name: float(val)
            for name in pipeline.feature_names
            if (val := last_row.get(name)) is not None
        }
        feat_cache.update_history(cache_dict)
        logger.info("Warm-up: cached %d features", len(cache_dict))

    # -- Bar builder --
    bar_builder = BarBuilder(assets=[asset_enum], timeframes=[tf_enum])

    # -- Load ticks --
    ticks_path = ticks_dir / f"asset={asset}" / f"timeframe={tf_label}"
    scan = pl.scan_parquet(str(ticks_path / "**/*.parquet"))
    scan = scan.filter(~pl.col("is_stale") & ~pl.col("is_heartbeat"))
    if filter_date is not None:
        scan = scan.filter(pl.col("ts").dt.date() == filter_date)
    ticks_df = scan.sort("ts").collect()
    logger.info("Loaded %d ticks (%d bars)", len(ticks_df), ticks_df["window_start"].n_unique())

    # -- Replay --
    engine = MarketMakerEngine(mm_config)
    sim = LimitOrderSimulator(
        fill_ticks=mm_config.fill_ticks,
        chase_threshold=mm_config.chase_threshold,
        max_chase=mm_config.max_chase,
        cancel_distance=mm_config.cancel_distance,
        sweep_threshold=mm_config.sweep_threshold,
    )

    recent_bars: list[dict] = []
    bar_results: list[dict] = []
    bar_groups = ticks_df.group_by("window_start", maintain_order=True)

    t0 = time.perf_counter()

    for (window_start,), bar_ticks in bar_groups:
        window_end = bar_ticks["window_end"][0]
        bar_secs = (window_end - window_start).total_seconds()
        if bar_secs <= 0:
            continue

        # Outcome
        first_spot = bar_ticks["spot_price"][0]
        last_spot = bar_ticks["spot_price"][-1]
        outcome = "UP" if last_spot > first_spot else "DN"

        # Reset
        engine.reset()
        sim.reset()

        last_inference_ts = None
        cal_prob = 0.5
        open_price = first_spot

        for tick in bar_ticks.iter_rows(named=True):
            ts = tick["ts"]
            elapsed = (ts - window_start).total_seconds()
            time_pct = min(elapsed / bar_secs, 1.0)

            # Feed BarBuilder
            completed = bar_builder.on_trade(
                asset_enum, tick["spot_price"], 0.001, ts,
            )
            for bar in completed:
                recent_bars.append({
                    "time": bar.timestamp,
                    "open": bar.open, "high": bar.high,
                    "low": bar.low, "close": bar.close,
                    "volume": bar.volume,
                    "trade_count": bar.trade_count,
                    "vwap": bar.vwap,
                })
                recent_bars[:] = recent_bars[-500:]
                if len(recent_bars) >= 20:
                    try:
                        bdf = pl.DataFrame(recent_bars)
                        featured = pipeline.compute(bdf)
                        last_row = featured.row(-1, named=True)
                        cache_dict = {
                            name: float(val)
                            for name in pipeline.feature_names
                            if (val := last_row.get(name)) is not None
                        }
                        feat_cache.update_history(cache_dict)
                    except Exception:
                        pass

            # Model inference at cadence
            if (
                last_inference_ts is None
                or (ts - last_inference_ts).total_seconds() >= inference_interval
            ):
                partial = bar_builder.get_partial_bar(asset_enum, tf_enum, now=ts)
                if partial is not None:
                    features = feat_cache.get_features(partial)
                    raw_prob = float(model.predict(features.reshape(1, -1))[0])
                    if calibrator:
                        cal_prob = float(calibrator.transform(
                            np.array([raw_prob]),
                            np.array([time_pct]),
                        )[0])
                    else:
                        cal_prob = raw_prob
                    last_inference_ts = ts

            # Books
            book_up, book_dn = tick_to_books(tick)

            # Engine -> orders
            orders = engine.on_tick(
                time_pct, cal_prob, book_up, book_dn,
                spot_price=tick["spot_price"],
                open_price=open_price,
            )
            for order in orders:
                sim.place(order)

            # Sim -> fills
            fills = sim.on_tick(time_pct, book_up, book_dn)
            for fill in fills:
                engine.on_fill(fill.order, fill.fill_price, fill.filled_shares)

        # Bar end: cancel + resolve
        sim.cancel_all()
        result = engine.resolve(outcome)
        result["window_start"] = str(window_start)
        result["fill_rate"] = (
            sim.stats.filled / max(sim.stats.placed, 1)
        )
        result["orders_filled"] = sim.stats.filled

        bar_results.append(result)

        if verbose:
            logger.info(
                "bar %s: %s | matched=%.0f pc=%.3f pnl=$%.2f fills=%d/%d guar=%s",
                window_start, outcome,
                result["matched"], result["avg_pair_cost"],
                result["profit"], sim.stats.filled, sim.stats.placed,
                result["guaranteed"],
            )

    elapsed_s = time.perf_counter() - t0
    logger.info("Backtest complete in %.1fs (%d bars)", elapsed_s, len(bar_results))
    return bar_results


def print_summary(results: list[dict]) -> None:
    """Print aggregate summary."""
    if not results:
        print("No results.")
        return

    n = len(results)
    profits = [r["profit"] for r in results]
    total_pnl = sum(profits)
    avg_pnl = total_pnl / n
    wins = sum(1 for p in profits if p > 0)
    losses = sum(1 for p in profits if p < 0)

    guaranteed = sum(1 for r in results if r["guaranteed"])
    with_matched = [r for r in results if r["matched"] > 0]
    avg_pair_cost = (
        np.mean([r["avg_pair_cost"] for r in with_matched])
        if with_matched else 0.0
    )
    avg_matched = np.mean([r["matched"] for r in results])
    avg_fill_rate = np.mean([r["fill_rate"] for r in results])

    # Drawdown
    cumulative = np.cumsum(profits)
    peak = np.maximum.accumulate(cumulative)
    drawdown = peak - cumulative
    max_dd = float(np.max(drawdown)) if len(drawdown) > 0 else 0.0

    # Scenario analysis
    pnl_if_up = [r["pnl_if_up"] for r in results]
    pnl_if_dn = [r["pnl_if_dn"] for r in results]
    both_positive = sum(1 for u, d in zip(pnl_if_up, pnl_if_dn) if u > 0 and d > 0)

    print("\n" + "=" * 80)
    print("MM BACKTEST SUMMARY (trader_a-style)")
    print("=" * 80)
    print(f"  Bars:              {n}")
    print(f"  Total PnL:         ${total_pnl:+.2f}")
    print(f"  Avg PnL/bar:       ${avg_pnl:+.2f}")
    print(f"  Win/Loss:          {wins}W / {losses}L ({wins/n*100:.0f}% win rate)")
    print(f"  Max drawdown:      ${max_dd:.2f}")
    print(f"  Avg pair cost:     ${avg_pair_cost:.4f}")
    print(f"  Avg matched pairs: {avg_matched:.1f}")
    print(f"  Avg fill rate:     {avg_fill_rate:.1%}")
    print(f"  Guaranteed profit: {guaranteed}/{n} bars ({guaranteed/n*100:.0f}%)")
    print(f"  Both-sides +EV:    {both_positive}/{n} bars ({both_positive/n*100:.0f}%)")

    # Per-outcome breakdown
    up_bars = [r for r in results if r["outcome"] == "UP"]
    dn_bars = [r for r in results if r["outcome"] == "DN"]
    print(f"\n  UP bars:  {len(up_bars)}  avg PnL=${np.mean([r['profit'] for r in up_bars]):+.2f}" if up_bars else "")
    print(f"  DN bars:  {len(dn_bars)}  avg PnL=${np.mean([r['profit'] for r in dn_bars]):+.2f}" if dn_bars else "")
    print("=" * 80)


def main() -> None:
    p = argparse.ArgumentParser(description="trader_a-style MM Backtest")
    p.add_argument("--ticks-dir", default="data/raw/polymarket_ticks")
    p.add_argument("--model-dir", default="data/models/pulse")
    p.add_argument("--date", default=None, help="Filter to date (YYYY-MM-DD)")
    p.add_argument("--output", default="data/analysis/trader_a/mm_backtest.csv")
    p.add_argument("--inference-interval", type=float, default=1.0)
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--bar-budget", type=float, default=200.0)
    p.add_argument("--target-pair-cost", type=float, default=0.94)
    p.add_argument("--max-elapsed", type=float, default=0.72)
    args = p.parse_args()

    config = MMConfig(
        bar_budget=args.bar_budget,
        target_pair_cost=args.target_pair_cost,
        max_elapsed_pct=args.max_elapsed,
    )

    filter_date = date_type.fromisoformat(args.date) if args.date else None

    results = run_backtest(
        ticks_dir=Path(args.ticks_dir),
        model_dir=Path(args.model_dir),
        mm_config=config,
        inference_interval=args.inference_interval,
        filter_date=filter_date,
        verbose=args.verbose,
    )

    # Save to CSV
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df = pl.DataFrame(results)
    df.write_csv(str(output_path))
    logger.info("Saved %d bar results to %s", len(results), output_path)

    print_summary(results)


if __name__ == "__main__":
    main()
