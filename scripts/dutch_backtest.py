#!/usr/bin/env python
"""Dutch accumulation backtest — replay recorded Polymarket tick data.

Replays tick Parquet from data/raw/polymarket_ticks/ through the exact same
DutchAccumulationEngine + LimitOrderSimulator pipeline used in live paper
trading (scripts/monitor_pulse.py --dutch).

Usage:
    uv run scripts/dutch_backtest.py --verbose --assets BTC --timeframes 15m
    uv run scripts/dutch_backtest.py --output autoresearch/dutch/backtest_results.tsv
    uv run scripts/dutch_backtest.py --save-bars --date 2026-03-21
    uv run scripts/dutch_backtest.py --knobs-dir autoresearch/dutch/ --pair BTC_5m --verbose
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import date as date_type
from pathlib import Path

import lightgbm as lgb
import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from qm.core.types import Asset, Timeframe  # noqa: E402
from qm.data.connectors.polymarket_ws import TokenBook  # noqa: E402
from qm.data.ingestion.bar_builder import BarBuilder  # noqa: E402
from qm.data.storage.parquet import ParquetStore  # noqa: E402
from qm.features.live_cache import LiveFeatureCache  # noqa: E402
from qm.features.pipeline import FeaturePipeline  # noqa: E402
from qm.model.calibration.calibrator import TimeAwareCalibrator  # noqa: E402
from qm.strategy.dutch.engine import (  # noqa: E402
    DutchAccumulationEngine,
    DutchBarSummary,
    DutchConfig,
)
from qm.strategy.dutch.fill_simulator import LimitOrderSimulator  # noqa: E402
from qm.strategy.dutch.summary_logger import DutchSummaryLogger  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("dutch_backtest")

# Mapping helpers
ASSET_MAP = {"BTC": Asset.BTC, "ETH": Asset.ETH, "SOL": Asset.SOL, "XRP": Asset.XRP}
TF_MAP = {"5m": Timeframe.M5, "15m": Timeframe.M15, "1h": Timeframe.H1}
BAR_SECONDS = {Timeframe.M5: 300.0, Timeframe.M15: 900.0, Timeframe.H1: 3600.0}


# -- CLI ------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Dutch Accumulation Backtest")
    p.add_argument(
        "--knobs", default="autoresearch/dutch/knobs.json",
        help="Shared knobs file (fallback if --knobs-dir not set)",
    )
    p.add_argument(
        "--knobs-dir", default=None,
        help="Directory with per-pair knobs_{ASSET}_{TF}.json files",
    )
    p.add_argument(
        "--pair", default=None,
        help="Run only this pair (e.g. BTC_5m). Default: all pairs.",
    )
    p.add_argument(
        "--ticks-dir", default="data/raw/polymarket_ticks",
        help="Root dir for Hive-partitioned tick Parquet",
    )
    p.add_argument(
        "--model-dir", default="data/models/pulse_v2",
        help="Model directory (default: data/models/pulse_v2)",
    )
    p.add_argument(
        "--assets", default="BTC,ETH,SOL,XRP",
        help="Comma-separated assets (default: BTC,ETH,SOL,XRP)",
    )
    p.add_argument(
        "--timeframes", default="5m,15m,1h",
        help="Comma-separated timeframes (default: 5m,15m,1h)",
    )
    p.add_argument("--date", default=None, help="Filter to specific date (YYYY-MM-DD)")
    p.add_argument(
        "--inference-interval", type=float, default=1.0,
        help="Seconds between model predictions (default: 1.0)",
    )
    p.add_argument("--output", default=None, help="TSV output file path")
    p.add_argument(
        "--save-bars", action="store_true",
        help="Write bar JSONL to data/dutch_backtest/",
    )
    p.add_argument("--verbose", action="store_true", help="Per-bar detail logging")
    return p.parse_args()


# -- Config loading (mirrors monitor_pulse.py:676-704) ---------------------

def _resolve_knobs_path(
    knobs_dir: Path | None, knobs_fallback: Path,
    asset: str, tf_label: str,
) -> Path:
    """Resolve knobs file: per-pair first, then shared fallback."""
    if knobs_dir:
        pair_path = knobs_dir / f"knobs_{asset}_{tf_label}.json"
        if pair_path.exists():
            return pair_path
    return knobs_fallback


def load_dutch_config(
    knobs_dir: Path | None, knobs_fallback: Path,
    asset: str, tf_label: str, tf: Timeframe,
) -> tuple[DutchConfig, dict]:
    """Load DutchConfig — tries per-pair file first, falls back to shared."""
    knobs_path = _resolve_knobs_path(knobs_dir, knobs_fallback, asset, tf_label)
    kwargs: dict = {"bar_seconds": BAR_SECONDS[tf]}
    sim_kwargs: dict = {}

    if knobs_path.exists():
        with open(knobs_path) as f:
            knobs = json.load(f)
        for key, val in knobs.items():
            if key.startswith("_") or key == "fill_simulator":
                continue
            if key in DutchConfig.__dataclass_fields__ and key != "bar_seconds":
                kwargs[key] = val
        sim_kwargs = knobs.get("fill_simulator", {})
        logger.info("Config loaded from %s", knobs_path)
    else:
        logger.warning("No knobs at %s — using defaults", knobs_path)

    return DutchConfig(**kwargs), sim_kwargs


# -- Model loading (mirrors monitor_pulse.py:140-160) ----------------------

def load_model(
    model_dir: Path, asset: str, tf_label: str,
) -> tuple[lgb.Booster | None, TimeAwareCalibrator | None]:
    """Load Pulse LightGBM model + calibrator. Returns (None, None) if missing."""
    model_path = model_dir / f"{asset}_{tf_label}" / "model.lgb"
    cal_path = model_dir / f"{asset}_{tf_label}" / "calibrator.pkl"

    if not model_path.exists():
        logger.warning("No model at %s — skipping %s/%s", model_path, asset, tf_label)
        return None, None

    model = lgb.Booster(model_file=str(model_path))
    calibrator = None
    if cal_path.exists():
        calibrator = TimeAwareCalibrator()
        calibrator.load(cal_path)

    logger.info("Loaded %s_%s model (%d trees)", asset, tf_label, model.num_trees())
    return model, calibrator


# -- Feature warm-up (mirrors monitor_pulse.py:165-186) --------------------

def warm_up_cache(
    cache: LiveFeatureCache, asset_enum: Asset, tf: Timeframe,
) -> None:
    """Populate feature cache from historical bars."""
    store = ParquetStore(base_dir=Path("data/raw/ohlcv"))
    pipeline = FeaturePipeline()
    bars_df = store.read_bars(asset_enum, tf)
    if bars_df.is_empty():
        logger.warning("No OHLCV data for %s/%s warm-up", asset_enum.value, tf.value)
        return

    n = min(500, len(bars_df))
    featured = pipeline.compute(bars_df.tail(n))
    last_row = featured.row(-1, named=True)
    cache_dict = {}
    for name in pipeline.feature_names:
        val = last_row.get(name)
        if val is not None:
            cache_dict[name] = float(val)

    cache.update_history(cache_dict)
    logger.info(
        "Warm-up %s/%s: cached %d features from %d bars",
        asset_enum.value, tf.value, len(cache_dict), n,
    )


# -- TokenBook reconstruction from BBO tick data --------------------------

def tick_to_books(row: dict) -> tuple[TokenBook, TokenBook]:
    """Reconstruct single-level TokenBooks from tick BBO data."""
    book_up = TokenBook(token_id="replay_up")
    if row["depth_bid_up"] > 0:
        book_up.bids = {row["bid_up"]: row["depth_bid_up"]}
    if row["depth_ask_up"] > 0:
        book_up.asks = {row["ask_up"]: row["depth_ask_up"]}
    book_up.best_bid = row["bid_up"]
    book_up.best_ask = row["ask_up"]
    book_up.last_trade = row["mid_up"]

    book_dn = TokenBook(token_id="replay_dn")
    if row["depth_bid_dn"] > 0:
        book_dn.bids = {row["bid_dn"]: row["depth_bid_dn"]}
    if row["depth_ask_dn"] > 0:
        book_dn.asks = {row["ask_dn"]: row["depth_ask_dn"]}
    book_dn.best_bid = row["bid_dn"]
    book_dn.best_ask = row["ask_dn"]
    book_dn.last_trade = 1.0 - row["mid_up"]

    return book_up, book_dn


# -- Metrics computation (same 9 metrics as dutch-researcher Phase 2) ------

def _compute_correct_side_pct(summaries: list[DutchBarSummary]) -> float:
    """Fraction of bars where unmatched lean matched the outcome."""
    correct = 0
    total = 0
    for s in summaries:
        unm_up = s.inventory.get("unmatched_up", 0)
        unm_dn = s.inventory.get("unmatched_dn", 0)
        if unm_up == 0 and unm_dn == 0:
            continue
        total += 1
        if unm_up > unm_dn and s.outcome == "UP":
            correct += 1
        elif unm_dn > unm_up and s.outcome == "DN":
            correct += 1
    return correct / total if total > 0 else 0.0


def _compute_sell_ratio(summaries: list[DutchBarSummary]) -> float:
    """Sell orders / buy orders across all bars."""
    buys = 0
    sells = 0
    for s in summaries:
        for o in s.orders:
            if o.get("action", "BUY") == "SELL":
                sells += 1
            else:
                buys += 1
    return sells / max(buys, 1)


def _compute_max_drawdown_pct(summaries: list[DutchBarSummary], bar_budget: float) -> float:
    """Max drawdown as % of bar_budget from running equity curve."""
    if not summaries or bar_budget <= 0:
        return 0.0
    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0
    for s in summaries:
        profit = s.pnl.get("profit", 0)
        cumulative += profit
        peak = max(peak, cumulative)
        dd = peak - cumulative
        max_dd = max(max_dd, dd)
    return (max_dd / bar_budget) * 100


def compute_metrics(summaries: list[DutchBarSummary], bar_budget: float) -> dict:
    """Compute the 10 standard evaluation metrics."""
    resolved = [s for s in summaries if s.pnl]
    with_matched = [s for s in resolved if s.inventory.get("matched", 0) > 0]

    if not resolved:
        return {"bars_evaluated": 0}

    def safe_mean(values: list) -> float:
        return sum(values) / len(values) if values else 0.0

    return {
        "avg_pair_cost": safe_mean(
            [s.cost["avg_pair_cost"] for s in with_matched],
        ),
        "avg_profit": safe_mean([s.pnl["profit"] for s in resolved]),
        "total_profit": sum(s.pnl["profit"] for s in resolved),
        "matched_ratio": safe_mean([
            s.inventory["matched"]
            / max(s.inventory["up_shares"], s.inventory["dn_shares"], 0.01)
            for s in resolved
        ]),
        "fill_rate": safe_mean([
            s.fill_stats["orders_filled"]
            / max(s.fill_stats["orders_placed"], 1)
            for s in resolved
        ]),
        "correct_side_pct": _compute_correct_side_pct(resolved),
        "budget_util": safe_mean([s.cost["total"] / bar_budget for s in resolved]),
        "sell_ratio": _compute_sell_ratio(resolved),
        "max_dd_pct": round(_compute_max_drawdown_pct(resolved, bar_budget), 2),
        "bars_evaluated": len(resolved),
    }


# -- Per-(asset, timeframe) backtest ---------------------------------------

def run_backtest(
    asset: str,
    tf_label: str,
    knobs_dir: Path | None,
    knobs_fallback: Path,
    ticks_dir: Path,
    model_dir: Path,
    inference_interval: float,
    save_bars: bool,
    verbose: bool,
    filter_date: date_type | None,
) -> dict:
    """Run backtest for one (asset, timeframe) pair. Returns metrics dict."""
    asset_enum = ASSET_MAP[asset]
    tf_enum = TF_MAP[tf_label]

    # -- Config --
    config, sim_kwargs = load_dutch_config(
        knobs_dir, knobs_fallback, asset, tf_label, tf_enum,
    )

    # -- Model --
    model, calibrator = load_model(model_dir, asset, tf_label)
    if model is None:
        return {"bars_evaluated": 0, "skipped": True}

    # -- Feature cache --
    cache_dir = model_dir / f"{asset}_{tf_label}"
    feat_cache = LiveFeatureCache.from_model_dir(
        cache_dir, asset=asset_enum, timeframe=tf_enum,
    )
    warm_up_cache(feat_cache, asset_enum, tf_enum)

    # -- BarBuilder --
    bar_builder = BarBuilder(assets=[asset_enum], timeframes=[tf_enum])

    # -- Feature pipeline for inter-bar updates --
    pipeline = FeaturePipeline()

    # -- Load tick data --
    ticks_path = ticks_dir / f"asset={asset}" / f"timeframe={tf_label}"
    if not ticks_path.exists():
        logger.warning("No tick dir at %s — skipping", ticks_path)
        return {"bars_evaluated": 0, "skipped": True}

    scan = pl.scan_parquet(str(ticks_path / "**/*.parquet"))
    scan = scan.filter(~pl.col("is_stale") & ~pl.col("is_heartbeat"))
    if filter_date is not None:
        scan = scan.filter(pl.col("ts").dt.date() == filter_date)
    ticks_df = scan.sort("ts").collect()

    if ticks_df.is_empty():
        logger.warning("No ticks for %s/%s — skipping", asset, tf_label)
        return {"bars_evaluated": 0, "skipped": True}

    logger.info(
        "Loaded %d ticks for %s/%s (%d unique bars)",
        len(ticks_df), asset, tf_label,
        ticks_df["window_start"].n_unique(),
    )

    # -- Engine + simulator --
    engine = DutchAccumulationEngine(config)
    sim = LimitOrderSimulator(**sim_kwargs) if sim_kwargs else LimitOrderSimulator()

    # -- Optional JSONL logger --
    dutch_logger: DutchSummaryLogger | None = None
    if save_bars:
        dutch_logger = DutchSummaryLogger(
            base_dir=Path("data/dutch_backtest"),
            asset=asset,
            timeframe=tf_label,
        )
        engine.set_event_callback(dutch_logger.log_event)

    # -- Replay loop --
    recent_bars: list[dict] = []  # empty — matches paper trading (monitor_pulse.py:833)
    bar_summaries: list[DutchBarSummary] = []
    bar_groups = ticks_df.group_by("window_start", maintain_order=True)

    t0 = time.perf_counter()

    for (window_start,), bar_ticks in bar_groups:
        window_end = bar_ticks["window_end"][0]
        condition_id = bar_ticks["condition_id"][0]
        bar_id = int(window_start.timestamp())
        bar_secs = (window_end - window_start).total_seconds()

        if bar_secs <= 0:
            continue

        # Outcome from spot price (first vs last)
        first_spot = bar_ticks["spot_price"][0]
        last_spot = bar_ticks["spot_price"][-1]
        if last_spot > first_spot:
            outcome = "UP"
        elif last_spot < first_spot:
            outcome = "DN"
        else:
            outcome = "DN"  # no movement → DN (Polymarket: "not up")

        # Reset (same as live bar boundary)
        engine.reset()
        sim.reset()
        engine.set_bar_info(
            bar_id=bar_id,
            condition_id=condition_id,
            window_start=str(window_start),
            window_end=str(window_end),
        )

        last_inference_ts = None
        cal_prob = 0.5

        for tick in bar_ticks.iter_rows(named=True):
            ts = tick["ts"]
            elapsed = (ts - window_start).total_seconds()
            time_pct = min(elapsed / bar_secs, 1.0)

            # Feed spot into BarBuilder
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
                # Update feature cache (mirrors monitor_pulse.py:889-899)
                if len(recent_bars) >= 20:
                    try:
                        bars_df = pl.DataFrame(recent_bars)
                        featured = pipeline.compute(bars_df)
                        last_row = featured.row(-1, named=True)
                        cache_dict = {
                            name: float(val)
                            for name in pipeline.feature_names
                            if (val := last_row.get(name)) is not None
                        }
                        feat_cache.update_history(cache_dict)
                    except Exception:
                        pass  # non-fatal: stale features better than crash

            # Model inference at cadence (1Hz default)
            if (
                last_inference_ts is None
                or (ts - last_inference_ts).total_seconds() >= inference_interval
            ):
                partial = bar_builder.get_partial_bar(
                    asset_enum, tf_enum, now=ts,
                )
                if partial is not None:
                    features = feat_cache.get_features(partial)
                    raw_prob = float(
                        model.predict(features.reshape(1, -1))[0],
                    )
                    if calibrator:
                        cal_prob = float(calibrator.transform(
                            np.array([raw_prob]),
                            np.array([time_pct]),
                        )[0])
                    else:
                        cal_prob = raw_prob
                    last_inference_ts = ts

            # Reconstruct books from tick BBO
            book_up, book_dn = tick_to_books(tick)

            # Engine → orders → sim → fills → engine
            orders = engine.on_tick(time_pct, cal_prob, book_up, book_dn)
            for order in orders:
                sim.place(order)
            fills = sim.on_tick(time_pct, book_up, book_dn)
            for fill in fills:
                engine.on_fill(fill.order, fill.fill_price, fill.filled_shares)

        # -- Bar end: cancel + resolve (mirrors monitor_pulse.py:916-947) --
        cancelled = sim.cancel_all()
        for order in cancelled:
            engine.on_order_cancelled(order)

        summary = engine.resolve(outcome)
        summary.fill_stats = {
            "orders_placed": sim.stats.placed,
            "orders_filled": sim.stats.filled,
            "partial_fills": sim.stats.partial,
            "would_fill_count": sim.stats.would_fill,
            "avg_fill_ticks": round(sim.stats.avg_fill_ticks, 1),
            "chased": sim.stats.chased,
            "cancelled": sim.stats.cancelled,
            "expired": sim.stats.expired,
        }
        bar_summaries.append(summary)

        if save_bars and dutch_logger:
            dutch_logger.log_bar(summary)

        if verbose:
            profit = summary.pnl.get("profit", 0)
            pc = summary.cost.get("avg_pair_cost", 0)
            matched = summary.inventory.get("matched", 0)
            fills_n = summary.fill_stats.get("orders_filled", 0)
            logger.info(
                "%s/%s bar %s: %s matched=%.1f pc=%.3f pnl=$%.2f fills=%d",
                asset, tf_label, window_start, outcome,
                matched, pc, profit, fills_n,
            )

        # -- Inter-bar feature cache update (mirrors monitor_pulse.py:876-902) --
        recent_bars[:] = recent_bars[-500:]
        if len(recent_bars) >= 20:
            try:
                bars_data = {
                    "time": [b.timestamp for b in recent_bars],
                    "open": [b.open for b in recent_bars],
                    "high": [b.high for b in recent_bars],
                    "low": [b.low for b in recent_bars],
                    "close": [b.close for b in recent_bars],
                    "volume": [b.volume for b in recent_bars],
                    "trade_count": [b.trade_count for b in recent_bars],
                    "vwap": [b.vwap for b in recent_bars],
                }
                bars_df = pl.DataFrame(bars_data)
                featured = pipeline.compute(bars_df)
                last_row = featured.row(-1, named=True)
                cache_dict = {
                    name: float(val)
                    for name in pipeline.feature_names
                    if (val := last_row.get(name)) is not None
                }
                feat_cache.update_history(cache_dict)
            except Exception as e:
                logger.warning("Feature cache update failed: %s", e)

    elapsed_s = time.perf_counter() - t0

    if dutch_logger:
        dutch_logger.close()

    metrics = compute_metrics(bar_summaries, config.bar_budget)
    metrics["asset"] = asset
    metrics["timeframe"] = tf_label
    metrics["elapsed_s"] = round(elapsed_s, 2)

    logger.info(
        "%s/%s done: %d bars in %.1fs — pair_cost=%.3f profit=$%.2f",
        asset, tf_label, metrics.get("bars_evaluated", 0),
        elapsed_s,
        metrics.get("avg_pair_cost", 0),
        metrics.get("total_profit", 0),
    )

    return metrics


# -- Output ----------------------------------------------------------------

TSV_HEADER = (
    "asset\ttimeframe\tavg_pair_cost\tavg_profit\ttotal_profit\t"
    "matched_ratio\tfill_rate\tcorrect_side_pct\tbudget_util\t"
    "sell_ratio\tmax_dd_pct\tbars_evaluated"
)


def metrics_to_tsv_row(m: dict) -> str:
    """Format a metrics dict as a TSV row."""
    return (
        f"{m.get('asset', 'ALL')}\t{m.get('timeframe', 'ALL')}\t"
        f"{m.get('avg_pair_cost', 0):.4f}\t{m.get('avg_profit', 0):.4f}\t"
        f"{m.get('total_profit', 0):.4f}\t{m.get('matched_ratio', 0):.4f}\t"
        f"{m.get('fill_rate', 0):.4f}\t{m.get('correct_side_pct', 0):.4f}\t"
        f"{m.get('budget_util', 0):.4f}\t{m.get('sell_ratio', 0):.4f}\t"
        f"{m.get('max_dd_pct', 0):.2f}\t"
        f"{m.get('bars_evaluated', 0)}"
    )


def print_summary(all_metrics: list[dict]) -> None:
    """Print human-readable summary to stdout."""
    print("\n" + "=" * 90)
    print("  DUTCH BACKTEST RESULTS")
    print("=" * 90)
    print(f"\n  {'Asset':<6} {'TF':<4} {'PairCost':>9} {'AvgPnL':>9} {'TotalPnL':>10} "
          f"{'Match%':>7} {'Fill%':>6} {'Correct%':>9} {'BudgUse%':>9} "
          f"{'SellR':>6} {'MaxDD%':>7} {'Bars':>5} {'Time':>6}")
    print("  " + "-" * 96)
    for m in all_metrics:
        if m.get("skipped"):
            continue
        bars = m.get("bars_evaluated", 0)
        if bars == 0:
            continue
        print(
            f"  {m.get('asset', '?'):<6} {m.get('timeframe', '?'):<4} "
            f"{m.get('avg_pair_cost', 0):>9.4f} "
            f"{m.get('avg_profit', 0):>9.2f} "
            f"{m.get('total_profit', 0):>10.2f} "
            f"{m.get('matched_ratio', 0):>6.1%} "
            f"{m.get('fill_rate', 0):>5.1%} "
            f"{m.get('correct_side_pct', 0):>8.1%} "
            f"{m.get('budget_util', 0):>8.1%} "
            f"{m.get('sell_ratio', 0):>6.2f} "
            f"{m.get('max_dd_pct', 0):>6.1f}% "
            f"{bars:>5} "
            f"{m.get('elapsed_s', 0):>5.1f}s"
        )
    print("=" * 100)


# -- Main ------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    knobs_dir = Path(args.knobs_dir) if args.knobs_dir else None
    knobs_fallback = Path(args.knobs)
    ticks_dir = Path(args.ticks_dir)
    model_dir = Path(args.model_dir)

    # Parse --pair shorthand (e.g. BTC_5m → assets=BTC, timeframes=5m)
    if args.pair:
        parts = args.pair.split("_", 1)
        if len(parts) != 2 or parts[0] not in ASSET_MAP or parts[1] not in TF_MAP:
            logger.error("Invalid --pair '%s'. Format: ASSET_TF (e.g. BTC_5m)", args.pair)
            sys.exit(1)
        assets = [parts[0]]
        timeframes = [parts[1]]
    else:
        assets = [a.strip() for a in args.assets.split(",")]
        timeframes = [t.strip() for t in args.timeframes.split(",")]

    filter_date = None
    if args.date:
        filter_date = date_type.fromisoformat(args.date)

    print("=" * 60)
    print("  Dutch Accumulation Backtest")
    print("=" * 60)
    print(f"  Knobs:      {knobs_dir or knobs_fallback}")
    print(f"  Ticks:      {ticks_dir}")
    print(f"  Models:     {model_dir}")
    print(f"  Pair:       {args.pair or 'all'}")
    print(f"  Assets:     {assets}")
    print(f"  Timeframes: {timeframes}")
    print(f"  Date:       {filter_date or 'all'}")
    print(f"  Inference:  {args.inference_interval}s")
    print("=" * 60)

    all_metrics: list[dict] = []
    any_data = False

    for asset in assets:
        if asset not in ASSET_MAP:
            logger.warning("Unknown asset %s — skipping", asset)
            continue
        for tf_label in timeframes:
            if tf_label not in TF_MAP:
                logger.warning("Unknown timeframe %s — skipping", tf_label)
                continue

            metrics = run_backtest(
                asset=asset,
                tf_label=tf_label,
                knobs_dir=knobs_dir,
                knobs_fallback=knobs_fallback,
                ticks_dir=ticks_dir,
                model_dir=model_dir,
                inference_interval=args.inference_interval,
                save_bars=args.save_bars,
                verbose=args.verbose,
                filter_date=filter_date,
            )
            all_metrics.append(metrics)
            if metrics.get("bars_evaluated", 0) > 0:
                any_data = True

    # -- Aggregate "ALL" row --
    evaluated = [m for m in all_metrics if m.get("bars_evaluated", 0) > 0]
    if evaluated:
        total_bars = sum(m["bars_evaluated"] for m in evaluated)
        agg: dict = {
            "asset": "ALL",
            "timeframe": "ALL",
            "bars_evaluated": total_bars,
        }
        # Weighted averages by bars_evaluated
        for key in [
            "avg_pair_cost", "avg_profit", "matched_ratio",
            "fill_rate", "correct_side_pct", "budget_util", "sell_ratio",
            "max_dd_pct",
        ]:
            weighted = sum(
                m.get(key, 0) * m["bars_evaluated"] for m in evaluated
            )
            agg[key] = weighted / total_bars if total_bars > 0 else 0
        agg["total_profit"] = sum(m.get("total_profit", 0) for m in evaluated)
        agg["elapsed_s"] = round(sum(m.get("elapsed_s", 0) for m in evaluated), 2)
        all_metrics.append(agg)

    # -- Print summary --
    print_summary(all_metrics)

    # -- Write TSV --
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            f.write(TSV_HEADER + "\n")
            for m in all_metrics:
                if m.get("bars_evaluated", 0) > 0:
                    f.write(metrics_to_tsv_row(m) + "\n")
        logger.info("TSV written to %s", output_path)

    if not any_data:
        logger.error("No data found for any asset/timeframe combination")
        sys.exit(1)


if __name__ == "__main__":
    main()
