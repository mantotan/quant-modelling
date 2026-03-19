#!/usr/bin/env python
"""Train Pulse model using REAL tick data -- zero interpolation.

Uses actual aggTrades from Binance for honest intra-bar features.
Backtests on held-out OOS with realistic friction ($50 flat bets).

Usage:
    python scripts/train_pulse_v2.py --asset BTC --timeframe 5m --n-trials 50
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import json

import numpy as np

from qm.backtest.intrabar_backtest import IntraBarBacktester
from qm.backtest.market_sim import MarketOddsSimulator
from qm.core.types import Asset, Timeframe
from qm.data.storage.parquet import ParquetStore
from qm.features.intrabar import CACHED_FEATURE_NAMES
from qm.features.pipeline import FeaturePipeline
from qm.model.calibration.calibrator import IsotonicCalibrator
from qm.model.targets.intrabar import IntraBarDataset
from qm.model.targets.tick_generator import RealTickDataGenerator
from qm.model.trainers.pulse_trainer import PulseTrainer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train Pulse with real tick data")
    parser.add_argument("--asset", type=str, default="BTC")
    parser.add_argument("--timeframe", type=str, default="5m")
    parser.add_argument("--ohlcv-dir", type=str, default="data/raw/ohlcv")
    parser.add_argument("--trades-dir", type=str, default="data/raw/trades")
    parser.add_argument("--model-dir", type=str, default="data/models/pulse_v2")
    parser.add_argument("--n-trials", type=int, default=50)
    parser.add_argument("--efficiency", type=float, default=0.75)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    asset_map = {"BTC": Asset.BTC, "ETH": Asset.ETH, "SOL": Asset.SOL, "XRP": Asset.XRP}
    tf_map = {"5m": Timeframe.M5, "15m": Timeframe.M15, "1h": Timeframe.H1}
    asset = asset_map[args.asset.upper()]
    timeframe = tf_map[args.timeframe]

    logger.info("=" * 60)
    logger.info("Pulse V2: Real Tick Data Training")
    logger.info("=" * 60)
    logger.info("Asset:      %s", asset.value)
    logger.info("Timeframe:  %s", timeframe.value)
    logger.info("Efficiency: %.2f", args.efficiency)
    logger.info("Data:       REAL aggTrades (zero interpolation)")
    logger.info("Backtest:   Held-out OOS, $50 flat, 2%% fees, impact")
    logger.info("=" * 60)

    # 1. Load OHLCV bars
    ohlcv_store = ParquetStore(base_dir=Path(args.ohlcv_dir))
    bars_df = ohlcv_store.read_bars(asset, timeframe)
    logger.info("Loaded %d %s bars", len(bars_df), timeframe.value)

    # 2. Join alpha stores if available, then compute features
    t0 = time.time()
    from qm.features.cross_asset import join_alpha_asof

    # Try joining funding rate data
    funding_dir = Path("data/raw/funding")
    if funding_dir.exists():
        try:
            funding_store = ParquetStore(base_dir=funding_dir)
            funding_df = funding_store.read_metrics(asset)
            if not funding_df.is_empty():
                bars_df = join_alpha_asof(
                    bars_df, funding_df, prefix="funding", tolerance="9h",
                )
                logger.info("Joined %d funding rate records", len(funding_df))
        except Exception as e:
            logger.warning("Could not join funding data: %s", e)

    # Try joining options IV data (BTC/ETH only)
    iv_dir = Path("data/raw/options_iv")
    if iv_dir.exists():
        try:
            iv_store = ParquetStore(base_dir=iv_dir)
            iv_df = iv_store.read_metrics(asset)
            if not iv_df.is_empty():
                bars_df = join_alpha_asof(
                    bars_df, iv_df, prefix="options_iv",
                )
                logger.info("Joined %d IV records", len(iv_df))
        except Exception as e:
            logger.warning("Could not join IV data: %s", e)

    pipeline = FeaturePipeline()
    featured_df = pipeline.compute(bars_df)

    # Use cached_features from knobs.json if available, otherwise fall back to CACHED_FEATURE_NAMES
    knobs_path = Path("autoresearch/knobs.json")
    if knobs_path.exists():
        with open(knobs_path) as f:
            knobs_data = json.load(f)
        feature_list = knobs_data.get("cached_features", CACHED_FEATURE_NAMES)
        logger.info("Feature list from knobs.json: %d features", len(feature_list))
    else:
        feature_list = CACHED_FEATURE_NAMES
        logger.info("Feature list from CACHED_FEATURE_NAMES: %d features", len(feature_list))

    available = [c for c in feature_list if c in featured_df.columns]
    missing = [c for c in feature_list if c not in featured_df.columns]
    if missing:
        logger.warning("Features in knobs but missing from data: %s", missing)
    history_features = featured_df.select(available)
    logger.info("Using %d/%d cached features (computed in %.1fs)",
                len(available), len(feature_list), time.time() - t0)

    # 3. Generate training data from REAL trades
    trades_store = ParquetStore(base_dir=Path(args.trades_dir))
    trade_dates = trades_store.list_trade_dates(asset)
    logger.info("Available trade dates: %d (%s to %s)",
                len(trade_dates),
                trade_dates[0] if trade_dates else "none",
                trade_dates[-1] if trade_dates else "none")

    market_sim = MarketOddsSimulator(efficiency=args.efficiency, timeframe=timeframe)
    gen = RealTickDataGenerator(timeframe=timeframe, seed=args.seed)

    # Check for cached dataset first
    cache_path = Path(args.model_dir) / f"{asset.value}_{timeframe.value}" / "dataset.npz"
    if cache_path.exists():
        dataset = IntraBarDataset.load(cache_path)
        logger.info("Loaded cached dataset: %d samples from %s", len(dataset.y), cache_path)
    else:
        t0 = time.time()
        dataset = gen.generate(bars_df, trades_store, history_features, market_sim)
        logger.info(
            "Training data: %d samples from %d bars in %.1fs (REAL TICKS)",
            len(dataset.y), len(np.unique(dataset.bar_indices)), time.time() - t0,
        )
        # Cache for reuse by ensemble script
        dataset.save(cache_path)
        logger.info("Cached dataset to %s", cache_path)

    if len(dataset.y) < 5000:
        logger.error("Not enough samples (%d). Download more trade data.", len(dataset.y))
        sys.exit(1)

    logger.info("Target balance: %.1f%% Up", dataset.y.mean() * 100)

    # 4. Optuna HPO — read walk-forward params from knobs.json
    knobs_path = Path("autoresearch/knobs.json")
    if knobs_path.exists():
        with open(knobs_path) as f:
            knobs = json.load(f)
        wf = knobs.get("walk_forward", {})
        wf_n_splits = wf.get("n_splits", 8)
        wf_train_bars = wf.get("train_bars", 5000)
        wf_test_bars = wf.get("test_bars", 2000)
        wf_purge = wf.get("purge_period", 12)
        wf_embargo = wf.get("embargo_period", 6)
        logger.info("Walk-forward from knobs.json: splits=%d train=%d test=%d purge=%d embargo=%d",
                     wf_n_splits, wf_train_bars, wf_test_bars, wf_purge, wf_embargo)
    else:
        wf_n_splits, wf_train_bars, wf_test_bars = 8, 5000, 2000
        wf_purge, wf_embargo = 12, 6

    t0 = time.time()
    trainer = PulseTrainer(
        n_trials=args.n_trials, n_splits=wf_n_splits,
        train_bars=wf_train_bars, test_bars=wf_test_bars,
        purge_period=wf_purge, embargo_period=wf_embargo,
        seed=args.seed,
    )
    best_metrics = trainer.fit(dataset)
    logger.info("HPO complete in %.1fs", time.time() - t0)
    logger.info("Best CV: %s", best_metrics)
    logger.info("Best params: %s", trainer.best_params)

    # 5. OOS predictions
    t0 = time.time()
    oos_probs, oos_targets, oos_mask = trainer.get_oos_predictions(dataset)
    oos_idx = np.where(oos_mask)[0]
    logger.info("OOS predictions: %d samples in %.1fs", len(oos_idx), time.time() - t0)

    if len(oos_idx) < 500:
        logger.error("Not enough OOS samples (%d).", len(oos_idx))
        sys.exit(1)

    # 6. Split OOS: 70% calibration, 30% backtest
    cal_end = int(len(oos_idx) * 0.7)
    cal_idx = oos_idx[:cal_end]
    bt_idx = oos_idx[cal_end:]

    calibrator = IsotonicCalibrator()
    calibrator.fit(oos_probs[cal_idx], oos_targets[cal_idx])
    calibrated_bt = calibrator.transform(oos_probs[bt_idx])
    logger.info("Calibrator: %d cal samples, %d backtest samples", len(cal_idx), len(bt_idx))

    # 7. Backtest: held-out OOS, $50 flat, realistic friction
    backtester = IntraBarBacktester(
        fee_bps=200, spread=0.02, min_edge=0.02,
        max_trades_per_bar=3, timeframe=timeframe,
        impact_bps=50, avg_daily_volume=50_000,
        max_daily_trades=100, fixed_bet_usd=50.0,
    )
    result = backtester.run_full(
        calibrated_bt, dataset.y[bt_idx], dataset.market_probs[bt_idx],
        dataset.time_pcts[bt_idx], dataset.bar_indices[bt_idx],
        initial_bankroll=10_000.0,
    )

    # 8. Results
    logger.info("=" * 60)
    logger.info("RESULTS (held-out OOS, $50 flat, 2%% fees, real ticks)")
    logger.info("=" * 60)
    for k, v in result.metrics.items():
        logger.info("  %-25s %s", k, f"{v:.4f}" if isinstance(v, float) else v)

    logger.info("")
    logger.info("TIME-SEGMENTED:")
    for bucket, m in result.metrics_by_time_bucket.items():
        logger.info("  %-15s trades=%d  win=%.1f%%  roi=%.2f%%",
                     bucket, m["n_trades"], m["win_rate"]*100, m["roi_per_trade"]*100)

    # Per-time-point accuracy
    bt_tps = dataset.time_pcts[bt_idx]
    bt_targets = dataset.y[bt_idx]
    bt_acc = float(np.mean((calibrated_bt > 0.5) == (bt_targets == 1)))
    bt_brier = float(np.mean((calibrated_bt - bt_targets) ** 2))

    logger.info("")
    logger.info("HELD-OUT ACCURACY: %.2f%%", bt_acc * 100)
    logger.info("HELD-OUT BRIER:    %.4f", bt_brier)

    logger.info("")
    logger.info("PER-TIME-POINT ACCURACY:")
    logger.info("%-10s %10s %10s", "time_pct", "N", "Accuracy")
    logger.info("-" * 35)
    for tp in sorted(set(bt_tps)):
        mask = bt_tps == tp
        acc = float(np.mean((calibrated_bt[mask] > 0.5) == (bt_targets[mask] == 1)))
        logger.info("%-10.3f %10d %9.1f%%", tp, int(mask.sum()), acc * 100)

    # Feature importance
    logger.info("")
    logger.info("TOP 10 FEATURES:")
    for name, imp in list(trainer.feature_importance.items())[:10]:
        logger.info("  %-30s %.0f", name, imp)

    # 9. Save
    model_dir = Path(args.model_dir) / f"{asset.value}_{timeframe.value}"
    trainer.save(model_dir / "model.lgb")
    calibrator.save(model_dir / "calibrator.pkl")
    logger.info("Model saved to %s", model_dir)


if __name__ == "__main__":
    main()
