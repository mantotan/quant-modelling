#!/usr/bin/env python
"""Multi-timeframe, multi-asset, multi-regime analysis.

Tests model accuracy across:
1. Timeframes: 5m, 15m, 1h
2. Assets: BTC, ETH, SOL, XRP
3. Market regimes: bear (2022), recovery (2023), bull (2024), range (2025-2026)
4. Walk-forward temporal splits (train on past, test on future)

Goal: find where the model genuinely works and where it breaks.
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
from qm.core.types import Asset, Timeframe
from qm.data.storage.parquet import ParquetStore
from qm.features.pipeline import FeaturePipeline
from qm.model.calibration.calibrator import IsotonicCalibrator
from qm.model.targets.binary import BinaryDirectionTarget

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("regime")

# Features to exclude (identified as leaky in V1)
EXCLUDE_FEATURES = {"return_1", "log_return_1", "gap"}

# Market regime date boundaries
REGIMES = {
    "bear_2022":     ("2022-01-01", "2022-12-31"),  # BTC 48k→16k
    "recovery_2023": ("2023-01-01", "2023-12-31"),  # BTC 16k→42k
    "bull_2024":     ("2024-01-01", "2024-12-31"),  # BTC 42k→93k, ETF approval
    "range_2025":    ("2025-01-01", "2025-12-31"),  # BTC oscillating 80-105k
    "recent_2026":   ("2026-01-01", "2026-12-31"),  # most recent
}

# Conservative LightGBM params (from V2 anti-overfit analysis)
LGB_PARAMS = {
    "objective": "binary",
    "metric": "binary_logloss",
    "verbosity": -1,
    "learning_rate": 0.01,
    "max_depth": 4,
    "num_leaves": 15,
    "min_child_samples": 200,
    "subsample": 0.7,
    "colsample_bytree": 0.5,
    "reg_alpha": 1.0,
    "reg_lambda": 5.0,
    "min_split_gain": 0.1,
    "seed": 42,
}
N_ROUNDS = 300


def load_and_prepare(asset: Asset, timeframe: Timeframe) -> tuple[pl.DataFrame, list[str]]:
    """Load data, compute features, return clean DataFrame + feature names."""
    store = ParquetStore(base_dir=Path("data/raw/ohlcv"))
    bars = store.read_bars(asset, timeframe)
    if bars.is_empty():
        return pl.DataFrame(), []

    pipeline = FeaturePipeline()
    featured = pipeline.compute(bars)
    target = BinaryDirectionTarget(horizon_bars=1).compute(featured)
    featured = featured.with_columns(target)

    feature_names = [f for f in pipeline.feature_names if f not in EXCLUDE_FEATURES]
    lookback = pipeline.max_lookback
    clean = featured.slice(lookback).drop_nulls(subset=["target"])
    return clean, feature_names


def train_and_eval(
    X_train: np.ndarray, y_train: np.ndarray,
    X_test: np.ndarray, y_test: np.ndarray,
    feature_names: list[str],
) -> dict[str, float]:
    """Train model, calibrate, evaluate. Returns metrics dict."""
    # Train
    ds = lgb.Dataset(X_train, y_train, feature_name=feature_names)
    model = lgb.train(LGB_PARAMS, ds, num_boost_round=N_ROUNDS)

    # Raw predictions
    raw_train = model.predict(X_train)
    raw_test = model.predict(X_test)

    # Calibrate on train OOS (simple hold-out from end of train)
    cal_split = int(len(raw_train) * 0.8)
    cal = IsotonicCalibrator()
    cal.fit(raw_train[cal_split:], y_train[cal_split:])
    cal_test = cal.transform(raw_test)

    # Metrics
    acc = float(np.mean((cal_test > 0.5) == (y_test == 1)))
    brier = brier_score(cal_test, y_test)
    ece = expected_calibration_error(cal_test, y_test)

    # Directional bias
    up_pct = float((cal_test > 0.5).mean())

    return {
        "accuracy": acc,
        "brier": brier,
        "ece": ece,
        "up_bias": up_pct,
        "n_test": len(y_test),
        "base_rate": float(y_test.mean()),
    }


def split_by_date(df: pl.DataFrame, start: str, end: str) -> pl.DataFrame:
    """Filter DataFrame by date range."""
    from datetime import datetime, timezone
    start_dt = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
    end_dt = datetime.fromisoformat(end).replace(tzinfo=timezone.utc)
    return df.filter(
        (pl.col("time") >= start_dt) & (pl.col("time") < end_dt)
    )


def main() -> None:
    logger.info("=" * 100)
    logger.info("MULTI-TIMEFRAME, MULTI-ASSET, MULTI-REGIME ANALYSIS")
    logger.info("=" * 100)

    # ═══════════════════════════════════════════════════════════════════
    # PART 1: All assets × all timeframes (full dataset, 80/20 split)
    # ═══════════════════════════════════════════════════════════════════
    logger.info("")
    logger.info("PART 1: Asset × Timeframe Matrix (train first 80%%, test last 20%%)")
    logger.info("-" * 100)
    logger.info("%-6s %-4s | %8s %8s %8s %8s %8s %8s",
                "Asset", "TF", "Acc", "Brier", "ECE", "UpBias", "BaseRate", "TestN")
    logger.info("-" * 100)

    results_matrix = {}
    for asset in [Asset.BTC, Asset.ETH, Asset.SOL, Asset.XRP]:
        for tf in [Timeframe.M5, Timeframe.M15, Timeframe.H1]:
            df, fnames = load_and_prepare(asset, tf)
            if df.is_empty() or len(fnames) == 0:
                logger.info("%-6s %-4s | NO DATA", asset.value, tf.value)
                continue

            split = int(len(df) * 0.80)
            X_train = df.slice(0, split).select(fnames).fill_null(0).to_numpy().astype(np.float64)
            y_train = df.slice(0, split)["target"].to_numpy().astype(np.float64)
            X_test = df.slice(split).select(fnames).fill_null(0).to_numpy().astype(np.float64)
            y_test = df.slice(split)["target"].to_numpy().astype(np.float64)

            m = train_and_eval(X_train, y_train, X_test, y_test, fnames)
            results_matrix[(asset.value, tf.value)] = m

            logger.info(
                "%-6s %-4s | %7.4f  %7.4f  %7.4f  %7.4f  %7.4f  %7d",
                asset.value, tf.value,
                m["accuracy"], m["brier"], m["ece"], m["up_bias"], m["base_rate"], m["n_test"],
            )

    # ═══════════════════════════════════════════════════════════════════
    # PART 2: Regime analysis for BTC 5m (train on each regime, test on next)
    # ═══════════════════════════════════════════════════════════════════
    logger.info("")
    logger.info("PART 2: BTC 5m Regime Walk-Forward (train on regime N, test on regime N+1)")
    logger.info("-" * 100)

    btc_df, btc_fnames = load_and_prepare(Asset.BTC, Timeframe.M5)

    regime_names = list(REGIMES.keys())
    logger.info("%-20s → %-20s | %8s %8s %8s %8s %8s",
                "Train Regime", "Test Regime", "Acc", "Brier", "ECE", "BaseRate", "TestN")
    logger.info("-" * 100)

    for i in range(len(regime_names) - 1):
        train_name = regime_names[i]
        test_name = regime_names[i + 1]
        train_start, train_end = REGIMES[train_name]
        test_start, test_end = REGIMES[test_name]

        train_slice = split_by_date(btc_df, train_start, train_end)
        test_slice = split_by_date(btc_df, test_start, test_end)

        if train_slice.is_empty() or test_slice.is_empty():
            logger.info("%-20s → %-20s | NO DATA", train_name, test_name)
            continue

        X_tr = train_slice.select(btc_fnames).fill_null(0).to_numpy().astype(np.float64)
        y_tr = train_slice["target"].to_numpy().astype(np.float64)
        X_te = test_slice.select(btc_fnames).fill_null(0).to_numpy().astype(np.float64)
        y_te = test_slice["target"].to_numpy().astype(np.float64)

        m = train_and_eval(X_tr, y_tr, X_te, y_te, btc_fnames)
        logger.info(
            "%-20s → %-20s | %7.4f  %7.4f  %7.4f  %7.4f  %7d",
            train_name, test_name,
            m["accuracy"], m["brier"], m["ece"], m["base_rate"], m["n_test"],
        )

    # ═══════════════════════════════════════════════════════════════════
    # PART 3: Cumulative training (expanding window across regimes)
    # ═══════════════════════════════════════════════════════════════════
    logger.info("")
    logger.info("PART 3: BTC 5m Expanding Window (train on ALL data up to regime, test on next)")
    logger.info("-" * 100)
    logger.info("%-35s → %-20s | %8s %8s %8s %8s",
                "Train (cumulative)", "Test Regime", "Acc", "Brier", "ECE", "TestN")
    logger.info("-" * 100)

    for i in range(1, len(regime_names)):
        # Train on everything before this regime
        test_name = regime_names[i]
        test_start, test_end = REGIMES[test_name]

        # Cumulative train: all data before test_start
        from datetime import datetime, timezone
        test_start_dt = datetime.fromisoformat(test_start).replace(tzinfo=timezone.utc)
        train_slice = btc_df.filter(pl.col("time") < test_start_dt)
        test_slice = split_by_date(btc_df, test_start, test_end)

        if train_slice.is_empty() or test_slice.is_empty():
            continue

        X_tr = train_slice.select(btc_fnames).fill_null(0).to_numpy().astype(np.float64)
        y_tr = train_slice["target"].to_numpy().astype(np.float64)
        X_te = test_slice.select(btc_fnames).fill_null(0).to_numpy().astype(np.float64)
        y_te = test_slice["target"].to_numpy().astype(np.float64)

        train_label = " + ".join(regime_names[:i])
        m = train_and_eval(X_tr, y_tr, X_te, y_te, btc_fnames)
        logger.info(
            "%-35s → %-20s | %7.4f  %7.4f  %7.4f  %7d",
            train_label[:35], test_name,
            m["accuracy"], m["brier"], m["ece"], m["n_test"],
        )

    # ═══════════════════════════════════════════════════════════════════
    # PART 4: Cross-asset transfer (train on one, test on others)
    # ═══════════════════════════════════════════════════════════════════
    logger.info("")
    logger.info("PART 4: Cross-Asset Transfer (5m, train on X, test on Y)")
    logger.info("-" * 100)
    logger.info("%-6s → %-6s | %8s %8s %8s",
                "Train", "Test", "Acc", "Brier", "ECE")
    logger.info("-" * 100)

    asset_data = {}
    for asset in [Asset.BTC, Asset.ETH, Asset.SOL, Asset.XRP]:
        df, fnames = load_and_prepare(asset, Timeframe.M5)
        if not df.is_empty():
            asset_data[asset] = (df, fnames)

    for train_asset in [Asset.BTC, Asset.ETH, Asset.SOL, Asset.XRP]:
        if train_asset not in asset_data:
            continue
        train_df, fnames = asset_data[train_asset]
        X_tr = train_df.select(fnames).fill_null(0).to_numpy().astype(np.float64)
        y_tr = train_df["target"].to_numpy().astype(np.float64)

        # Train model
        ds = lgb.Dataset(X_tr, y_tr, feature_name=fnames)
        model = lgb.train(LGB_PARAMS, ds, num_boost_round=N_ROUNDS)

        for test_asset in [Asset.BTC, Asset.ETH, Asset.SOL, Asset.XRP]:
            if test_asset not in asset_data:
                continue
            test_df, _ = asset_data[test_asset]
            X_te = test_df.select(fnames).fill_null(0).to_numpy().astype(np.float64)
            y_te = test_df["target"].to_numpy().astype(np.float64)

            raw = model.predict(X_te)
            acc = float(np.mean((raw > 0.5) == (y_te == 1)))
            brier = float(np.mean((raw - y_te) ** 2))

            marker = " ←same" if train_asset == test_asset else ""
            logger.info(
                "%-6s → %-6s | %7.4f  %7.4f  %8s%s",
                train_asset.value, test_asset.value, acc, brier, "", marker,
            )

    logger.info("")
    logger.info("=" * 100)
    logger.info("ANALYSIS COMPLETE")
    logger.info("=" * 100)


if __name__ == "__main__":
    main()
