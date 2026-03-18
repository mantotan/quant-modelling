#!/usr/bin/env python
"""Diagnose Pulse accuracy: real signal vs interpolation artifact.

The Pulse model shows 63% accuracy at t=0.003 (1 second into bar).
This script determines whether that comes from:
  A) Historical features (RSI, stoch, etc.) — genuine signal
  B) Tiny `distance_from_open` from interpolation — artifact

Tests:
  1. Train on ONLY real 1m boundary points (t=0.20, 0.40, 0.60, 0.80)
     — no interpolation, purely real data
  2. Train on ALL time points but ZERO OUT tick features
     — isolates historical feature signal
  3. Train on ALL time points but ZERO OUT historical features
     — isolates tick feature signal (possibly leaky)
  4. Compare per-time-point accuracy across all three
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import numpy as np

from qm.backtest.market_sim import MarketOddsSimulator
from qm.core.types import Asset, Timeframe
from qm.data.storage.parquet import ParquetStore
from qm.features.intrabar import CACHED_FEATURE_NAMES
from qm.features.pipeline import FeaturePipeline
from qm.model.targets.intrabar import RealPathIntraBarDataGenerator
from qm.model.trainers.pulse_trainer import PulseTrainer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def evaluate_accuracy_by_time(trainer, dataset, label):
    """Train model and report per-time-point OOS accuracy."""
    logger.info("")
    logger.info("=" * 60)
    logger.info("EXPERIMENT: %s", label)
    logger.info("=" * 60)

    metrics = trainer.fit(dataset)
    logger.info("Best CV Brier: %.4f, Accuracy: %.4f", metrics["brier"], metrics["accuracy"])

    oos_probs, oos_targets, oos_mask = trainer.get_oos_predictions(dataset)
    oos_idx = np.where(oos_mask)[0]

    if len(oos_idx) == 0:
        logger.warning("No OOS samples")
        return

    # Split: 70% calibration, 30% evaluation (same as honest pipeline)
    cal_end = int(len(oos_idx) * 0.7)
    bt_idx = oos_idx[cal_end:]

    bt_probs = oos_probs[bt_idx]
    bt_targets = oos_targets[bt_idx]
    bt_time_pcts = dataset.time_pcts[bt_idx]

    overall_acc = float(np.mean((bt_probs > 0.5) == (bt_targets == 1)))
    logger.info("Overall held-out accuracy: %.1f%%", overall_acc * 100)

    logger.info("")
    logger.info("%-10s %10s %10s", "time_pct", "N Samples", "Accuracy")
    logger.info("-" * 35)
    for tp in sorted(set(bt_time_pcts)):
        mask = bt_time_pcts == tp
        acc = float(np.mean((bt_probs[mask] > 0.5) == (bt_targets[mask] == 1)))
        logger.info("%-10.3f %10d %9.1f%%", tp, int(mask.sum()), acc * 100)


def main():
    store = ParquetStore(base_dir=Path("data/raw/ohlcv"))
    bars_df = store.read_bars(Asset.BTC, Timeframe.M5)
    m1_bars_df = store.read_bars(Asset.BTC, Timeframe.M1)

    pipeline = FeaturePipeline()
    featured_df = pipeline.compute(bars_df)
    available_cached = [c for c in CACHED_FEATURE_NAMES if c in featured_df.columns]
    history_features = featured_df.select(available_cached)

    market_sim = MarketOddsSimulator(efficiency=0.75, timeframe=Timeframe.M5)

    # ============================================================
    # Experiment 1: ONLY real 1m boundary points (no interpolation)
    # ============================================================
    gen = RealPathIntraBarDataGenerator(timeframe=Timeframe.M5)
    real_only_tps = [0.20, 0.40, 0.60, 0.80]  # exact 1m boundaries
    ds_real = gen.generate(bars_df, m1_bars_df, history_features, market_sim,
                           time_pcts=real_only_tps)
    logger.info("Real-only dataset: %d samples", len(ds_real.y))

    trainer1 = PulseTrainer(n_trials=10, n_splits=3, train_bars=5000, test_bars=1000)
    evaluate_accuracy_by_time(trainer1, ds_real, "REAL 1m BOUNDARIES ONLY (no interpolation)")

    # ============================================================
    # Experiment 2: All time points, ZERO OUT tick features (hist only)
    # ============================================================
    gen2 = RealPathIntraBarDataGenerator(timeframe=Timeframe.M5)
    ds_all = gen2.generate(bars_df, m1_bars_df, history_features, market_sim)
    logger.info("Full dataset: %d samples", len(ds_all.y))

    # Zero out tick features (columns 0-7), keep historical (columns 8-22)
    ds_hist_only = type(ds_all)(
        X=ds_all.X.copy(),
        y=ds_all.y.copy(),
        market_probs=ds_all.market_probs.copy(),
        bar_indices=ds_all.bar_indices.copy(),
        time_pcts=ds_all.time_pcts.copy(),
        feature_names=ds_all.feature_names,
    )
    ds_hist_only.X[:, 0:8] = 0.0  # zero all tick features

    trainer2 = PulseTrainer(n_trials=10, n_splits=3, train_bars=5000, test_bars=1000)
    evaluate_accuracy_by_time(trainer2, ds_hist_only,
                              "ALL time points, TICK FEATURES ZEROED (history only)")

    # ============================================================
    # Experiment 3: All time points, ZERO OUT historical features (ticks only)
    # ============================================================
    ds_tick_only = type(ds_all)(
        X=ds_all.X.copy(),
        y=ds_all.y.copy(),
        market_probs=ds_all.market_probs.copy(),
        bar_indices=ds_all.bar_indices.copy(),
        time_pcts=ds_all.time_pcts.copy(),
        feature_names=ds_all.feature_names,
    )
    ds_tick_only.X[:, 8:] = 0.0  # zero all historical features

    trainer3 = PulseTrainer(n_trials=10, n_splits=3, train_bars=5000, test_bars=1000)
    evaluate_accuracy_by_time(trainer3, ds_tick_only,
                              "ALL time points, HISTORICAL FEATURES ZEROED (ticks only)")

    # ============================================================
    # Experiment 4: Full model (baseline comparison)
    # ============================================================
    trainer4 = PulseTrainer(n_trials=10, n_splits=3, train_bars=5000, test_bars=1000)
    evaluate_accuracy_by_time(trainer4, ds_all, "FULL MODEL (all features, all time points)")

    # ============================================================
    # Summary
    # ============================================================
    logger.info("")
    logger.info("=" * 60)
    logger.info("INTERPRETATION GUIDE:")
    logger.info("=" * 60)
    logger.info("- If 'history only' shows ~50%% at all times -> no historical signal")
    logger.info("- If 'history only' shows ~52-55%% -> genuine Sentinel-like signal")
    logger.info("- If 'ticks only' shows 63%% at t=0.003 -> interpolation artifact")
    logger.info("- If 'ticks only' shows ~50%% at t=0.003 -> early accuracy was from history")
    logger.info("- Real boundaries (t=0.20+) accuracy = legitimate intra-bar signal")


if __name__ == "__main__":
    main()
