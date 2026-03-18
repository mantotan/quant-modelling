#!/usr/bin/env python
"""V3 Training: Correct target + aggressive HPO to find real signal.

Target: close[t+1] >= open[t+1] (did the NEXT bar go up?)
This is what Polymarket actually resolves.

Expected: accuracy will be much closer to 50%. Even 52-53% with
good calibration can be very profitable on Polymarket.
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

import lightgbm as lgb
import numpy as np
import polars as pl
import optuna

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from qm.backtest.engine import BacktestEngine
from qm.backtest.metrics.calibration import brier_score, expected_calibration_error
from qm.backtest.report import check_acceptance
from qm.backtest.validation.walk_forward import WalkForwardSplitter
from qm.core.types import Asset, Timeframe
from qm.data.storage.parquet import ParquetStore
from qm.features.cross_asset import CrossAssetPipeline
from qm.features.pipeline import FeaturePipeline
from qm.features.selection import select_features
from qm.model.calibration.calibrator import IsotonicCalibrator
from qm.model.targets.binary import BinaryDirectionTarget

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("train_v3")
optuna.logging.set_verbosity(optuna.logging.WARNING)

EXCLUDE_FEATURES = {"return_1", "log_return_1", "gap"}


def main() -> None:
    t0 = time.time()
    logger.info("=" * 70)
    logger.info("V3 TRAINING: Correct target (close[t+1] >= open[t+1])")
    logger.info("=" * 70)

    # ── Load data ─────────────────────────────────────────────────
    store = ParquetStore(base_dir=Path("data/raw/ohlcv"))
    metrics_store = ParquetStore(base_dir=Path("data/raw/metrics"))
    pipeline = FeaturePipeline()
    cross_pipeline = CrossAssetPipeline(
        store, Timeframe.M5, pipeline=pipeline,
        metrics_store=metrics_store,
    )

    assets_results = {}

    for asset in [Asset.BTC, Asset.ETH, Asset.SOL, Asset.XRP]:
        logger.info("")
        logger.info("━" * 70)
        logger.info("ASSET: %s 5m", asset.value)
        logger.info("━" * 70)

        # Features (with cross-asset context)
        featured = cross_pipeline.compute(asset)
        if featured.is_empty():
            continue
        available_cols = set(featured.columns)
        feature_names = [f for f in cross_pipeline.feature_names(asset)
                         if f not in EXCLUDE_FEATURES and f in available_cols]

        # CORRECT target
        target = BinaryDirectionTarget(horizon_bars=1).compute(featured)
        featured = featured.with_columns(target)

        lookback = cross_pipeline.max_lookback
        clean = featured.slice(lookback).drop_nulls(subset=["target"])

        # 80/20 temporal split
        split = int(len(clean) * 0.80)
        train_df = clean.slice(0, split)
        test_df = clean.slice(split)

        X_train = train_df.select(feature_names).fill_null(0).to_numpy().astype(np.float64)
        y_train = train_df["target"].to_numpy().astype(np.float64)
        X_test = test_df.select(feature_names).fill_null(0).to_numpy().astype(np.float64)
        y_test = test_df["target"].to_numpy().astype(np.float64)

        logger.info("Data: %d train, %d test, %d features, base rate: %.4f",
                    len(X_train), len(X_test), len(feature_names), y_train.mean())

        # ── Feature selection ─────────────────────────────────────
        logger.info("Running feature selection...")
        selected = select_features(
            train_df.select(feature_names).fill_null(0),
            train_df["target"],
            missing_threshold=0.5,
            min_target_corr=0.005,  # lower bar — signal is weak
            max_pairwise_corr=0.90,
        )
        if len(selected) < 5:
            selected = feature_names  # fallback if too aggressive
        logger.info("Selected %d/%d features", len(selected), len(feature_names))

        X_train_sel = train_df.select(selected).fill_null(0).to_numpy().astype(np.float64)
        X_test_sel = test_df.select(selected).fill_null(0).to_numpy().astype(np.float64)

        # ── Optuna HPO ────────────────────────────────────────────
        logger.info("Running Optuna HPO (100 trials)...")

        splitter = WalkForwardSplitter(
            n_splits=5,
            train_period=min(len(X_train_sel) // 2, 50000),
            test_period=min(len(X_train_sel) // 10, 10000),
            purge_period=24,
            embargo_period=12,
        )

        best_val_brier = [1.0]

        def objective(trial: optuna.Trial) -> float:
            params = {
                "objective": "binary",
                "metric": "binary_logloss",
                "verbosity": -1,
                "device": "gpu",
                "n_estimators": trial.suggest_int("n_estimators", 50, 1000),
                "learning_rate": trial.suggest_float("lr", 0.005, 0.1, log=True),
                "max_depth": trial.suggest_int("max_depth", 2, 8),
                "num_leaves": trial.suggest_int("num_leaves", 7, 127),
                "min_child_samples": trial.suggest_int("min_child", 50, 500),
                "subsample": trial.suggest_float("subsample", 0.5, 1.0),
                "colsample_bytree": trial.suggest_float("colsample", 0.3, 1.0),
                "reg_alpha": trial.suggest_float("reg_alpha", 1e-8, 10.0, log=True),
                "reg_lambda": trial.suggest_float("reg_lambda", 1e-8, 10.0, log=True),
                "min_split_gain": trial.suggest_float("min_gain", 0.0, 1.0),
                "seed": 42,
            }

            briers = []
            n_est = params.pop("n_estimators")
            if "lr" in params:
                params["learning_rate"] = params.pop("lr")
            if "min_child" in params:
                params["min_child_samples"] = params.pop("min_child")
            if "colsample" in params:
                params["colsample_bytree"] = params.pop("colsample")
            if "min_gain" in params:
                params["min_split_gain"] = params.pop("min_gain")

            for train_idx, test_idx in splitter.split(len(X_train_sel)):
                ds = lgb.Dataset(X_train_sel[train_idx], y_train[train_idx])
                model = lgb.train(params, ds, num_boost_round=n_est)
                preds = model.predict(X_train_sel[test_idx])
                briers.append(float(np.mean((preds - y_train[test_idx]) ** 2)))

            avg_brier = np.mean(briers)
            if avg_brier < best_val_brier[0]:
                best_val_brier[0] = avg_brier
            return avg_brier

        study = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=42))
        study.optimize(objective, n_trials=100, n_jobs=1)

        logger.info("Best HPO Brier: %.6f", study.best_value)

        # ── Retrain with best params ──────────────────────────────
        bp = study.best_params.copy()
        n_est = bp.pop("n_estimators", 500)
        if "lr" in bp: bp["learning_rate"] = bp.pop("lr")
        if "min_child" in bp: bp["min_child_samples"] = bp.pop("min_child")
        if "colsample" in bp: bp["colsample_bytree"] = bp.pop("colsample")
        if "min_gain" in bp: bp["min_split_gain"] = bp.pop("min_gain")

        final_params = {"objective": "binary", "metric": "binary_logloss", "verbosity": -1, "device": "gpu", "seed": 42, **bp}
        ds_final = lgb.Dataset(X_train_sel, y_train, feature_name=selected)
        model_final = lgb.train(final_params, ds_final, num_boost_round=n_est)

        # ── Calibrate ─────────────────────────────────────────────
        # OOS predictions for calibration
        oos_probs = np.zeros(len(y_train))
        oos_mask = np.zeros(len(y_train), dtype=bool)
        for train_idx, test_idx in splitter.split(len(X_train_sel)):
            ds = lgb.Dataset(X_train_sel[train_idx], y_train[train_idx])
            m = lgb.train(final_params, ds, num_boost_round=n_est)
            oos_probs[test_idx] = m.predict(X_train_sel[test_idx])
            oos_mask[test_idx] = True

        cal = IsotonicCalibrator()
        cal.fit(oos_probs[oos_mask], y_train[oos_mask])

        # ── Test set evaluation ───────────────────────────────────
        raw_test = model_final.predict(X_test_sel)
        cal_test = cal.transform(raw_test)

        acc = float(np.mean((cal_test > 0.5) == (y_test == 1)))
        brier = brier_score(cal_test, y_test)
        ece = expected_calibration_error(cal_test, y_test)
        base_rate = float(y_test.mean())

        logger.info("")
        logger.info("TEST SET RESULTS:")
        logger.info("  Accuracy:  %.4f  (base rate: %.4f, lift: %.4f)",
                    acc, base_rate, acc - base_rate)
        logger.info("  Brier:     %.6f  (uninformed: %.6f)", brier, base_rate * (1 - base_rate))
        logger.info("  ECE:       %.4f", ece)

        # Backtest with realistic assumptions
        engine = BacktestEngine(fee_bps=0.0, spread=0.02, min_edge=0.01)
        result = engine.run_full_simulation(
            model_probs=cal_test,
            targets=y_test,
            timestamps=np.arange(len(y_test)),
            market_probs=np.full(len(y_test), base_rate),  # market knows the base rate
            initial_bankroll=10_000.0,
            kelly_fraction=0.25,
        )

        m = result.metrics
        logger.info("  Backtest PnL:    $%.2f", m["total_pnl"])
        logger.info("  Trades:          %d", m["n_trades"])
        logger.info("  Win rate:        %.4f", m["win_rate"])
        logger.info("  Sharpe:          %.2f", m["sharpe"])

        # Feature importance
        fi = dict(zip(model_final.feature_name(), model_final.feature_importance(importance_type="gain")))
        fi_sorted = sorted(fi.items(), key=lambda x: -x[1])[:10]
        logger.info("")
        logger.info("  Top 10 features:")
        for fname, imp in fi_sorted:
            logger.info("    %-25s %.0f", fname, imp)

        assets_results[asset.value] = {"accuracy": acc, "brier": brier, "ece": ece, "pnl": m["total_pnl"]}

        # Save model
        model_dir = Path("data/models") / f"{asset.value}_5m_v3"
        model_dir.mkdir(parents=True, exist_ok=True)
        model_final.save_model(str(model_dir / "model.txt"))
        cal.save(model_dir / "calibrator.pkl")

    # Summary
    logger.info("")
    logger.info("=" * 70)
    logger.info("SUMMARY (correct target: close[t+1] >= open[t+1])")
    logger.info("=" * 70)
    logger.info("%-6s | %8s %8s %8s %10s", "Asset", "Acc", "Brier", "ECE", "PnL")
    logger.info("-" * 50)
    for asset_name, r in assets_results.items():
        logger.info("%-6s | %7.4f  %7.6f  %7.4f  %9.2f",
                    asset_name, r["accuracy"], r["brier"], r["ece"], r["pnl"])

    logger.info("")
    logger.info("Total time: %.0f seconds", time.time() - t0)
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
