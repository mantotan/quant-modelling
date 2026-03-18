#!/usr/bin/env python
"""Evaluate Sentinel + Pulse ensemble on aligned OOS predictions.

Does NOT train new permanent models. Re-trains both Sentinel and Pulse
on the SAME walk-forward folds to produce aligned OOS predictions,
then evaluates combination strategies head-to-head.

Usage:
    python scripts/train_ensemble.py --asset BTC --n-trials 20
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import lightgbm as lgb
import numpy as np

from qm.backtest.ensemble_backtest import EnsembleBacktester, format_comparison
from qm.backtest.market_sim import MarketOddsSimulator
from qm.backtest.validation.walk_forward import WalkForwardSplitter
from qm.core.types import Asset, Timeframe
from qm.data.storage.parquet import ParquetStore
from qm.features.cross_asset import CrossAssetPipeline
from qm.features.intrabar import CACHED_FEATURE_NAMES
from qm.features.pipeline import FeaturePipeline
from qm.model.calibration.calibrator import IsotonicCalibrator
from qm.model.ensemble.predictor import (
    BayesianUpdateStrategy,
    TimeWeightedStrategy,
)
from qm.model.targets.binary import BinaryDirectionTarget
from qm.model.targets.tick_generator import RealTickDataGenerator
from qm.model.trainers.device import detect_device

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

EXCLUDE_FEATURES = {"return_1", "log_return_1", "gap"}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Evaluate Sentinel+Pulse ensemble")
    p.add_argument("--asset", type=str, default="BTC")
    p.add_argument("--timeframe", type=str, default="5m")
    p.add_argument("--ohlcv-dir", type=str, default="data/raw/ohlcv")
    p.add_argument("--metrics-dir", type=str, default="data/raw/metrics")
    p.add_argument("--trades-dir", type=str, default="data/raw/trades")
    p.add_argument("--model-dir", type=str, default="data/models/ensemble")
    p.add_argument("--n-trials", type=int, default=20,
                   help="HPO trials per model per fold (keep low for ensemble eval)")
    p.add_argument("--n-splits", type=int, default=5)
    p.add_argument("--train-bars", type=int, default=5000)
    p.add_argument("--test-bars", type=int, default=1000)
    p.add_argument("--efficiency", type=float, default=0.75)
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    asset_map = {"BTC": Asset.BTC, "ETH": Asset.ETH, "SOL": Asset.SOL, "XRP": Asset.XRP}
    tf_map = {"5m": Timeframe.M5, "15m": Timeframe.M15, "1h": Timeframe.H1}
    asset = asset_map[args.asset.upper()]
    timeframe = tf_map[args.timeframe]
    device = detect_device(prefer_gpu=True)

    logger.info("=" * 60)
    logger.info("Sentinel + Pulse Ensemble Evaluation")
    logger.info("=" * 60)
    logger.info("Asset:     %s", asset.value)
    logger.info("Timeframe: %s", timeframe.value)
    logger.info("Device:    %s", device)
    logger.info("=" * 60)

    # ── 1. Load OHLCV + compute Sentinel features ───────────────────
    t0 = time.time()
    ohlcv_store = ParquetStore(base_dir=Path(args.ohlcv_dir))
    metrics_store = ParquetStore(base_dir=Path(args.metrics_dir))
    cross_pipeline = CrossAssetPipeline(
        ohlcv_store, timeframe, metrics_store=metrics_store,
    )
    featured_df = cross_pipeline.compute(asset)

    # Target: close[t+1] >= open[t+1]
    target = BinaryDirectionTarget(horizon_bars=1)
    featured_df = featured_df.with_columns(target.compute(featured_df).alias("target"))

    # Clean: drop lookback + nulls
    lookback = cross_pipeline.max_lookback
    clean_df = featured_df.slice(lookback).drop_nulls(subset=["target"])

    # Sentinel feature columns
    all_feat_names = cross_pipeline.feature_names(asset)
    sentinel_features = [f for f in all_feat_names if f not in EXCLUDE_FEATURES]
    logger.info("Sentinel features: %d, bars: %d (%.1fs)",
                len(sentinel_features), len(clean_df), time.time() - t0)

    # ── 2. Generate Pulse training data from real ticks ─────────────
    t0 = time.time()
    trades_store = ParquetStore(base_dir=Path(args.trades_dir))
    trade_dates = trades_store.list_trade_dates(asset)
    if not trade_dates:
        logger.error("No trade data for %s. Run download_trades.py first.", asset.value)
        sys.exit(1)

    # Compute Pulse historical features
    pipeline = FeaturePipeline()
    bars_df = ohlcv_store.read_bars(asset, timeframe)
    featured_bars = pipeline.compute(bars_df)
    available = [c for c in CACHED_FEATURE_NAMES if c in featured_bars.columns]
    history_features = featured_bars.select(available)

    market_sim = MarketOddsSimulator(efficiency=args.efficiency, timeframe=timeframe)
    gen = RealTickDataGenerator(timeframe=timeframe, seed=args.seed)
    pulse_dataset = gen.generate(bars_df, trades_store, history_features, market_sim)

    if len(pulse_dataset.y) < 5000:
        logger.error("Not enough Pulse samples (%d). Need more trade data.", len(pulse_dataset.y))
        sys.exit(1)

    logger.info("Pulse data: %d samples from %d bars (%.1fs)",
                len(pulse_dataset.y), len(np.unique(pulse_dataset.bar_indices)),
                time.time() - t0)

    # ── 3. Align bar indices between Sentinel and Pulse ─────────────
    # Sentinel: clean_df has one row per bar (indexed 0..N-1)
    # Pulse: pulse_dataset.bar_indices maps samples to bar positions
    # We need both predictions on the same bar set.
    #
    # Strategy: use Pulse's bar indices as the authoritative set,
    # then map each Pulse bar to the corresponding Sentinel bar.

    sentinel_X = clean_df.select(sentinel_features).fill_null(0).to_numpy().astype(np.float64)
    sentinel_y = clean_df["target"].to_numpy().astype(np.float64)

    pulse_X = pulse_dataset.X
    pulse_y = pulse_dataset.y
    pulse_bar_indices = pulse_dataset.bar_indices
    pulse_time_pcts = pulse_dataset.time_pcts
    pulse_market_probs = pulse_dataset.market_probs

    unique_pulse_bars = np.unique(pulse_bar_indices)
    n_pulse_bars = len(unique_pulse_bars)

    # Both models use these bars. Sentinel features are indexed
    # directly by bar position. Pulse bar_indices are already
    # consecutive integers from the tick generator.
    logger.info("Shared bars for ensemble: %d", n_pulse_bars)

    # ── 4. Walk-forward: train both models on same folds ────────────
    t0 = time.time()
    splitter = WalkForwardSplitter(
        n_splits=args.n_splits,
        train_period=args.train_bars,
        test_period=args.test_bars,
        purge_period=12,
        embargo_period=6,
    )

    # OOS containers
    sentinel_oos_probs = np.full(n_pulse_bars, np.nan)
    pulse_oos_probs = np.full(len(pulse_y), np.nan)
    oos_mask_bars = np.zeros(n_pulse_bars, dtype=bool)
    oos_mask_samples = np.zeros(len(pulse_y), dtype=bool)

    sentinel_hpo_params = _default_sentinel_params(args.seed, device)
    pulse_hpo_params = _default_pulse_params(args.seed, device)

    fold_count = 0
    for bar_train_idx, bar_test_idx in splitter.split(n_pulse_bars):
        fold_count += 1
        train_bars = unique_pulse_bars[bar_train_idx]
        test_bars = unique_pulse_bars[bar_test_idx]

        # ── Sentinel: train on bar-level features ───────────────
        # Map bar indices to sentinel_X rows (clamped to valid range)
        s_train_idx = train_bars[train_bars < len(sentinel_X)]
        s_test_idx = test_bars[test_bars < len(sentinel_X)]

        if len(s_train_idx) < 100 or len(s_test_idx) < 50:
            continue

        s_train_data = lgb.Dataset(
            sentinel_X[s_train_idx], sentinel_y[s_train_idx],
            feature_name=sentinel_features,
        )
        s_model = lgb.train(
            sentinel_hpo_params, s_train_data,
            num_boost_round=500,
        )
        sentinel_oos_probs[bar_test_idx] = s_model.predict(sentinel_X[s_test_idx])
        oos_mask_bars[bar_test_idx] = True

        # ── Pulse: train on intra-bar features ──────────────────
        p_train_mask = np.isin(pulse_bar_indices, train_bars)
        p_test_mask = np.isin(pulse_bar_indices, test_bars)
        p_train_idx = np.where(p_train_mask)[0]
        p_test_idx = np.where(p_test_mask)[0]

        if len(p_train_idx) < 100 or len(p_test_idx) < 50:
            continue

        p_train_data = lgb.Dataset(
            pulse_X[p_train_idx], pulse_y[p_train_idx],
            feature_name=pulse_dataset.feature_names,
        )
        p_model = lgb.train(
            pulse_hpo_params, p_train_data,
            num_boost_round=500,
        )
        pulse_oos_probs[p_test_idx] = p_model.predict(pulse_X[p_test_idx])
        oos_mask_samples[p_test_idx] = True

        logger.info("Fold %d: sentinel=%d bars, pulse=%d samples (OOS)",
                     fold_count, len(s_test_idx), len(p_test_idx))

    elapsed = time.time() - t0
    logger.info("Walk-forward complete in %.1fs (%d folds)", elapsed, fold_count)

    # Filter to samples with BOTH models' predictions
    valid_samples = oos_mask_samples & np.array([
        oos_mask_bars[np.searchsorted(unique_pulse_bars, bi)]
        if bi in unique_pulse_bars else False
        for bi in pulse_bar_indices
    ])

    valid_idx = np.where(valid_samples)[0]
    if len(valid_idx) < 500:
        logger.error("Not enough aligned OOS samples (%d). Need more data.", len(valid_idx))
        sys.exit(1)

    logger.info("Aligned OOS samples: %d", len(valid_idx))

    # Extract aligned arrays
    v_pulse_probs = pulse_oos_probs[valid_idx]
    v_targets = pulse_y[valid_idx]
    v_time_pcts = pulse_time_pcts[valid_idx]
    v_market_probs = pulse_market_probs[valid_idx]
    v_bar_indices = pulse_bar_indices[valid_idx]

    # Map bar indices to consecutive 0..N for sentinel_probs lookup
    unique_valid_bars = np.unique(v_bar_indices)
    bar_remap = {old: new for new, old in enumerate(unique_valid_bars)}
    v_bar_indices_remapped = np.array([bar_remap[bi] for bi in v_bar_indices])

    v_sentinel_probs = np.array([
        sentinel_oos_probs[np.searchsorted(unique_pulse_bars, bi)]
        for bi in unique_valid_bars
    ])

    # ── 5. Calibrate each model (70/30 split) ──────────────────────
    cal_end = int(len(valid_idx) * 0.7)
    cal_idx = np.arange(cal_end)
    bt_idx = np.arange(cal_end, len(valid_idx))

    # Sentinel calibration (bar-level)
    cal_bar_end = int(len(unique_valid_bars) * 0.7)
    sentinel_cal = IsotonicCalibrator()
    sentinel_cal.fit(v_sentinel_probs[:cal_bar_end], sentinel_y[unique_valid_bars[:cal_bar_end]])
    cal_sentinel = sentinel_cal.transform(v_sentinel_probs)

    # Pulse calibration (sample-level)
    pulse_cal = IsotonicCalibrator()
    pulse_cal.fit(v_pulse_probs[cal_idx], v_targets[cal_idx])
    cal_pulse = pulse_cal.transform(v_pulse_probs)

    logger.info("Calibration: %d cal samples, %d backtest samples", cal_end, len(bt_idx))

    # ── 6. Evaluate strategies ──────────────────────────────────────
    bt_sentinel = cal_sentinel  # already calibrated for all bars
    bt_pulse = cal_pulse[bt_idx]
    bt_targets = v_targets[bt_idx]
    bt_time_pcts = v_time_pcts[bt_idx]
    bt_market_probs = v_market_probs[bt_idx]
    bt_bar_indices = v_bar_indices_remapped[bt_idx]

    backtester = EnsembleBacktester(
        fee_bps=200, spread=0.02, min_edge=0.02,
        max_trades_per_bar=3, impact_bps=50,
        avg_daily_volume=50_000, max_daily_trades=100,
        fixed_bet_usd=50.0, timeframe=timeframe,
    )

    strategies = {
        "bayesian": BayesianUpdateStrategy(),
        "time_weighted": TimeWeightedStrategy(),
    }

    best_strategy_name = None
    best_sharpe = -np.inf
    all_results = {}

    for name, strategy in strategies.items():
        logger.info("")
        logger.info("Strategy: %s", name)
        logger.info("-" * 40)

        result = backtester.evaluate(
            bt_sentinel, bt_pulse, bt_targets, bt_market_probs,
            bt_time_pcts, bt_bar_indices, strategy,
        )
        all_results[name] = result

        logger.info("\n%s", format_comparison(result))

        ens = result["ensemble"]
        ens_sharpe = ens.get("sharpe", 0)
        if ens_sharpe > best_sharpe:
            best_sharpe = ens_sharpe
            best_strategy_name = name

        # Disagreement stats
        logger.info("  Avg disagreement: %.3f", ens.get("avg_disagreement", 0))
        logger.info("  High disagreement (>0.30): %.1f%%", ens.get("pct_high_disagreement", 0))

    # ── 7. Summary ──────────────────────────────────────────────────
    logger.info("")
    logger.info("=" * 60)
    logger.info("ENSEMBLE EVALUATION SUMMARY")
    logger.info("=" * 60)
    logger.info("Best strategy: %s (Sharpe=%.2f)", best_strategy_name, best_sharpe)

    for name, result in all_results.items():
        ens = result["ensemble"]
        pul = result["pulse"]
        sen = result["sentinel"]
        logger.info("")
        logger.info("Strategy: %s", name)
        logger.info("  Ensemble: Sharpe=%.2f PnL=$%.2f Trades=%d Win=%.1f%%",
                     ens.get("sharpe", 0), ens.get("total_pnl", 0),
                     ens.get("n_trades", 0), ens.get("win_rate", 0) * 100)
        logger.info("  Pulse:    Sharpe=%.2f PnL=$%.2f Trades=%d Win=%.1f%%",
                     pul.get("sharpe", 0), pul.get("total_pnl", 0),
                     pul.get("n_trades", 0), pul.get("win_rate", 0) * 100)
        logger.info("  Sentinel: Sharpe=%.2f PnL=$%.2f Trades=%d Win=%.1f%%",
                     sen.get("sharpe", 0), sen.get("total_pnl", 0),
                     sen.get("n_trades", 0), sen.get("win_rate", 0) * 100)

    # ── 8. Save ─────────────────────────────────────────────────────
    model_dir = Path(args.model_dir) / f"{asset.value}_{timeframe.value}"
    model_dir.mkdir(parents=True, exist_ok=True)

    # Save strategy config
    config = {
        "best_strategy": best_strategy_name,
        "best_sharpe": best_sharpe,
        "n_aligned_oos": len(valid_idx),
        "n_backtest": len(bt_idx),
        "strategies": {},
    }
    for name, result in all_results.items():
        config["strategies"][name] = {
            "ensemble_sharpe": result["ensemble"].get("sharpe", 0),
            "ensemble_pnl": result["ensemble"].get("total_pnl", 0),
            "pulse_sharpe": result["pulse"].get("sharpe", 0),
            "sentinel_sharpe": result["sentinel"].get("sharpe", 0),
        }

    with open(model_dir / "strategy.json", "w") as f:
        json.dump(config, f, indent=2)

    # Save calibrators for the best strategy
    sentinel_cal.save(model_dir / "sentinel_calibrator.pkl")
    pulse_cal.save(model_dir / "pulse_calibrator.pkl")

    logger.info("Results saved to %s", model_dir)


def _default_sentinel_params(seed: int, device: str) -> dict:
    """Default LightGBM params for Sentinel (used without HPO for eval speed)."""
    return {
        "objective": "binary",
        "metric": "binary_logloss",
        "verbosity": -1,
        "device": device,
        "learning_rate": 0.03,
        "max_depth": 5,
        "num_leaves": 63,
        "min_child_samples": 100,
        "subsample": 0.8,
        "colsample_bytree": 0.7,
        "reg_alpha": 0.1,
        "reg_lambda": 1.0,
        "seed": seed,
    }


def _default_pulse_params(seed: int, device: str) -> dict:
    """Default LightGBM params for Pulse (used without HPO for eval speed)."""
    return {
        "objective": "binary",
        "metric": "binary_logloss",
        "verbosity": -1,
        "device": device,
        "learning_rate": 0.02,
        "max_depth": 4,
        "num_leaves": 31,
        "min_child_samples": 200,
        "subsample": 0.75,
        "colsample_bytree": 0.6,
        "reg_alpha": 0.5,
        "reg_lambda": 2.0,
        "seed": seed,
    }


if __name__ == "__main__":
    main()
