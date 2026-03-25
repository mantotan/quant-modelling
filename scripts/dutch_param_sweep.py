#!/usr/bin/env python
"""Dutch accumulation parameter sweep — quantify impact of parameter changes.

Runs the full dutch_backtest pipeline multiple times with different knob
configurations, collecting metrics for comparison. Outputs a TSV summary
and prints a ranked analysis.

Usage:
    uv run scripts/dutch_param_sweep.py --pair BTC_15m
    uv run scripts/dutch_param_sweep.py --pair BTC_15m --output sweep_results.tsv
"""

from __future__ import annotations

import argparse
import copy
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

from qm.core.types import Asset, PartialBar, Timeframe  # noqa: E402
from qm.data.connectors.polymarket_ws import TokenBook  # noqa: E402
from qm.data.ingestion.bar_builder import BarBuilder  # noqa: E402
from qm.data.storage.parquet import ParquetStore  # noqa: E402
from qm.features.live_cache import CrossAssetLiveFeatureCache, LiveFeatureCache  # noqa: E402
from qm.features.pipeline import FeaturePipeline  # noqa: E402
from qm.model.calibration.calibrator import TimeAwareCalibrator  # noqa: E402
from qm.strategy.dutch.engine import (  # noqa: E402
    DutchAccumulationEngine,
    DutchBarSummary,
    DutchConfig,
)
from qm.strategy.dutch.fill_simulator import LimitOrderSimulator  # noqa: E402

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("dutch_sweep")
logger.setLevel(logging.INFO)

ASSET_MAP = {"BTC": Asset.BTC, "ETH": Asset.ETH, "SOL": Asset.SOL, "XRP": Asset.XRP}
TF_MAP = {"5m": Timeframe.M5, "15m": Timeframe.M15, "1h": Timeframe.H1}
BAR_SECONDS = {Timeframe.M5: 300.0, Timeframe.M15: 900.0, Timeframe.H1: 3600.0}


# ---------------------------------------------------------------------------
# Precomputed bar data: run model inference once, replay engine many times
# ---------------------------------------------------------------------------

class PrecomputedBar:
    """One bar's worth of tick-level data with precomputed model predictions."""

    __slots__ = ("window_start", "window_end", "condition_id", "bar_id",
                 "bar_secs", "outcome", "ticks")

    def __init__(self):
        self.ticks: list[dict] = []  # Each: {time_pct, cal_prob, book_up, book_dn}


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


def precompute_bars(
    asset: str, tf_label: str, model_dir: Path,
    ticks_dir: Path, inference_interval: float = 1.0,
    filter_date: date_type | None = None,
) -> list[PrecomputedBar]:
    """Load ticks, run model inference, return precomputed bars for fast replay."""
    from qm.model.specialist import load_pulse_model

    asset_enum = ASSET_MAP[asset]
    tf_enum = TF_MAP[tf_label]

    # Load model
    sub_dir = model_dir / f"{asset}_{tf_label}"
    if not (sub_dir / "model.lgb").exists() and not (sub_dir / "specialist_config.json").exists():
        logger.error("No model at %s", sub_dir)
        return []

    model = load_pulse_model(sub_dir)
    calibrator = None
    from qm.model.specialist import SpecialistModelRouter
    if not isinstance(model, SpecialistModelRouter):
        cal_path = sub_dir / "calibrator.pkl"
        if cal_path.exists():
            calibrator = TimeAwareCalibrator()
            calibrator.load(cal_path)

    # Feature cache
    feat_cache = LiveFeatureCache.from_model_dir(
        sub_dir, asset=asset_enum, timeframe=tf_enum,
    )
    store = ParquetStore(base_dir=Path("data/raw/ohlcv"))
    pipeline = FeaturePipeline()
    bars_df = store.read_bars(asset_enum, tf_enum)
    if not bars_df.is_empty():
        n = min(500, len(bars_df))
        featured = pipeline.compute(bars_df.tail(n))
        last_row = featured.row(-1, named=True)
        cache_dict = {
            name: float(val) for name in pipeline.feature_names
            if (val := last_row.get(name)) is not None
        }
        feat_cache.update_history(cache_dict)

    # BTC cross-asset context
    btc_bars_dict: dict = {}
    if isinstance(feat_cache, CrossAssetLiveFeatureCache):
        btc_bars_df = store.read_bars(Asset.BTC, tf_enum)
        if not btc_bars_df.is_empty():
            for row in btc_bars_df.iter_rows(named=True):
                btc_bars_dict[row["time"]] = row
            btc_pipeline = FeaturePipeline()
            btc_featured = btc_pipeline.compute(btc_bars_df.tail(500))
            btc_last = btc_featured.row(-1, named=True)
            btc_hist = {
                n: float(v) for n in btc_pipeline.feature_names
                if (v := btc_last.get(n)) is not None
            }
            feat_cache.update_btc_history(btc_hist)

    # BarBuilder
    bar_builder = BarBuilder(assets=[asset_enum], timeframes=[tf_enum])

    # Load ticks
    ticks_path = ticks_dir / f"asset={asset}" / f"timeframe={tf_label}"
    if not ticks_path.exists():
        logger.error("No tick dir at %s", ticks_path)
        return []

    scan = pl.scan_parquet(str(ticks_path / "**/*.parquet"))
    scan = scan.filter(~pl.col("is_stale") & ~pl.col("is_heartbeat"))
    if filter_date is not None:
        scan = scan.filter(pl.col("ts").dt.date() == filter_date)
    ticks_df = scan.sort("ts").collect()

    if ticks_df.is_empty():
        logger.error("No ticks for %s/%s", asset, tf_label)
        return []

    logger.info(
        "Loaded %d ticks for %s/%s (%d bars)",
        len(ticks_df), asset, tf_label, ticks_df["window_start"].n_unique(),
    )

    # Process each bar
    recent_bars: list[dict] = []
    precomputed: list[PrecomputedBar] = []
    bar_groups = ticks_df.group_by("window_start", maintain_order=True)

    for (window_start,), bar_ticks in bar_groups:
        window_end = bar_ticks["window_end"][0]
        condition_id = bar_ticks["condition_id"][0]
        bar_id = int(window_start.timestamp())
        bar_secs = (window_end - window_start).total_seconds()
        if bar_secs <= 0:
            continue

        # Outcome
        first_spot = bar_ticks["spot_price"][0]
        last_spot = bar_ticks["spot_price"][-1]
        outcome = "UP" if last_spot > first_spot else "DN"

        pb = PrecomputedBar()
        pb.window_start = str(window_start)
        pb.window_end = str(window_end)
        pb.condition_id = condition_id
        pb.bar_id = bar_id
        pb.bar_secs = bar_secs
        pb.outcome = outcome

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
                    "time": bar.timestamp, "open": bar.open, "high": bar.high,
                    "low": bar.low, "close": bar.close, "volume": bar.volume,
                    "trade_count": bar.trade_count, "vwap": bar.vwap,
                })
                recent_bars[:] = recent_bars[-500:]
                if len(recent_bars) >= 20:
                    try:
                        bdf = pl.DataFrame(recent_bars)
                        featured = pipeline.compute(bdf)
                        last_row = featured.row(-1, named=True)
                        cd = {
                            name: float(val) for name in pipeline.feature_names
                            if (val := last_row.get(name)) is not None
                        }
                        feat_cache.update_history(cd)
                    except Exception:
                        pass

            # Model inference at cadence
            if (
                last_inference_ts is None
                or (ts - last_inference_ts).total_seconds() >= inference_interval
            ):
                if btc_bars_dict and isinstance(feat_cache, CrossAssetLiveFeatureCache):
                    btc_bar = btc_bars_dict.get(window_start)
                    if btc_bar is not None:
                        elapsed_sec = (ts - window_start).total_seconds()
                        feat_cache.set_btc_partial(PartialBar(
                            window_start=window_start, window_end=window_end,
                            asset=Asset.BTC, timeframe=tf_enum,
                            open=btc_bar["open"],
                            high_so_far=btc_bar["high"],
                            low_so_far=btc_bar["low"],
                            current_price=btc_bar["close"],
                            volume_so_far=btc_bar["volume"],
                            trade_count=btc_bar.get("trade_count", 0),
                            elapsed_seconds=elapsed_sec,
                            remaining_seconds=max(0.0, bar_secs - elapsed_sec),
                        ))

                partial = bar_builder.get_partial_bar(asset_enum, tf_enum, now=ts)
                if partial is not None:
                    features = feat_cache.get_features(partial)
                    raw_prob = float(model.predict(features.reshape(1, -1))[0])
                    if calibrator:
                        cal_prob = float(calibrator.transform(
                            np.array([raw_prob]), np.array([time_pct]),
                        )[0])
                    else:
                        cal_prob = raw_prob
                    last_inference_ts = ts

            # Store tick with precomputed probability
            book_up, book_dn = tick_to_books(tick)
            pb.ticks.append({
                "time_pct": time_pct,
                "cal_prob": cal_prob,
                "book_up": book_up,
                "book_dn": book_dn,
            })

        precomputed.append(pb)

        # Inter-bar feature update
        recent_bars[:] = recent_bars[-500:]

    logger.info("Precomputed %d bars", len(precomputed))
    return precomputed


# ---------------------------------------------------------------------------
# Fast replay: run engine with given config over precomputed bars
# ---------------------------------------------------------------------------

def replay_with_config(
    bars: list[PrecomputedBar],
    config: DutchConfig,
    sim_kwargs: dict | None = None,
    min_time_pct: float = 0.0,
    max_flips_kill: int = 0,
    prob_variance_gate: float = 0.0,
) -> dict:
    """Replay precomputed bars through engine with given config.

    Extra experimental gates (not in the engine, applied here):
      - min_time_pct: skip all ticks before this time fraction
      - max_flips_kill: stop buying after N model flips within a bar
      - prob_variance_gate: require model prob std > this to trade
    """
    sim_kw = sim_kwargs or {}
    all_summaries: list[DutchBarSummary] = []

    for pb in bars:
        engine = DutchAccumulationEngine(config)
        sim = LimitOrderSimulator(**sim_kw)
        engine.set_bar_info(
            bar_id=pb.bar_id,
            condition_id=pb.condition_id,
            window_start=pb.window_start,
            window_end=pb.window_end,
        )

        flip_count = 0
        prev_prob = None
        probs_seen: list[float] = []
        killed = False

        for tick_data in pb.ticks:
            time_pct = tick_data["time_pct"]
            cal_prob = tick_data["cal_prob"]
            book_up = tick_data["book_up"]
            book_dn = tick_data["book_dn"]

            # Track flips
            if prev_prob is not None and (prev_prob - 0.5) * (cal_prob - 0.5) < 0:
                flip_count += 1
            prev_prob = cal_prob
            probs_seen.append(cal_prob)

            # --- Experimental gate: min_time_pct ---
            if time_pct < min_time_pct:
                # Still feed ticks for sell passes, but use prob=0.5 to prevent buys
                # Actually, just skip entirely — engine won't see early ticks
                continue

            # --- Experimental gate: flip kill switch ---
            if max_flips_kill > 0 and flip_count >= max_flips_kill and not killed:
                killed = True
                # Cancel all pending orders
                cancelled = sim.cancel_all()
                for order in cancelled:
                    engine.on_order_cancelled(order)

            if killed:
                # Only process fills for already-placed orders
                fills = sim.on_tick(time_pct, book_up, book_dn)
                for fill in fills:
                    engine.on_fill(fill.order, fill.fill_price, fill.filled_shares)
                continue

            # --- Experimental gate: prob variance ---
            if prob_variance_gate > 0 and len(probs_seen) > 10:
                prob_std = np.std(probs_seen[-20:])
                if prob_std < prob_variance_gate:
                    continue

            # Normal engine processing
            orders = engine.on_tick(time_pct, cal_prob, book_up, book_dn)
            for order in orders:
                sim.place(order)
            fills = sim.on_tick(time_pct, book_up, book_dn)
            for fill in fills:
                engine.on_fill(fill.order, fill.fill_price, fill.filled_shares)

        # Bar end
        cancelled = sim.cancel_all()
        for order in cancelled:
            engine.on_order_cancelled(order)

        summary = engine.resolve(pb.outcome)
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
        all_summaries.append(summary)

    return compute_extended_metrics(all_summaries, config.bar_budget)


def compute_extended_metrics(
    summaries: list[DutchBarSummary], bar_budget: float,
) -> dict:
    """Compute metrics including win/loss breakdown."""
    resolved = [s for s in summaries if s.pnl]
    with_matched = [s for s in resolved if s.inventory.get("matched", 0) > 0]

    if not resolved:
        return {"bars_evaluated": 0}

    def safe_mean(values: list) -> float:
        return sum(values) / len(values) if values else 0.0

    profits = [s.pnl["profit"] for s in resolved]
    costs = [s.cost["total"] for s in resolved]
    wins = [p for p in profits if p > 0]
    losses = [p for p in profits if p < 0]
    active = [s for s in resolved if s.cost["total"] > 0]

    # Win rate (only on bars with orders)
    active_profits = [s.pnl["profit"] for s in active]
    active_wins = sum(1 for p in active_profits if p > 0)
    active_total = len(active_profits)

    # Max drawdown
    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in profits:
        cumulative += p
        peak = max(peak, cumulative)
        dd = peak - cumulative
        max_dd = max(max_dd, dd)

    return {
        "bars_evaluated": len(resolved),
        "bars_active": len(active),
        "total_profit": sum(profits),
        "avg_profit": safe_mean(profits),
        "avg_cost": safe_mean(costs),
        "total_cost": sum(costs),
        "win_count": len(wins),
        "loss_count": len(losses),
        "zero_count": sum(1 for p in profits if p == 0),
        "win_rate": active_wins / active_total if active_total > 0 else 0.0,
        "avg_win": safe_mean(wins),
        "avg_loss": safe_mean(losses),
        "wl_ratio": abs(safe_mean(wins) / safe_mean(losses)) if losses else float("inf"),
        "avg_pair_cost": safe_mean(
            [s.cost["avg_pair_cost"] for s in with_matched],
        ),
        "matched_ratio": safe_mean([
            s.inventory["matched"]
            / max(s.inventory["up_shares"], s.inventory["dn_shares"], 0.01)
            for s in resolved
        ]),
        "max_dd": max_dd,
        "max_dd_pct": (max_dd / bar_budget) * 100 if bar_budget > 0 else 0,
        "profit_factor": abs(sum(wins) / sum(losses)) if losses else float("inf"),
        "roi_pct": (sum(profits) / sum(costs) * 100) if sum(costs) > 0 else 0,
    }


# ---------------------------------------------------------------------------
# Experiment definitions
# ---------------------------------------------------------------------------

def build_base_knobs(knobs_path: Path) -> dict:
    """Load base knobs from file."""
    with open(knobs_path) as f:
        return json.load(f)


def knobs_to_config(knobs: dict, bar_seconds: float) -> tuple[DutchConfig, dict]:
    """Convert knobs dict to DutchConfig + sim_kwargs."""
    kwargs = {"bar_seconds": bar_seconds}
    for key, val in knobs.items():
        if key.startswith("_") or key == "fill_simulator":
            continue
        if key in DutchConfig.__dataclass_fields__ and key != "bar_seconds":
            kwargs[key] = val
    sim_kwargs = knobs.get("fill_simulator", {})
    return DutchConfig(**kwargs), sim_kwargs


def define_experiments(base_knobs: dict) -> list[dict]:
    """Define all parameter experiments to run.

    Each experiment is a dict with:
      - name: short label
      - category: grouping for analysis
      - knobs: modified knobs dict (or None to use base)
      - min_time_pct: experimental gate (0 = disabled)
      - max_flips_kill: experimental gate (0 = disabled)
      - prob_variance_gate: experimental gate (0 = disabled)
    """
    experiments = []

    def exp(name, category, overrides=None, **extra_gates):
        k = copy.deepcopy(base_knobs)
        if overrides:
            for key, val in overrides.items():
                if key == "fill_simulator":
                    k["fill_simulator"].update(val)
                else:
                    k[key] = val
        experiments.append({
            "name": name,
            "category": category,
            "knobs": k,
            "min_time_pct": extra_gates.get("min_time_pct", 0.0),
            "max_flips_kill": extra_gates.get("max_flips_kill", 0),
            "prob_variance_gate": extra_gates.get("prob_variance_gate", 0.0),
        })

    # === 0. BASELINE ===
    exp("baseline", "baseline")

    # === 1. WARMUP DELAY — skip early noise ===
    for delay in [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]:
        exp(f"warmup_{delay:.2f}", "warmup_delay", min_time_pct=delay)

    # === 2. CONVICTION BUY SKIP — require stronger model signal ===
    for skip in [0.55, 0.60, 0.65, 0.70, 0.75]:
        exp(f"conv_skip_{skip:.2f}", "conviction_skip",
            overrides={"conviction_buy_skip": skip})

    # === 3. MAX ONE-SIDED COST — limit unmatched exposure ===
    for cap in [2.0, 3.0, 4.0, 6.0, 8.0, 10.0]:
        exp(f"onesided_{cap:.0f}", "onesided_cap",
            overrides={"max_onesided_cost": cap})

    # === 4. FLIP COUNT KILL SWITCH — stop trading on indecisive bars ===
    for flips in [2, 3, 4, 5, 6]:
        exp(f"flip_kill_{flips}", "flip_kill", max_flips_kill=flips)

    # === 5. RISK BUDGET TIMING — delay risk growth ===
    for t_start in [0.15, 0.20, 0.25, 0.30]:
        exp(f"risk_start_{t_start:.2f}", "risk_timing",
            overrides={"risk_t_start": t_start})

    # === 6. RISK FLOOR — limit minimum bet ===
    for floor in [0.005, 0.008, 0.015, 0.02]:
        exp(f"risk_floor_{floor:.3f}", "risk_floor",
            overrides={"risk_floor": floor})

    # === 7. RISK CEILING — limit max bet scaling ===
    for ceil in [0.05, 0.08, 0.10, 0.12]:
        exp(f"risk_ceil_{ceil:.2f}", "risk_ceiling",
            overrides={"risk_ceil": ceil})

    # === 8. CONVICTION SIZE FLOOR — bias sizing toward favored side ===
    for floor in [0.0, 0.2, 0.4, 0.5, 0.6]:
        exp(f"size_floor_{floor:.1f}", "conviction_sizing",
            overrides={"conviction_size_floor": floor})

    # === 9. WARMUP + CONVICTION SKIP combos ===
    for delay in [0.10, 0.15, 0.20]:
        for skip in [0.55, 0.60, 0.65]:
            exp(f"warmup_{delay:.2f}_skip_{skip:.2f}", "combo_warmup_skip",
                overrides={"conviction_buy_skip": skip},
                min_time_pct=delay)

    # === 10. WARMUP + FLIP KILL combos ===
    for delay in [0.10, 0.15]:
        for flips in [3, 4]:
            exp(f"warmup_{delay:.2f}_flip_{flips}", "combo_warmup_flip",
                min_time_pct=delay, max_flips_kill=flips)

    # === 11. FULL DEFENSIVE — warmup + skip + onesided + flip kill ===
    for delay in [0.10, 0.15]:
        for skip in [0.60, 0.65]:
            exp(f"defensive_{delay:.2f}_{skip:.2f}", "combo_defensive",
                overrides={
                    "conviction_buy_skip": skip,
                    "max_onesided_cost": 3.0,
                    "risk_ceil": 0.10,
                },
                min_time_pct=delay, max_flips_kill=4)

    # === 12. PROB VARIANCE GATE — only trade when model is decisive ===
    for var in [0.02, 0.05, 0.08, 0.10]:
        exp(f"prob_var_{var:.2f}", "prob_variance", prob_variance_gate=var)

    # === 13. OBSERVATION-ONLY EARLY — warmup + aggressive after ===
    for delay in [0.15, 0.20, 0.25]:
        exp(f"observe_{delay:.2f}_aggr", "observe_then_aggress",
            overrides={
                "conviction_buy_skip": 0.55,
                "risk_t_start": delay,
                "risk_ceil": 0.20,
            },
            min_time_pct=delay)

    # === 14. PAIR COST GUARD tightening ===
    for mpc in [1.005, 1.01, 1.015, 1.02]:
        exp(f"pair_cost_{mpc:.3f}", "pair_cost_guard",
            overrides={"max_marginal_pair_cost": mpc})

    # === 15. BAR BUDGET reduction ===
    for budget in [50.0, 100.0, 150.0]:
        exp(f"budget_{budget:.0f}", "bar_budget",
            overrides={"bar_budget": budget})

    # === 16. ORDER SIZE ===
    for size in [2.0, 3.0, 8.0, 10.0]:
        exp(f"order_size_{size:.0f}", "order_size",
            overrides={"order_size": size})

    # === 17. UNMATCHED CAP tightening ===
    for ratio in [0.10, 0.15, 0.20, 0.30]:
        exp(f"unmatched_{ratio:.2f}", "unmatched_cap",
            overrides={"unmatched_ratio": ratio, "min_unmatched_shares": 5.0})

    # === 18. VWAP TOLERANCE tightening ===
    for tol in [0.05, 0.08, 0.15, 0.20]:
        exp(f"vwap_{tol:.2f}", "vwap_tolerance",
            overrides={"vwap_tolerance": tol})

    # === 19. SELL TIMING — sell earlier to cut losses ===
    for loss_start in [0.50, 0.60, 0.65]:
        for dump_start in [0.75, 0.80, 0.85]:
            if dump_start > loss_start:
                exp(f"sell_{loss_start:.2f}_{dump_start:.2f}", "sell_timing",
                    overrides={
                        "sell_loss_start": loss_start,
                        "sell_dump_start": dump_start,
                    })

    return experiments


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description="Dutch Parameter Sweep")
    p.add_argument("--pair", required=True, help="Pair to test (e.g. BTC_15m)")
    p.add_argument("--knobs", default=None, help="Base knobs file (default: per-pair)")
    p.add_argument("--ticks-dir", default="data/raw/polymarket_ticks")
    p.add_argument("--model-dir", default="data/models/pulse_v2")
    p.add_argument("--date", default=None, help="Filter to date (YYYY-MM-DD)")
    p.add_argument("--output", default=None, help="TSV output path")
    p.add_argument(
        "--inference-interval", type=float, default=1.0,
        help="Seconds between model predictions (default: 1.0)",
    )
    return p.parse_args()


def main():
    args = parse_args()
    asset, tf_label = args.pair.split("_")

    # Resolve knobs
    if args.knobs:
        knobs_path = Path(args.knobs)
    else:
        knobs_path = Path(f"autoresearch/dutch/knobs_{asset}_{tf_label}.json")
        if not knobs_path.exists():
            knobs_path = Path("autoresearch/dutch/knobs.json")

    bar_seconds = BAR_SECONDS[TF_MAP[tf_label]]
    base_knobs = build_base_knobs(knobs_path)
    logger.info("Base knobs from %s", knobs_path)

    filter_date = date_type.fromisoformat(args.date) if args.date else None

    # Step 1: Precompute (expensive — done once)
    logger.info("=== PRECOMPUTING bars (model inference) ===")
    t0 = time.perf_counter()
    bars = precompute_bars(
        asset, tf_label, Path(args.model_dir),
        Path(args.ticks_dir), args.inference_interval, filter_date,
    )
    precompute_time = time.perf_counter() - t0
    logger.info("Precomputed %d bars in %.1fs", len(bars), precompute_time)

    if not bars:
        logger.error("No bars to replay — exiting")
        return

    # Step 2: Define experiments
    experiments = define_experiments(base_knobs)
    logger.info("Running %d experiments...", len(experiments))

    # Step 3: Run all experiments
    results = []
    t0 = time.perf_counter()

    for i, exp in enumerate(experiments):
        config, sim_kwargs = knobs_to_config(exp["knobs"], bar_seconds)
        metrics = replay_with_config(
            bars, config, sim_kwargs,
            min_time_pct=exp["min_time_pct"],
            max_flips_kill=exp["max_flips_kill"],
            prob_variance_gate=exp["prob_variance_gate"],
        )
        metrics["name"] = exp["name"]
        metrics["category"] = exp["category"]
        results.append(metrics)

        if (i + 1) % 20 == 0:
            logger.info("  ...completed %d/%d experiments", i + 1, len(experiments))

    sweep_time = time.perf_counter() - t0
    logger.info("All %d experiments completed in %.1fs", len(experiments), sweep_time)

    # Step 4: Sort and display results
    baseline = next((r for r in results if r["name"] == "baseline"), None)
    bl_profit = baseline["total_profit"] if baseline else 0

    # Sort by total_profit descending
    ranked = sorted(results, key=lambda r: r.get("total_profit", -999), reverse=True)

    print("\n" + "=" * 140)
    print(f"  DUTCH PARAMETER SWEEP — {asset}/{tf_label} — {len(bars)} bars")
    print("=" * 140)
    print(f"\n  {'Rank':<5} {'Name':<35} {'Category':<22} "
          f"{'TotalPnL':>10} {'AvgPnL':>8} {'WinRate':>8} "
          f"{'AvgWin':>8} {'AvgLoss':>9} {'W/L':>6} "
          f"{'PairCost':>9} {'ROI%':>7} {'MaxDD':>7} "
          f"{'Active':>7} {'vsBL':>8}")
    print("  " + "-" * 136)

    for rank, r in enumerate(ranked, 1):
        bars_active = r.get("bars_active", 0)
        total_pnl = r.get("total_profit", 0)
        delta = total_pnl - bl_profit

        marker = ""
        if r["name"] == "baseline":
            marker = " <-- BASELINE"
        elif delta > 0:
            marker = " +"

        print(
            f"  {rank:<5} {r['name']:<35} {r['category']:<22} "
            f"${total_pnl:>9.2f} "
            f"${r.get('avg_profit', 0):>7.2f} "
            f"{r.get('win_rate', 0):>7.1%} "
            f"${r.get('avg_win', 0):>7.2f} "
            f"${r.get('avg_loss', 0):>8.2f} "
            f"{r.get('wl_ratio', 0):>5.2f} "
            f"{r.get('avg_pair_cost', 0):>9.4f} "
            f"{r.get('roi_pct', 0):>6.1f}% "
            f"${r.get('max_dd', 0):>6.1f} "
            f"{bars_active:>7} "
            f"{'$' + f'{delta:+.2f}':>8}{marker}"
        )

    # Step 5: Category summary
    print("\n" + "=" * 100)
    print("  CATEGORY SUMMARY (best experiment per category)")
    print("=" * 100)

    categories = {}
    for r in results:
        cat = r["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(r)

    cat_bests = []
    for cat, cat_results in categories.items():
        best = max(cat_results, key=lambda r: r.get("total_profit", -999))
        cat_bests.append((cat, best))

    cat_bests.sort(key=lambda x: x[1].get("total_profit", -999), reverse=True)

    print(f"\n  {'Category':<25} {'BestExperiment':<35} "
          f"{'TotalPnL':>10} {'WinRate':>8} {'W/L':>6} {'vsBL':>10}")
    print("  " + "-" * 96)

    for cat, best in cat_bests:
        delta = best.get("total_profit", 0) - bl_profit
        print(
            f"  {cat:<25} {best['name']:<35} "
            f"${best.get('total_profit', 0):>9.2f} "
            f"{best.get('win_rate', 0):>7.1%} "
            f"{best.get('wl_ratio', 0):>5.2f} "
            f"{'$' + f'{delta:+.2f}':>10}"
        )

    # Step 6: Write TSV
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        header = (
            "rank\tname\tcategory\ttotal_profit\tavg_profit\twin_rate\t"
            "avg_win\tavg_loss\twl_ratio\tavg_pair_cost\troi_pct\t"
            "max_dd\tbars_active\tvs_baseline"
        )
        with open(output_path, "w") as f:
            f.write(header + "\n")
            for rank, r in enumerate(ranked, 1):
                delta = r.get("total_profit", 0) - bl_profit
                f.write(
                    f"{rank}\t{r['name']}\t{r['category']}\t"
                    f"{r.get('total_profit', 0):.4f}\t"
                    f"{r.get('avg_profit', 0):.4f}\t"
                    f"{r.get('win_rate', 0):.4f}\t"
                    f"{r.get('avg_win', 0):.4f}\t"
                    f"{r.get('avg_loss', 0):.4f}\t"
                    f"{r.get('wl_ratio', 0):.4f}\t"
                    f"{r.get('avg_pair_cost', 0):.4f}\t"
                    f"{r.get('roi_pct', 0):.4f}\t"
                    f"{r.get('max_dd', 0):.4f}\t"
                    f"{r.get('bars_active', 0)}\t"
                    f"{delta:.4f}\n"
                )
        logger.info("Results written to %s", output_path)

    # Step 7: Top recommendations
    print("\n" + "=" * 100)
    print("  TOP 10 EXPERIMENTS (by total PnL)")
    print("=" * 100)
    for i, r in enumerate(ranked[:10], 1):
        delta = r.get("total_profit", 0) - bl_profit
        print(f"\n  #{i}: {r['name']} ({r['category']})")
        print(f"      PnL: ${r.get('total_profit', 0):+.2f}  (vs baseline: ${delta:+.2f})")
        print(f"      Win rate: {r.get('win_rate', 0):.1%}  W/L ratio: {r.get('wl_ratio', 0):.2f}")
        print(f"      Avg win: ${r.get('avg_win', 0):.2f}  Avg loss: ${r.get('avg_loss', 0):.2f}")
        print(f"      ROI: {r.get('roi_pct', 0):.1f}%  Max DD: ${r.get('max_dd', 0):.2f}")


if __name__ == "__main__":
    main()
