#!/usr/bin/env python
"""Sweep alternative target formulations to find which breaks the Brier floor.

Trains LightGBM (fast) with each target type on a single asset/timeframe
and compares Brier, accuracy, Sharpe, and edge metrics.

Usage:
    python scripts/sweep_targets.py --asset BTC --timeframe 5m --n-trials 10
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from qm.backtest.engine import BacktestEngine
from qm.backtest.metrics.calibration import brier_score, expected_calibration_error
from qm.backtest.validation.walk_forward import WalkForwardSplitter
from qm.core.types import Asset, Timeframe
from qm.data.storage.parquet import ParquetStore
from qm.features.pipeline import FeaturePipeline
from qm.model.calibration.calibrator import IsotonicCalibrator
from qm.model.targets.binary import BinaryDirectionTarget
from qm.model.targets.cumulative import CumulativeDirectionTarget
from qm.model.targets.magnitude import MagnitudeTarget
from qm.model.targets.threshold import ThresholdDirectionTarget
from qm.model.trainers.lgbm_trainer import LGBMTrainer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("sweep_targets")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Sweep target formulations")
    p.add_argument("--asset", default="BTC", choices=["BTC", "ETH", "SOL", "XRP"])
    p.add_argument("--timeframe", default="5m", choices=["5m", "15m", "1h"])
    p.add_argument("--n-trials", type=int, default=10)
    p.add_argument("--data-dir", default="data/raw/ohlcv")
    p.add_argument("--train-pct", type=float, default=0.80)
    return p.parse_args()


def _build_targets() -> list[tuple[str, object]]:
    """Build list of (name, target_builder) pairs to sweep."""
    return [
        ("binary_h1", BinaryDirectionTarget(horizon_bars=1)),
        ("binary_h3", BinaryDirectionTarget(horizon_bars=3)),
        ("binary_h12", BinaryDirectionTarget(horizon_bars=12)),
        ("cumul_h3", CumulativeDirectionTarget(horizon_bars=3)),
        ("cumul_h6", CumulativeDirectionTarget(horizon_bars=6)),
        ("cumul_h12", CumulativeDirectionTarget(horizon_bars=12)),
        ("magnitude", MagnitudeTarget(lookback=100)),
        ("threshold_30", ThresholdDirectionTarget(min_percentile=0.30, lookback=500)),
    ]


def _train_and_evaluate(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_test: np.ndarray,
    y_test: np.ndarray,
    feature_names: list[str],
    n_trials: int,
    label: str,
) -> dict[str, float]:
    """Train LightGBM + calibrate + evaluate. Returns metrics dict."""
    import lightgbm as lgb

    logger.info("[%s] Training with %d samples, %d features...",
                label, len(y_train), len(feature_names))

    engine = BacktestEngine(min_edge=0.03)
    tp = min(len(X_train) // 2, 50000)
    tep = min(len(X_train) // 10, 10000)

    trainer = LGBMTrainer(
        n_trials=n_trials, n_splits=5,
        train_period=tp, test_period=tep,
        backtest_engine=engine, seed=42,
    )
    trainer.fit(X_train, y_train, feature_names=feature_names)

    # OOS calibration via walk-forward
    splitter = WalkForwardSplitter(
        n_splits=5, train_period=tp, test_period=tep,
        purge_period=12, embargo_period=6,
    )
    best_params = trainer.best_params.copy()
    n_estimators = best_params.pop("n_estimators", 500)
    if "lr" in best_params:
        best_params["learning_rate"] = best_params.pop("lr")
    if "min_child" in best_params:
        best_params["min_child_samples"] = best_params.pop("min_child")
    if "colsample" in best_params:
        best_params["colsample_bytree"] = best_params.pop("colsample")

    lgb_params = {
        "objective": "binary", "metric": "binary_logloss",
        "verbosity": -1, "seed": 42, **best_params,
    }

    oos_probs = np.zeros(len(y_train))
    oos_mask = np.zeros(len(y_train), dtype=bool)
    for train_idx, test_idx in splitter.split(len(X_train)):
        ds = lgb.Dataset(X_train[train_idx], y_train[train_idx])
        model = lgb.train(lgb_params, ds, num_boost_round=n_estimators)
        oos_probs[test_idx] = model.predict(X_train[test_idx])
        oos_mask[test_idx] = True

    oos_idx = np.where(oos_mask)[0]
    calibrator = IsotonicCalibrator()
    calibrator.fit(oos_probs[oos_idx], y_train[oos_idx])

    # Evaluate on test set
    raw_probs = trainer.predict_proba(X_test)
    cal_probs = calibrator.transform(raw_probs)

    return {
        "brier": brier_score(cal_probs, y_test),
        "ece": expected_calibration_error(cal_probs, y_test),
        "accuracy": float(np.mean((cal_probs > 0.5) == (y_test == 1))),
        "n_train": len(y_train),
        "n_test": len(y_test),
        "target_balance": float(y_train.mean()),
    }


def main() -> None:
    args = parse_args()
    asset = Asset(args.asset)
    timeframe = {
        "5m": Timeframe.M5, "15m": Timeframe.M15, "1h": Timeframe.H1,
    }[args.timeframe]

    logger.info("=" * 70)
    logger.info("TARGET SWEEP: %s %s", asset.value, timeframe.value)
    logger.info("=" * 70)

    # Load data + compute features (shared across all targets)
    store = ParquetStore(base_dir=Path(args.data_dir))
    bars_df = store.read_bars(asset, timeframe)
    if bars_df.is_empty():
        logger.error("No data for %s/%s", asset.value, timeframe.value)
        sys.exit(1)
    logger.info("Loaded %d bars", len(bars_df))

    pipeline = FeaturePipeline()
    featured_df = pipeline.compute(bars_df)
    feature_names = [f for f in pipeline.feature_names if f in featured_df.columns]
    lookback = pipeline.max_lookback

    logger.info("Features: %d", len(feature_names))

    # Sweep each target
    results = []
    targets = _build_targets()

    for target_name, target_builder in targets:
        logger.info("")
        logger.info("── Target: %s ──", target_name)
        t0 = time.time()

        # Compute target
        target = target_builder.compute(featured_df)
        df = featured_df.with_columns(target)

        # Clean: drop warmup + null targets
        clean = df.slice(lookback).drop_nulls(subset=["target"])
        logger.info("  Samples after cleanup: %d (dropped %d)",
                     len(clean), len(df) - len(clean))

        if len(clean) < 10000:
            logger.warning("  Too few samples (%d), skipping", len(clean))
            continue

        # Train/test split
        split_idx = int(len(clean) * args.train_pct)
        train_df = clean.slice(0, split_idx)
        test_df = clean.slice(split_idx)

        X_train = train_df.select(feature_names).fill_null(0).to_numpy().astype(np.float64)
        y_train = train_df["target"].to_numpy().astype(np.float64)
        X_test = test_df.select(feature_names).fill_null(0).to_numpy().astype(np.float64)
        y_test = test_df["target"].to_numpy().astype(np.float64)

        metrics = _train_and_evaluate(
            X_train, y_train, X_test, y_test,
            feature_names, args.n_trials, target_name,
        )
        metrics["target"] = target_name
        metrics["elapsed_s"] = time.time() - t0
        results.append(metrics)

        logger.info("  Brier: %.4f | Acc: %.4f | Balance: %.2f%% | Time: %.0fs",
                     metrics["brier"], metrics["accuracy"],
                     metrics["target_balance"] * 100, metrics["elapsed_s"])

    # Final report
    logger.info("")
    logger.info("=" * 70)
    logger.info("SWEEP RESULTS")
    logger.info("=" * 70)
    logger.info("")
    logger.info(
        "%-15s %8s %8s %8s %10s %8s",
        "Target", "Brier", "Acc", "ECE", "N_Train", "Balance",
    )
    logger.info("-" * 62)

    # Sort by Brier (best first)
    results.sort(key=lambda r: r["brier"])
    for r in results:
        logger.info(
            "%-15s %8.4f %8.4f %8.4f %10d %7.1f%%",
            r["target"], r["brier"], r["accuracy"], r["ece"],
            r["n_train"], r["target_balance"] * 100,
        )

    # Verdict
    best = results[0]
    baseline = next((r for r in results if r["target"] == "binary_h1"), results[-1])

    improvement = baseline["brier"] - best["brier"]
    logger.info("")
    if improvement > 0.005:
        logger.info(
            "VERDICT: '%s' improves Brier by %.4f over baseline — ADOPT",
            best["target"], improvement,
        )
    elif improvement > 0.001:
        logger.info(
            "VERDICT: '%s' shows marginal improvement (%.4f) — INVESTIGATE",
            best["target"], improvement,
        )
    else:
        logger.info(
            "VERDICT: No target significantly improves over baseline "
            "(best delta: %.4f). Signal may be insufficient for bar-level prediction.",
            improvement,
        )


if __name__ == "__main__":
    main()
