#!/usr/bin/env python
"""CPCV validation: measure probability of backtest overfitting.

Runs Combinatorial Purged Cross-Validation on the FULL dataset to
compute PBO (Probability of Backtest Overfitting).

PBO < 0.40 = acceptable
PBO < 0.20 = good
PBO > 0.50 = likely overfit
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from qm.backtest.engine import BacktestEngine
from qm.backtest.validation.cpcv import CombPurgedKFoldCV
from qm.core.types import Asset, Timeframe
from qm.data.storage.parquet import ParquetStore
from qm.features.pipeline import FeaturePipeline
from qm.model.targets.binary import BinaryDirectionTarget

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("cpcv")


def main() -> None:
    logger.info("Loading data and features...")

    store = ParquetStore(base_dir=Path("data/raw/ohlcv"))
    bars_df = store.read_bars(Asset.BTC, Timeframe.M5)

    pipeline = FeaturePipeline()
    featured_df = pipeline.compute(bars_df)
    target = BinaryDirectionTarget(horizon_bars=1).compute(featured_df)
    featured_df = featured_df.with_columns(target)

    lookback = pipeline.max_lookback
    clean_df = featured_df.slice(lookback).drop_nulls(subset=["target"])

    feature_names = pipeline.feature_names
    X = clean_df.select(feature_names).fill_null(0).to_numpy().astype(np.float64)
    y = clean_df["target"].to_numpy().astype(np.float64)

    logger.info("Data: %d rows, %d features", len(X), len(feature_names))

    # Load best params from trained model
    model_path = Path("data/models/BTC_5m/model.txt")
    if not model_path.exists():
        logger.error("No trained model found. Run train_and_backtest.py first.")
        sys.exit(1)

    base_model = lgb.Booster(model_file=str(model_path))
    # Extract params (approximate — LightGBM doesn't expose all params easily)

    # CPCV: 8 groups, 2 test groups → C(8,2) = 28 paths
    cv = CombPurgedKFoldCV(n_groups=8, k_test_groups=2, purge_period=12, embargo_pct=0.01)
    logger.info("Running CPCV with %d paths...", cv.n_paths)

    engine = BacktestEngine(fee_bps=0.0, spread=0.02, min_edge=0.03)

    is_sharpes = []
    oos_sharpes = []

    for i, (train_idx, test_idx) in enumerate(cv.split(len(X))):
        # Train on this fold
        ds = lgb.Dataset(X[train_idx], y[train_idx])
        params = {
            "objective": "binary", "metric": "binary_logloss",
            "verbosity": -1, "n_estimators": 500,
            "learning_rate": 0.05, "max_depth": 6, "num_leaves": 31,
            "min_child_samples": 50, "subsample": 0.8, "colsample_bytree": 0.8,
            "seed": 42,
        }
        n_est = params.pop("n_estimators")
        model = lgb.train(params, ds, num_boost_round=n_est)

        # In-sample evaluation
        is_probs = model.predict(X[train_idx])
        is_metrics = engine.evaluate_model_fast(is_probs, y[train_idx])
        is_sharpes.append(is_metrics["sharpe"])

        # Out-of-sample evaluation
        oos_probs = model.predict(X[test_idx])
        oos_metrics = engine.evaluate_model_fast(oos_probs, y[test_idx])
        oos_sharpes.append(oos_metrics["sharpe"])

        logger.info(
            "  Path %2d/%d: IS Sharpe=%.2f, OOS Sharpe=%.2f, OOS Accuracy=%.4f, OOS Brier=%.4f",
            i + 1, cv.n_paths,
            is_metrics["sharpe"], oos_metrics["sharpe"],
            oos_metrics["accuracy"], oos_metrics["brier"],
        )

    is_arr = np.array(is_sharpes)
    oos_arr = np.array(oos_sharpes)

    # Compute PBO
    pbo = cv.probability_of_backtest_overfitting(is_arr, oos_arr)

    logger.info("")
    logger.info("=" * 60)
    logger.info("CPCV RESULTS (%d paths)", cv.n_paths)
    logger.info("=" * 60)
    logger.info("  IS Sharpe:  mean=%.2f, std=%.2f", is_arr.mean(), is_arr.std())
    logger.info("  OOS Sharpe: mean=%.2f, std=%.2f", oos_arr.mean(), oos_arr.std())
    logger.info("  PBO (Probability of Backtest Overfitting): %.4f", pbo)
    logger.info("")

    if pbo < 0.20:
        logger.info("  VERDICT: EXCELLENT — very low overfitting risk")
    elif pbo < 0.40:
        logger.info("  VERDICT: ACCEPTABLE — moderate overfitting risk")
    elif pbo < 0.50:
        logger.info("  VERDICT: CONCERNING — high overfitting risk")
    else:
        logger.info("  VERDICT: LIKELY OVERFIT — do not deploy")

    logger.info("")

    # Correlation between IS and OOS performance
    corr = np.corrcoef(is_arr, oos_arr)[0, 1]
    logger.info("  IS-OOS Sharpe correlation: %.4f", corr)
    logger.info("  (>0.5 = model generalizes well, <0.2 = overfitting)")

    # OOS consistency
    pct_positive_oos = (oos_arr > 0).mean()
    logger.info("  OOS paths with positive Sharpe: %.0f%% (%d/%d)",
                pct_positive_oos * 100, int((oos_arr > 0).sum()), len(oos_arr))

    logger.info("=" * 60)


if __name__ == "__main__":
    main()
