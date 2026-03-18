#!/usr/bin/env python
"""End-to-end Pulse (intra-bar) model training pipeline.

Usage:
    python scripts/train_pulse.py
    python scripts/train_pulse.py --asset BTC --timeframe 5m
    python scripts/train_pulse.py --n-trials 50 --efficiency 0.3

Flow:
    1. Load OHLCV bars from ParquetStore
    2. Compute Sentinel features via FeaturePipeline
    3. Generate intra-bar training data (16 samples/bar, 23 features)
    4. Run Optuna HPO with bar-level walk-forward
    5. Train final model, generate OOS predictions for calibration
    6. Fit IsotonicCalibrator on OOS predictions
    7. Run IntraBarBacktester with time-segmented reporting
    8. Print time-bucket breakdown (validates early-bar ROI thesis)
    9. Save model + calibrator
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import numpy as np

from qm.backtest.intrabar_backtest import IntraBarBacktester
from qm.backtest.market_sim import MarketOddsSimulator
from qm.core.types import Asset, Timeframe
from qm.data.storage.parquet import ParquetStore
from qm.features.intrabar import CACHED_FEATURE_NAMES
from qm.features.pipeline import FeaturePipeline
from qm.model.calibration.calibrator import IsotonicCalibrator
from qm.model.targets.intrabar import IntraBarTrainingDataGenerator
from qm.model.trainers.pulse_trainer import PulseTrainer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train Pulse intra-bar model")
    parser.add_argument("--asset", type=str, default="BTC", help="Asset (default: BTC)")
    parser.add_argument("--timeframe", type=str, default="5m", help="Timeframe (default: 5m)")
    parser.add_argument("--data-dir", type=str, default="data/raw/ohlcv", help="Data directory")
    parser.add_argument("--model-dir", type=str, default="data/models/pulse", help="Model output dir")
    parser.add_argument("--n-trials", type=int, default=80, help="Optuna HPO trials")
    parser.add_argument("--efficiency", type=float, default=0.3, help="Market efficiency (0-1)")
    parser.add_argument("--noise", type=float, default=0.1, help="Path noise std")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    asset_map = {"BTC": Asset.BTC, "ETH": Asset.ETH, "SOL": Asset.SOL, "XRP": Asset.XRP}
    tf_map = {"1m": Timeframe.M1, "5m": Timeframe.M5, "15m": Timeframe.M15, "1h": Timeframe.H1}

    asset = asset_map[args.asset.upper()]
    timeframe = tf_map[args.timeframe]

    logger.info("=" * 60)
    logger.info("Pulse Model Training Pipeline")
    logger.info("=" * 60)
    logger.info("Asset:      %s", asset.value)
    logger.info("Timeframe:  %s", timeframe.value)
    logger.info("Efficiency: %.2f", args.efficiency)
    logger.info("HPO trials: %d", args.n_trials)
    logger.info("=" * 60)

    # 1. Load bars
    store = ParquetStore(base_dir=Path(args.data_dir))
    bars_df = store.read_bars(asset, timeframe)
    logger.info("Loaded %d bars for %s/%s", len(bars_df), asset.value, timeframe.value)

    if len(bars_df) < 10_000:
        logger.error("Need at least 10,000 bars. Got %d.", len(bars_df))
        sys.exit(1)

    # 2. Compute Sentinel features
    t0 = time.time()
    pipeline = FeaturePipeline()
    featured_df = pipeline.compute(bars_df)
    logger.info("Features computed in %.1fs (%d columns)", time.time() - t0, featured_df.width)

    # Extract history features for Pulse
    available_cached = [c for c in CACHED_FEATURE_NAMES if c in featured_df.columns]
    missing = [c for c in CACHED_FEATURE_NAMES if c not in featured_df.columns]
    if missing:
        logger.warning("Missing cached features (will use defaults): %s", missing)
    history_features = featured_df.select(available_cached)

    # 3. Generate intra-bar training data
    t0 = time.time()
    market_sim = MarketOddsSimulator(efficiency=args.efficiency, timeframe=timeframe)
    gen = IntraBarTrainingDataGenerator(seed=args.seed)
    dataset = gen.generate(
        bars_df, history_features, market_sim,
        path_noise_std=args.noise,
    )
    logger.info(
        "Training data: %d samples from %d bars in %.1fs",
        len(dataset.y), len(bars_df), time.time() - t0,
    )
    logger.info("Target balance: %.1f%% Up", dataset.y.mean() * 100)

    # 4. Optuna HPO with bar-level walk-forward
    t0 = time.time()
    trainer = PulseTrainer(
        n_trials=args.n_trials,
        n_splits=5,
        train_bars=5000,
        test_bars=1000,
        seed=args.seed,
    )
    best_metrics = trainer.fit(dataset)
    logger.info("HPO complete in %.1fs", time.time() - t0)
    logger.info("Best CV metrics: %s", best_metrics)
    logger.info("Best params: %s", trainer.best_params)

    # 5. Generate OOS predictions for calibration
    t0 = time.time()
    oos_probs, oos_targets, oos_mask = trainer.get_oos_predictions(dataset)
    oos_idx = np.where(oos_mask)[0]
    logger.info("OOS predictions: %d samples in %.1fs", len(oos_idx), time.time() - t0)

    # 6. Calibrate
    calibrator = IsotonicCalibrator()
    calibrator.fit(oos_probs[oos_idx], oos_targets[oos_idx])
    logger.info("Calibrator fitted on %d OOS samples", len(oos_idx))

    # 7. Run backtest with time-segmented reporting
    calibrated_probs = calibrator.transform(trainer.predict_proba(dataset.X))
    backtester = IntraBarBacktester(
        fee_bps=0.0, spread=0.02, min_edge=0.02,
        max_trades_per_bar=3, timeframe=timeframe,
    )
    result = backtester.run_full(
        calibrated_probs, dataset.y, dataset.market_probs,
        dataset.time_pcts, dataset.bar_indices,
        initial_bankroll=10_000.0,
    )

    # 8. Print results
    logger.info("=" * 60)
    logger.info("BACKTEST RESULTS")
    logger.info("=" * 60)
    for k, v in result.metrics.items():
        logger.info("  %-25s %s", k, f"{v:.4f}" if isinstance(v, float) else v)

    logger.info("")
    logger.info("TIME-SEGMENTED ROI (validates early-bar thesis):")
    logger.info("%-15s %10s %12s %10s", "Window", "N Trades", "ROI/Trade", "Win Rate")
    logger.info("-" * 50)
    for bucket, metrics in result.metrics_by_time_bucket.items():
        logger.info(
            "%-15s %10d %11.4f%% %9.1f%%",
            bucket,
            metrics["n_trades"],
            metrics["roi_per_trade"] * 100,
            metrics["win_rate"] * 100,
        )

    # Feature importance
    logger.info("")
    logger.info("TOP 10 FEATURES:")
    for name, imp in list(trainer.feature_importance.items())[:10]:
        logger.info("  %-30s %.0f", name, imp)

    # 9. Save model + calibrator
    model_dir = Path(args.model_dir) / f"{asset.value}_{timeframe.value}"
    trainer.save(model_dir / "model.lgb")
    calibrator.save(model_dir / "calibrator.pkl")
    logger.info("Model saved to %s", model_dir)


if __name__ == "__main__":
    main()
