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
import asyncio
import json
import logging
import sys
import time
from datetime import UTC, date as date_type, datetime
from pathlib import Path

import lightgbm as lgb
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
from qm.strategy.dutch.summary_logger import DutchSummaryLogger  # noqa: E402
from qm.strategy.dutch.tick_processor import process_tick, run_inference  # noqa: E402

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
    p.add_argument(
        "--outcome-source", choices=["gamma", "live-log", "spot"], default="spot",
        help="Outcome source: 'gamma'=Polymarket API (accurate), "
             "'live-log'=from paper trading logs, 'spot'=first/last spot (default)",
    )
    p.add_argument(
        "--feature-source", choices=["recorded", "recompute"], default="recompute",
        help="Feature source: 'recorded'=live's cache snapshots (100%% parity), "
             "'recompute'=run full pipeline (default, for model changes)",
    )
    p.add_argument(
        "--tick-cadence", choices=["live", "full"], default="full",
        help="Tick rate: 'live'=1Hz downsample (parity with paper trading), "
             "'full'=all ticks (default, for researcher/sweeps)",
    )
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
    """Load Pulse LightGBM or specialist model + calibrator. Returns (None, None) if missing."""
    from qm.model.specialist import SpecialistModelRouter, load_pulse_model

    sub_dir = model_dir / f"{asset}_{tf_label}"
    if not (sub_dir / "model.lgb").exists() and not (sub_dir / "specialist_config.json").exists():
        logger.warning("No model at %s — skipping %s/%s", sub_dir, asset, tf_label)
        return None, None

    model = load_pulse_model(sub_dir)
    calibrator = None
    if not isinstance(model, SpecialistModelRouter):
        cal_path = sub_dir / "calibrator.pkl"
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


# -- Outcome resolution (Gamma API / live logs / spot fallback) ------------

_SLUG_ASSET = {"BTC": "btc", "ETH": "ethereum", "SOL": "solana", "XRP": "xrp"}
GAMMA_API_URL = "https://gamma-api.polymarket.com/markets"


def _derive_slug(asset: str, tf_label: str, bar_id: int) -> str:
    """Derive Gamma API slug from asset + timeframe + bar_id."""
    prefix = _SLUG_ASSET.get(asset, asset.lower())
    if tf_label == "1h":
        from qm.execution.polymarket.market_scanner import _build_1h_slug
        bar_dt = datetime.fromtimestamp(bar_id, tz=UTC)
        return _build_1h_slug(ASSET_MAP[asset], bar_dt)
    return f"{prefix}-updown-{tf_label}-{bar_id}"


def _parse_outcome(market: dict) -> str | None:
    """Parse outcome from Gamma API market response."""
    outcomes_raw = market.get("outcomes", "[]")
    prices_raw = market.get("outcomePrices", "[]")
    try:
        outcomes = json.loads(outcomes_raw) if isinstance(outcomes_raw, str) else outcomes_raw
        prices = json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw
    except (json.JSONDecodeError, TypeError):
        return None
    for i, p in enumerate(prices):
        if float(p) >= 0.99 and i < len(outcomes):
            raw = outcomes[i].upper()
            # Normalize: Gamma returns "Up"/"Down", we use "UP"/"DN"
            if raw == "DOWN":
                return "DN"
            return raw
    return None


def _load_resolution_cache(cache_file: Path) -> dict[int, str]:
    """Load cached resolutions from JSONL."""
    cached = {}
    if cache_file.exists():
        for line in open(cache_file):
            try:
                r = json.loads(line)
                cached[r["bar_id"]] = r["outcome"]
            except (json.JSONDecodeError, KeyError):
                continue
    return cached


def _save_resolution_cache(cache_file: Path, resolutions: dict[int, str]) -> None:
    """Save resolutions to JSONL cache."""
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_file, "w") as f:
        for bar_id, outcome in sorted(resolutions.items()):
            json.dump({"bar_id": bar_id, "outcome": outcome,
                       "fetched_at": datetime.now(UTC).isoformat()}, f)
            f.write("\n")


async def _batch_fetch_gamma(
    bars: list[tuple[int, str]], asset: str, tf_label: str,
) -> dict[int, str]:
    """Query Gamma API for each bar's resolution. Rate-limited to 5 req/sec."""
    import aiohttp

    results = {}
    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=10),
    ) as session:
        for i, (bar_id, cid) in enumerate(bars):
            slug = _derive_slug(asset, tf_label, bar_id)
            try:
                async with session.get(GAMMA_API_URL, params={"slug": slug}) as resp:
                    if resp.status == 200:
                        markets = await resp.json()
                        if markets and markets[0].get("closed", False):
                            outcome = _parse_outcome(markets[0])
                            if outcome:
                                results[bar_id] = outcome
            except Exception:
                pass
            # Rate limit: 5 req/sec
            if (i + 1) % 5 == 0:
                await asyncio.sleep(1.0)

    logger.info("Fetched %d/%d resolutions from Gamma API", len(results), len(bars))
    return results


def _fetch_gamma_resolutions(
    ticks_df: pl.DataFrame, asset: str, tf_label: str,
    ticks_dir: Path, filter_date: date_type | None,
) -> dict[int, str]:
    """Fetch Polymarket outcomes. Uses local cache, falls back to Gamma API."""
    date_str = str(filter_date) if filter_date else "all"
    cache_file = ticks_dir / "resolutions" / f"{asset}_{tf_label}_{date_str}.jsonl"
    cached = _load_resolution_cache(cache_file)

    # Find bars not in cache
    bar_cids = (
        ticks_df.group_by("window_start", maintain_order=True)
        .agg(pl.col("condition_id").first())
    )
    missing = []
    for row in bar_cids.iter_rows(named=True):
        bar_id = int(row["window_start"].timestamp())
        if bar_id not in cached:
            missing.append((bar_id, row["condition_id"]))

    if not missing:
        logger.info("All %d resolutions loaded from cache", len(cached))
        return cached

    logger.info("Fetching %d resolutions from Gamma API (%d cached)...",
                len(missing), len(cached))
    new_resolutions = asyncio.run(_batch_fetch_gamma(missing, asset, tf_label))

    cached.update(new_resolutions)
    _save_resolution_cache(cache_file, cached)
    return cached


def _load_live_outcomes(asset: str, tf_label: str) -> dict[int, str]:
    """Load outcomes from live paper trading bar logs."""
    outcomes = {}
    bar_dir = Path(f"data/dutch_paper/{asset}_{tf_label}")
    for bf in bar_dir.glob("bars_*.jsonl"):
        for line in open(bf):
            try:
                b = json.loads(line)
                if b.get("outcome"):
                    outcomes[b["bar_id"]] = b["outcome"]
            except (json.JSONDecodeError, KeyError):
                continue
    logger.info("Loaded %d outcomes from live bar logs", len(outcomes))
    return outcomes


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
    tick_cadence: str = "full",
    outcome_source: str = "spot",
    feature_source: str = "recompute",
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

    # -- BTC cross-asset context (non-BTC models only) --
    btc_bar_builder: BarBuilder | None = None
    btc_tick_iter = None
    btc_next_tick = None
    if isinstance(feat_cache, CrossAssetLiveFeatureCache):
        # Warm up BTC historical features from OHLCV (same as live warm-up)
        store = ParquetStore(base_dir=Path("data/raw/ohlcv"))
        btc_bars_df = store.read_bars(Asset.BTC, tf_enum)
        if not btc_bars_df.is_empty():
            btc_pipeline = FeaturePipeline()
            btc_featured = btc_pipeline.compute(btc_bars_df.tail(500))
            btc_last = btc_featured.row(-1, named=True)
            btc_hist = {
                n: float(v) for n in btc_pipeline.feature_names
                if (v := btc_last.get(n)) is not None
            }
            feat_cache.update_btc_history(btc_hist)
            logger.info("BTC warm-up: cached %d features", len(btc_hist))

        # Load BTC tick data for incremental PartialBar (same as live BarBuilder)
        btc_ticks_path = ticks_dir / "asset=BTC" / f"timeframe={tf_label}"
        if btc_ticks_path.exists():
            btc_scan = pl.scan_parquet(str(btc_ticks_path / "**/*.parquet"))
            btc_scan = btc_scan.filter(~pl.col("is_stale") & ~pl.col("is_heartbeat"))
            if filter_date is not None:
                btc_scan = btc_scan.filter(pl.col("ts").dt.date() == filter_date)
            btc_ticks_df = btc_scan.sort("ts").collect()
            if not btc_ticks_df.is_empty():
                btc_bar_builder = BarBuilder(
                    assets=[Asset.BTC], timeframes=[tf_enum],
                )
                btc_tick_iter = iter(btc_ticks_df.iter_rows(named=True))
                btc_next_tick = next(btc_tick_iter, None)
                logger.info(
                    "BTC ticks: %d for incremental PartialBar",
                    len(btc_ticks_df),
                )

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

    # -- Load resolutions for outcome determination --
    resolutions: dict[int, str] = {}
    if outcome_source == "gamma":
        resolutions = _fetch_gamma_resolutions(
            ticks_df, asset, tf_label, ticks_dir, filter_date,
        )
    elif outcome_source == "live-log":
        resolutions = _load_live_outcomes(asset, tf_label)

    # -- Load feature cache snapshots (for recorded mode) --
    cache_snapshots: dict[int, dict] = {}
    if feature_source == "recorded":
        snap_dir = Path(f"data/dutch_paper/{asset}_{tf_label}")
        for sf in snap_dir.glob("cache_snapshots_*.jsonl"):
            for line in open(sf):
                try:
                    s = json.loads(line)
                    cache_snapshots[s["bar_id"]] = s["cache"]
                except (json.JSONDecodeError, KeyError):
                    continue
        logger.info("Loaded %d cache snapshots for recorded feature mode", len(cache_snapshots))

    # -- Replay loop --
    recent_bars: list = []  # Store Bar objects (same as live monitor_pulse.py)
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

        # Outcome determination
        outcome = resolutions.get(bar_id)
        if outcome is None:
            # Fallback: spot price direction
            first_spot = bar_ticks["spot_price"][0]
            last_spot = bar_ticks["spot_price"][-1]
            outcome = "UP" if last_spot > first_spot else "DN"

        # Reset (same as live bar boundary)
        engine.reset()
        sim.reset()
        engine.set_bar_info(
            bar_id=bar_id,
            condition_id=condition_id,
            window_start=str(bar_id),
            window_end=str(bar_id + int(bar_secs)),
        )

        last_inference_ts = None
        cal_prob = 0.5
        last_spot_price = None
        btc_last_spot_price = None
        current_elapsed_pct = 0.0
        live_cadence = tick_cadence == "live"

        for tick in bar_ticks.iter_rows(named=True):
            ts = tick["ts"]
            spot = tick["spot_price"]

            # In live mode: process EVERY tick (live's main loop runs on every
            # book update, not just spot changes). Only feed BarBuilder when
            # spot_price actually changes.
            # In full mode: also process every tick.
            spot_changed = (last_spot_price is None or spot != last_spot_price)
            if spot_changed:
                last_spot_price = spot

            # Feed spot into BarBuilder (only when price changed)
            completed = []
            if spot_changed:
                completed = bar_builder.on_trade(
                    asset_enum, tick["spot_price"], 0.001, ts,
                )
            for bar in completed:
                recent_bars.append(bar)
                recent_bars[:] = recent_bars[-500:]

            # Compute elapsed_pct: use recorded value if available, else from PartialBar
            has_recorded_pct = live_cadence and "elapsed_pct" in tick and tick["elapsed_pct"] > 0
            if has_recorded_pct:
                current_elapsed_pct = tick["elapsed_pct"]
            else:
                partial = bar_builder.get_partial_bar(asset_enum, tf_enum, now=ts)
                if partial is not None:
                    current_elapsed_pct = partial.elapsed_seconds / (
                        partial.remaining_seconds + partial.elapsed_seconds + 1e-10
                    )

            # Advance BTC ticks at same cadence for cross-asset models
            if btc_bar_builder and isinstance(feat_cache, CrossAssetLiveFeatureCache):
                while btc_next_tick and btc_next_tick["ts"] <= ts:
                    btc_spot = btc_next_tick["spot_price"]
                    btc_sampled = (
                        not live_cadence
                        or btc_last_spot_price is None
                        or btc_spot != btc_last_spot_price
                    )
                    if btc_sampled:
                        btc_bar_builder.on_trade(
                            Asset.BTC, btc_spot, 0.001, btc_next_tick["ts"],
                        )
                        btc_last_spot_price = btc_spot
                    btc_next_tick = next(btc_tick_iter, None)
                btc_partial = btc_bar_builder.get_partial_bar(
                    Asset.BTC, tf_enum, now=ts,
                )
            else:
                btc_partial = None

            # Model inference: use recorded cal_prob if available, else recompute
            has_recorded_cal = (
                live_cadence and "cal_prob" in tick and "is_inference" in tick
            )
            if has_recorded_cal:
                # Use live's exact recorded values — 100% parity
                if tick["is_inference"]:
                    cal_prob = tick["cal_prob"]
                    last_inference_ts = ts
            elif (
                last_inference_ts is None
                or (ts - last_inference_ts).total_seconds() >= inference_interval
            ):
                partial_for_inf = partial if not has_recorded_pct else bar_builder.get_partial_bar(asset_enum, tf_enum, now=ts)
                if partial_for_inf is not None:
                    _raw, cal_prob, _feats = run_inference(
                        model, calibrator, feat_cache,
                        partial_for_inf, current_elapsed_pct, btc_partial,
                    )
                    last_inference_ts = ts

            # Reconstruct books from tick BBO
            book_up, book_dn = tick_to_books(tick)

            # Engine → orders → sim → fills (shared code path with live)
            _orders, _fills = process_tick(
                current_elapsed_pct, cal_prob, book_up, book_dn, engine, sim,
            )

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

        # -- Inter-bar feature cache update --
        recent_bars[:] = recent_bars[-500:]
        if feature_source == "recorded":
            # Use live's exact cache snapshot (100% parity)
            recorded_cache = cache_snapshots.get(bar_id)
            if recorded_cache:
                feat_cache.update_history(recorded_cache)
        elif len(recent_bars) >= 20:
            # Recompute from BarBuilder (for model changes)
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
                tick_cadence=args.tick_cadence,
                outcome_source=args.outcome_source,
                feature_source=args.feature_source,
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
