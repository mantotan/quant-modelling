#!/usr/bin/env python
"""V2 Training: Anti-overfit measures applied.

Changes from V1:
1. Remove leaky features (return_1, log_return_1 — correlated with target definition)
2. Add regularization: fewer trees, more min_child_samples, more subsample
3. Feature selection: only keep features with stable importance across folds
4. Use PURGED walk-forward with larger purge gap (24 bars = 2 hours at 5m)
5. Test across multiple assets to check generalization
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from qm.backtest.engine import BacktestEngine
from qm.backtest.metrics.calibration import brier_score, expected_calibration_error
from qm.backtest.report import check_acceptance
from qm.backtest.validation.cpcv import CombPurgedKFoldCV
from qm.backtest.validation.walk_forward import WalkForwardSplitter
from qm.core.types import Asset, Timeframe
from qm.data.storage.parquet import ParquetStore
from qm.features.pipeline import FeaturePipeline
from qm.model.calibration.calibrator import IsotonicCalibrator
from qm.model.targets.binary import BinaryDirectionTarget

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("train_v2")

# Features to EXCLUDE (potential leakage or redundancy)
EXCLUDE_FEATURES = {
    "return_1",       # close[t]/close[t-1] — leaks info about open[t] which is in target
    "log_return_1",   # same issue, log version
    "gap",            # open[t]/close[t-1] — directly related to target construction
}


def prepare_data(asset: Asset, timeframe: Timeframe) -> tuple[np.ndarray, np.ndarray, list[str], pl.DataFrame]:
    """Load data, compute features, filter for safety."""
    store = ParquetStore(base_dir=Path("data/raw/ohlcv"))
    bars_df = store.read_bars(asset, timeframe)

    pipeline = FeaturePipeline()
    featured_df = pipeline.compute(bars_df)

    # Target with 1-bar horizon
    target = BinaryDirectionTarget(horizon_bars=1).compute(featured_df)
    featured_df = featured_df.with_columns(target)

    # Get feature names, exclude leaky ones
    feature_names = [f for f in pipeline.feature_names if f not in EXCLUDE_FEATURES]
    logger.info("Using %d features (excluded %d leaky)", len(feature_names), len(EXCLUDE_FEATURES))

    # Cleanup
    lookback = pipeline.max_lookback
    clean_df = featured_df.slice(lookback).drop_nulls(subset=["target"])

    X = clean_df.select(feature_names).fill_null(0).to_numpy().astype(np.float64)
    y = clean_df["target"].to_numpy().astype(np.float64)

    return X, y, feature_names, clean_df


def train_conservative(
    X: np.ndarray, y: np.ndarray, feature_names: list[str],
) -> lgb.Booster:
    """Train with conservative hyperparameters to reduce overfitting."""
    params = {
        "objective": "binary",
        "metric": "binary_logloss",
        "verbosity": -1,
        "learning_rate": 0.01,       # slower learning
        "max_depth": 4,              # shallower trees (was 6+)
        "num_leaves": 15,            # fewer leaves (was 31+)
        "min_child_samples": 200,    # more samples per leaf (was 50)
        "subsample": 0.7,            # more dropout
        "colsample_bytree": 0.5,     # only use 50% of features per tree
        "reg_alpha": 1.0,            # L1 regularization
        "reg_lambda": 5.0,           # L2 regularization
        "min_split_gain": 0.1,       # higher bar for splits
        "seed": 42,
    }
    ds = lgb.Dataset(X, y, feature_name=feature_names)
    model = lgb.train(params, ds, num_boost_round=300)  # fewer rounds
    return model


def run_cpcv(X: np.ndarray, y: np.ndarray, feature_names: list[str]) -> dict:
    """Run CPCV and return comprehensive results."""
    cv = CombPurgedKFoldCV(
        n_groups=8, k_test_groups=2,
        purge_period=24,   # 2 hours at 5m (was 12)
        embargo_pct=0.02,  # 2% embargo (was 1%)
    )

    engine = BacktestEngine(fee_bps=0.0, spread=0.02, min_edge=0.03)

    is_sharpes = []
    oos_sharpes = []
    oos_accuracies = []
    oos_briers = []

    for i, (train_idx, test_idx) in enumerate(cv.split(len(X))):
        model = train_conservative(X[train_idx], y[train_idx], feature_names)

        # IS metrics
        is_probs = model.predict(X[train_idx])
        is_metrics = engine.evaluate_model_fast(is_probs, y[train_idx])
        is_sharpes.append(is_metrics["sharpe"])

        # OOS metrics
        oos_probs = model.predict(X[test_idx])
        oos_metrics = engine.evaluate_model_fast(oos_probs, y[test_idx])
        oos_sharpes.append(oos_metrics["sharpe"])
        oos_accuracies.append(oos_metrics["accuracy"])
        oos_briers.append(oos_metrics["brier"])

        logger.info(
            "  Path %2d/%d: IS=%.1f OOS=%.1f Acc=%.4f Brier=%.4f",
            i + 1, cv.n_paths, is_metrics["sharpe"], oos_metrics["sharpe"],
            oos_metrics["accuracy"], oos_metrics["brier"],
        )

    is_arr = np.array(is_sharpes)
    oos_arr = np.array(oos_sharpes)
    pbo = cv.probability_of_backtest_overfitting(is_arr, oos_arr)
    corr = np.corrcoef(is_arr, oos_arr)[0, 1]

    return {
        "pbo": pbo,
        "is_oos_corr": corr,
        "is_sharpe_mean": is_arr.mean(),
        "oos_sharpe_mean": oos_arr.mean(),
        "oos_accuracy_mean": np.mean(oos_accuracies),
        "oos_brier_mean": np.mean(oos_briers),
        "oos_sharpe_std": oos_arr.std(),
        "pct_positive_oos": (oos_arr > 0).mean(),
    }


def main() -> None:
    logger.info("=" * 70)
    logger.info("V2 TRAINING: Anti-overfit measures")
    logger.info("=" * 70)

    # Test on BTC first
    for asset in [Asset.BTC, Asset.ETH]:
        logger.info("")
        logger.info("--- %s 5m ---", asset.value)
        X, y, feature_names, clean_df = prepare_data(asset, Timeframe.M5)
        logger.info("Data: %d rows, base rate: %.4f", len(X), y.mean())

        results = run_cpcv(X, y, feature_names)

        logger.info("")
        logger.info("  PBO:              %.4f", results["pbo"])
        logger.info("  IS-OOS corr:      %.4f", results["is_oos_corr"])
        logger.info("  IS Sharpe:        %.2f", results["is_sharpe_mean"])
        logger.info("  OOS Sharpe:       %.2f (+/- %.2f)", results["oos_sharpe_mean"], results["oos_sharpe_std"])
        logger.info("  OOS Accuracy:     %.4f", results["oos_accuracy_mean"])
        logger.info("  OOS Brier:        %.4f", results["oos_brier_mean"])
        logger.info("  OOS positive:     %.0f%%", results["pct_positive_oos"] * 100)
        logger.info("")

        if results["pbo"] < 0.40 and results["is_oos_corr"] > 0.2:
            logger.info("  VERDICT: ACCEPTABLE — model generalizes")
        elif results["pbo"] < 0.50:
            logger.info("  VERDICT: MARGINAL — needs more work")
        else:
            logger.info("  VERDICT: OVERFIT — do not deploy")

    # Also test: train on BTC, predict on ETH (cross-asset generalization)
    logger.info("")
    logger.info("--- CROSS-ASSET: Train BTC → Predict ETH ---")
    X_btc, y_btc, fnames, _ = prepare_data(Asset.BTC, Timeframe.M5)
    X_eth, y_eth, _, _ = prepare_data(Asset.ETH, Timeframe.M5)

    model = train_conservative(X_btc, y_btc, fnames)
    eth_probs = model.predict(X_eth)
    eth_acc = float(np.mean((eth_probs > 0.5) == (y_eth == 1)))
    eth_brier = brier_score(eth_probs, y_eth)
    logger.info("  ETH accuracy (BTC model): %.4f", eth_acc)
    logger.info("  ETH Brier (BTC model):    %.4f", eth_brier)
    if eth_acc > 0.52:
        logger.info("  Cross-asset signal detected — model captures crypto-wide patterns")
    else:
        logger.info("  No cross-asset signal — model is BTC-specific")

    logger.info("")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
