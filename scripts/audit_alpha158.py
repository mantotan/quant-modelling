#!/usr/bin/env python
"""Audit Alpha158-inspired features: measure impact on Sentinel model.

Trains LightGBM with and without the 22 new Alpha158 features, comparing
Brier, Sharpe, accuracy.  Also runs the 3-stage feature selection filter
(which train_sentinel.py does NOT call) to report which new features survive
and flag collinear pairs.

Usage:
    python scripts/audit_alpha158.py --asset BTC --timeframe 5m
    python scripts/audit_alpha158.py --asset ETH --timeframe 15m --n-trials 30
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from qm.backtest.engine import BacktestEngine
from qm.backtest.metrics.calibration import brier_score, expected_calibration_error
from qm.core.types import Asset, Timeframe
from qm.data.storage.parquet import ParquetStore
from qm.features.pipeline import FeaturePipeline
from qm.features.selection import select_features
from qm.model.calibration.calibrator import IsotonicCalibrator
from qm.model.targets.binary import BinaryDirectionTarget
from qm.model.trainers.lgbm_trainer import LGBMTrainer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("audit_alpha158")

# New Alpha158-inspired features to audit
ALPHA158_FEATURES = {
    "autocorr_1", "autocorr_2", "autocorr_3", "autocorr_5", "autocorr_sum",
    "vp_corr_10", "vp_corr_20", "vp_divergence", "vp_corr_change",
    "range_pct_10", "range_pct_20", "range_std_10", "range_ratio",
    "vwap_zscore_10", "vwap_zscore_20", "vwap_zscore_cross",
    "return_rank_20", "volume_rank_20", "range_rank_20",
    "turnover_ratio", "turnover_trend", "turnover_accel",
}

# Known collinearity pairs to check
COLLINEARITY_PAIRS = [
    ("turnover_ratio", "volume_ratio"),
    ("vwap_zscore_10", "vwap_deviation"),
    ("range_pct_10", "parkinson_vol_10"),
]

PROTECTED_PREFIXES = [
    "funding_", "liquidation_", "regime_", "leverage_",
    "oi_", "iv_", "pm_", "btc_",
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Audit Alpha158 feature impact")
    p.add_argument("--asset", default="BTC", choices=["BTC", "ETH", "SOL", "XRP"])
    p.add_argument("--timeframe", default="5m", choices=["5m", "15m", "1h"])
    p.add_argument("--n-trials", type=int, default=30, help="Optuna HPO trials per config")
    p.add_argument("--data-dir", default="data/raw/ohlcv")
    p.add_argument("--train-pct", type=float, default=0.80)
    return p.parse_args()


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

    from qm.backtest.validation.walk_forward import WalkForwardSplitter

    logger.info("[%s] Training with %d features, %d trials...", label, len(feature_names), n_trials)
    trainer = LGBMTrainer(
        n_trials=n_trials,
        n_splits=5,
        train_period=min(len(X_train) // 2, 50000),
        test_period=min(len(X_train) // 10, 10000),
        backtest_engine=BacktestEngine(min_edge=0.03),
        seed=42,
    )
    trainer.fit(X_train, y_train, feature_names=feature_names)

    # Generate OOS predictions for calibration
    splitter = WalkForwardSplitter(
        n_splits=5,
        train_period=min(len(X_train) // 2, 50000),
        test_period=min(len(X_train) // 10, 10000),
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

    test_brier = brier_score(cal_probs, y_test)
    test_ece = expected_calibration_error(cal_probs, y_test)
    test_acc = float(np.mean((cal_probs > 0.5) == (y_test == 1)))

    engine = BacktestEngine(min_edge=0.03)
    fast_metrics = engine.evaluate_model_fast(
        cal_probs, y_test, np.full(len(y_test), 0.5),
    )

    results = {
        "brier": test_brier,
        "ece": test_ece,
        "accuracy": test_acc,
        "sharpe": fast_metrics.get("sharpe", 0.0),
        "n_trades": fast_metrics.get("n_trades", 0),
        "total_pnl": fast_metrics.get("total_pnl", 0.0),
        "n_features": len(feature_names),
    }

    # Feature importance (top 20)
    fi = trainer.feature_importance
    top20 = list(fi.items())[:20]
    results["top20_features"] = ", ".join(f"{n}={v:.0f}" for n, v in top20)
    results["alpha158_in_top20"] = sum(1 for n, _ in top20 if n in ALPHA158_FEATURES)

    return results


def main() -> None:
    args = parse_args()
    asset = Asset(args.asset)
    timeframe = {"5m": Timeframe.M5, "15m": Timeframe.M15, "1h": Timeframe.H1}[args.timeframe]

    logger.info("=" * 70)
    logger.info("ALPHA158 FEATURE AUDIT: %s %s", asset.value, timeframe.value)
    logger.info("=" * 70)

    # 1. Load data
    store = ParquetStore(base_dir=Path(args.data_dir))
    bars_df = store.read_bars(asset, timeframe)
    if bars_df.is_empty():
        logger.error("No data for %s/%s", asset.value, timeframe.value)
        sys.exit(1)
    logger.info("Loaded %d bars", len(bars_df))

    # 2. Compute all features (including new Alpha158 groups)
    pipeline = FeaturePipeline()
    featured_df = pipeline.compute(bars_df)
    # Filter to features that actually exist (alpha groups no-op if data absent)
    all_feature_names = [
        f for f in pipeline.feature_names if f in featured_df.columns
    ]
    logger.info("Total features available: %d", len(all_feature_names))

    # 3. Construct targets
    target_builder = BinaryDirectionTarget(horizon_bars=1)
    target = target_builder.compute(featured_df)
    featured_df = featured_df.with_columns(target)
    lookback = pipeline.max_lookback
    clean_df = featured_df.slice(lookback).drop_nulls(subset=["target"])

    # 4. Feature selection analysis
    logger.info("")
    logger.info("── Feature Selection Analysis ──")
    feature_df = clean_df.select(all_feature_names)
    target_series = clean_df["target"]

    selected = select_features(
        feature_df, target_series, protected_prefixes=PROTECTED_PREFIXES,
    )
    new_survived = [f for f in selected if f in ALPHA158_FEATURES]
    new_dropped = ALPHA158_FEATURES - set(selected)
    logger.info("Features selected: %d / %d", len(selected), len(all_feature_names))
    logger.info(
        "New Alpha158 survived: %d / %d: %s",
        len(new_survived), len(ALPHA158_FEATURES), new_survived,
    )
    logger.info("New Alpha158 dropped: %s", sorted(new_dropped))

    # 5. Collinearity check
    logger.info("")
    logger.info("── Collinearity Check ──")
    for f1, f2 in COLLINEARITY_PAIRS:
        if f1 in feature_df.columns and f2 in feature_df.columns:
            c1 = feature_df[f1].to_numpy().astype(np.float64)
            c2 = feature_df[f2].to_numpy().astype(np.float64)
            mask = ~(np.isnan(c1) | np.isnan(c2))
            if mask.sum() > 20:
                corr = np.corrcoef(c1[mask], c2[mask])[0, 1]
                flag = " ⚠ HIGH" if abs(corr) > 0.90 else ""
                logger.info("  %s vs %s: corr=%.3f%s", f1, f2, corr, flag)

    # 6. Train/test split
    split_idx = int(len(clean_df) * args.train_pct)
    train_df = clean_df.slice(0, split_idx)
    test_df = clean_df.slice(split_idx)
    y_train = train_df["target"].to_numpy().astype(np.float64)
    y_test = test_df["target"].to_numpy().astype(np.float64)

    # 7. Config A: All features (with Alpha158)
    logger.info("")
    logger.info("── Config A: All features (with Alpha158) ──")
    X_train_all = train_df.select(all_feature_names).fill_null(0).to_numpy().astype(np.float64)
    X_test_all = test_df.select(all_feature_names).fill_null(0).to_numpy().astype(np.float64)
    results_a = _train_and_evaluate(
        X_train_all, y_train, X_test_all, y_test, all_feature_names, args.n_trials, "ALL",
    )

    # 8. Config B: Without Alpha158 features
    logger.info("")
    logger.info("── Config B: Without Alpha158 features ──")
    orig_features = [f for f in all_feature_names if f not in ALPHA158_FEATURES]
    X_train_orig = train_df.select(orig_features).fill_null(0).to_numpy().astype(np.float64)
    X_test_orig = test_df.select(orig_features).fill_null(0).to_numpy().astype(np.float64)
    results_b = _train_and_evaluate(
        X_train_orig, y_train, X_test_orig, y_test, orig_features, args.n_trials, "ORIG",
    )

    # 9. Report
    logger.info("")
    logger.info("=" * 70)
    logger.info("AUDIT RESULTS")
    logger.info("=" * 70)
    logger.info("")
    logger.info("%-25s %12s %12s %10s", "Metric", "All Features", "Without A158", "Delta")
    logger.info("-" * 62)
    for metric in ["brier", "ece", "accuracy", "sharpe", "n_trades", "total_pnl"]:
        va = results_a[metric]
        vb = results_b[metric]
        delta = va - vb
        # For brier/ece, lower is better (negative delta = improvement)
        logger.info("%-25s %12.4f %12.4f %+10.4f", metric, va, vb, delta)

    logger.info("")
    logger.info("n_features:  ALL=%d  ORIG=%d", results_a["n_features"], results_b["n_features"])
    logger.info("Alpha158 features in top-20 importance: %d", results_a["alpha158_in_top20"])
    logger.info("")

    # Verdict
    brier_improvement = results_b["brier"] - results_a["brier"]
    if brier_improvement > 0.001:
        logger.info(
            "VERDICT: Alpha158 features IMPROVE Brier by %.4f — KEEP",
            brier_improvement,
        )
    elif brier_improvement > -0.001:
        logger.info(
            "VERDICT: Alpha158 features have NEGLIGIBLE impact (%.4f) — NEUTRAL",
            brier_improvement,
        )
    else:
        logger.info(
            "VERDICT: Alpha158 features HURT Brier by %.4f — INVESTIGATE",
            -brier_improvement,
        )


if __name__ == "__main__":
    main()
