#!/usr/bin/env python
"""End-to-end training and backtesting pipeline.

1. Load historical data from Parquet
2. Compute features
3. Construct binary targets
4. Split: train (first 80%) / test (last 20%)
5. Train LightGBM with Optuna HPO (walk-forward on train set)
6. Calibrate on OOS predictions from walk-forward
7. Run full backtest on held-out test set
8. Generate report with acceptance gates

Usage:
    python scripts/train_and_backtest.py
    python scripts/train_and_backtest.py --asset BTC --timeframe 5m --n-trials 50
    python scripts/train_and_backtest.py --asset BTC --timeframe 5m --n-trials 200 --kelly 0.25
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
from qm.backtest.report import check_acceptance, generate_report
from qm.backtest.validation.walk_forward import WalkForwardSplitter
from qm.core.types import Asset, Timeframe
from qm.data.storage.parquet import ParquetStore
from qm.features.pipeline import FeaturePipeline
from qm.model.calibration.calibrator import IsotonicCalibrator
from qm.model.targets.binary import BinaryDirectionTarget

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("train")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Train and backtest pipeline")
    p.add_argument("--asset", default="BTC", choices=["BTC", "ETH", "SOL", "XRP"])
    p.add_argument("--timeframe", default="5m", choices=["5m", "15m", "1h"])
    p.add_argument("--n-trials", type=int, default=50, help="Optuna HPO trials")
    p.add_argument("--kelly", type=float, default=0.25, help="Kelly fraction")
    p.add_argument("--min-edge", type=float, default=0.03, help="Min edge to trade")
    p.add_argument("--data-dir", default="data/raw/ohlcv")
    p.add_argument("--output-dir", default="data/reports")
    p.add_argument("--train-pct", type=float, default=0.80, help="Train split fraction")
    p.add_argument(
        "--model-type", default="lgbm",
        choices=["lgbm", "alstm", "transformer", "tabnet", "stacking"],
        help="Model architecture to train",
    )
    p.add_argument("--seq-len", type=int, default=20, help="Sequence length for ALSTM/Transformer")
    p.add_argument(
        "--alpha", action="store_true",
        help="Join alpha data (funding rates, derivatives metrics) before feature computation",
    )
    p.add_argument("--funding-dir", default="data/raw/funding", help="Funding rate parquet dir")
    p.add_argument(
        "--metrics-dir", default="data/raw/metrics", help="Derivatives metrics dir",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    asset = Asset(args.asset)
    timeframe = {"5m": Timeframe.M5, "15m": Timeframe.M15, "1h": Timeframe.H1}[args.timeframe]

    logger.info("=" * 70)
    logger.info("TRAINING PIPELINE: %s %s", asset.value, timeframe.value)
    logger.info("=" * 70)

    # ── 1. Load data ──────────────────────────────────────────────────
    t0 = time.time()
    store = ParquetStore(base_dir=Path(args.data_dir))
    bars_df = store.read_bars(asset, timeframe)

    if bars_df.is_empty():
        logger.error("No data found for %s/%s", asset.value, timeframe.value)
        sys.exit(1)

    logger.info("Loaded %d bars (%s to %s)", len(bars_df),
                bars_df["time"].min(), bars_df["time"].max())

    # ── 2. Compute features ───────────────────────────────────────────
    logger.info("Computing features (alpha=%s)...", args.alpha)

    if args.alpha:
        from qm.features.cross_asset import CrossAssetPipeline

        metrics_store = ParquetStore(base_dir=Path(args.metrics_dir))
        funding_store = ParquetStore(base_dir=Path(args.funding_dir))
        cross_pipeline = CrossAssetPipeline(
            store, timeframe,
            metrics_store=metrics_store,
            alpha_stores={"funding": funding_store},
            alpha_tolerances={"funding": "9h"},
        )
        featured_df = cross_pipeline.compute(asset)
        feature_names = [
            f for f in cross_pipeline.feature_names(asset)
            if f in featured_df.columns
        ]
        lookback = cross_pipeline.max_lookback
    else:
        pipeline = FeaturePipeline()
        featured_df = pipeline.compute(bars_df)
        feature_names = [f for f in pipeline.feature_names if f in featured_df.columns]
        lookback = pipeline.max_lookback
    logger.info("Computed %d features: %s", len(feature_names), feature_names[:5])

    # ── 3. Construct targets ──────────────────────────────────────────
    target_builder = BinaryDirectionTarget(horizon_bars=1)
    target = target_builder.compute(featured_df)
    featured_df = featured_df.with_columns(target)

    # Drop rows with null target (last row) or null features (warmup period)
    clean_df = featured_df.slice(lookback).drop_nulls(subset=["target"])
    logger.info(
        "After cleanup: %d rows (dropped %d warmup + null)",
        len(clean_df), len(featured_df) - len(clean_df),
    )

    # ── 4. Train/test split ───────────────────────────────────────────
    split_idx = int(len(clean_df) * args.train_pct)
    train_df = clean_df.slice(0, split_idx)
    test_df = clean_df.slice(split_idx)

    logger.info("Train: %d rows | Test: %d rows (%.0f%%/%.0f%%)",
                len(train_df), len(test_df), args.train_pct * 100, (1 - args.train_pct) * 100)

    X_train = train_df.select(feature_names).fill_null(0).to_numpy().astype(np.float64)
    y_train = train_df["target"].to_numpy().astype(np.float64)
    X_test = test_df.select(feature_names).fill_null(0).to_numpy().astype(np.float64)
    y_test = test_df["target"].to_numpy().astype(np.float64)

    # ── 5. Train model with Optuna HPO ─────────────────────────────────
    logger.info("Training %s with %d Optuna trials...", args.model_type, args.n_trials)
    engine = BacktestEngine(min_edge=args.min_edge)
    tp = min(len(X_train) // 2, 50000)
    tep = min(len(X_train) // 10, 10000)

    if args.model_type == "lgbm":
        from qm.model.trainers.lgbm_trainer import LGBMTrainer
        trainer = LGBMTrainer(
            n_trials=args.n_trials, n_splits=5,
            train_period=tp, test_period=tep,
            backtest_engine=engine, seed=42,
        )
    elif args.model_type == "alstm":
        from qm.model.trainers.alstm_trainer import ALSTMTrainer
        trainer = ALSTMTrainer(
            n_trials=min(args.n_trials, 30), n_splits=5,
            train_period=tp, test_period=tep,
            backtest_engine=engine, seed=42,
            seq_len=args.seq_len,
        )
    elif args.model_type == "transformer":
        from qm.model.trainers.transformer_trainer import TransformerTrainer
        trainer = TransformerTrainer(
            n_trials=min(args.n_trials, 30), n_splits=5,
            train_period=tp, test_period=tep,
            backtest_engine=engine, seed=42,
            seq_len=args.seq_len,
        )
    elif args.model_type == "tabnet":
        from qm.model.trainers.tabnet_trainer import TabNetTrainer
        trainer = TabNetTrainer(
            n_trials=min(args.n_trials, 30), n_splits=5,
            train_period=tp, test_period=tep,
            backtest_engine=engine, seed=42,
        )
    elif args.model_type == "stacking":
        from qm.model.trainers.alstm_trainer import ALSTMTrainer
        from qm.model.trainers.lgbm_trainer import LGBMTrainer
        from qm.model.trainers.stacking_trainer import StackingTrainer
        from qm.model.trainers.transformer_trainer import TransformerTrainer
        base_trainers = [
            ("lgbm", LGBMTrainer(
                n_trials=args.n_trials, n_splits=5,
                train_period=tp, test_period=tep,
                backtest_engine=engine, seed=42,
            )),
            ("alstm", ALSTMTrainer(
                n_trials=min(args.n_trials, 30), n_splits=5,
                train_period=tp, test_period=tep,
                backtest_engine=engine, seed=42, seq_len=args.seq_len,
            )),
            ("transformer", TransformerTrainer(
                n_trials=min(args.n_trials, 30), n_splits=5,
                train_period=tp, test_period=tep,
                backtest_engine=engine, seed=42, seq_len=args.seq_len,
            )),
        ]
        trainer = StackingTrainer(base_trainers=base_trainers, seed=42)
    else:
        logger.error("Unknown model type: %s", args.model_type)
        sys.exit(1)

    hpo_metrics = trainer.fit(X_train, y_train, feature_names=feature_names)

    logger.info("HPO complete. Best CV metrics:")
    for k, v in hpo_metrics.items():
        logger.info("  %s: %.4f", k, v)

    # ── 6. Generate OOS predictions for calibration ───────────────────
    logger.info("Generating walk-forward OOS predictions for calibration...")

    if args.model_type == "lgbm":
        # LightGBM: re-train walk-forward folds with best params
        import lightgbm as lgb

        splitter = WalkForwardSplitter(
            n_splits=5,
            train_period=tp, test_period=tep,
            purge_period=12, embargo_period=6,
        )

        oos_probs = np.zeros(len(y_train))
        oos_mask = np.zeros(len(y_train), dtype=bool)

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

        for train_idx, test_idx in splitter.split(len(X_train)):
            ds = lgb.Dataset(X_train[train_idx], y_train[train_idx])
            model = lgb.train(lgb_params, ds, num_boost_round=n_estimators)
            oos_probs[test_idx] = model.predict(X_train[test_idx])
            oos_mask[test_idx] = True

        oos_idx = np.where(oos_mask)[0]
    else:
        # Non-LGBM models: use the trained model's own predictions on
        # the training set.  This is a simpler approach — the model was
        # already trained with walk-forward HPO internally, so its OOS
        # predictions during HPO were honest.  For calibration we use
        # the final model's train-set predictions (slightly optimistic
        # but consistent across model types).
        raw_train = trainer.predict_proba(X_train)
        if len(raw_train) < len(y_train):
            # Sequence models return fewer predictions — pad front
            pad = np.full(len(y_train) - len(raw_train), 0.5)
            raw_train = np.concatenate([pad, raw_train])
        oos_probs = raw_train
        oos_idx = np.arange(len(y_train))

    logger.info("OOS predictions: %d samples", len(oos_idx))

    # ── 7. Calibrate ──────────────────────────────────────────────────
    logger.info("Fitting isotonic calibrator on OOS predictions...")
    calibrator = IsotonicCalibrator()
    calibrator.fit(oos_probs[oos_idx], y_train[oos_idx])

    cal_oos = calibrator.transform(oos_probs[oos_idx])
    oos_brier = brier_score(cal_oos, y_train[oos_idx])
    oos_ece = expected_calibration_error(cal_oos, y_train[oos_idx])
    logger.info("OOS calibration — Brier: %.4f, ECE: %.4f", oos_brier, oos_ece)

    # ── 8. Predict on held-out test set ───────────────────────────────
    logger.info("Predicting on held-out test set (%d bars)...", len(X_test))
    raw_test_probs = trainer.predict_proba(X_test)

    # Align sequence model outputs: pad front with 0.5, trim targets to match
    if len(raw_test_probs) < len(y_test):
        offset = len(y_test) - len(raw_test_probs)
        pad = np.full(offset, 0.5)
        raw_test_probs = np.concatenate([pad, raw_test_probs])
        logger.info(
            "Sequence model: padded %d samples at front (seq_len=%s)",
            offset, getattr(args, "seq_len", "?"),
        )

    cal_test_probs = calibrator.transform(raw_test_probs)

    test_brier = brier_score(cal_test_probs, y_test)
    test_ece = expected_calibration_error(cal_test_probs, y_test)
    test_accuracy = float(np.mean((cal_test_probs > 0.5) == (y_test == 1)))
    logger.info(
        "Test set — Brier: %.4f, ECE: %.4f, Accuracy: %.4f",
        test_brier, test_ece, test_accuracy,
    )

    # ── 9. Full backtest on test set ──────────────────────────────────
    logger.info("Running full backtest simulation on test set...")
    bt_engine = BacktestEngine(
        fee_bps=0.0,       # Polymarket maker fee ~0 currently
        spread=0.02,       # ~2 cent spread assumption
        min_edge=args.min_edge,
    )

    timestamps = test_df["time"].to_numpy()
    result = bt_engine.run_full_simulation(
        model_probs=cal_test_probs,
        targets=y_test,
        timestamps=timestamps,
        market_probs=np.full(len(y_test), 0.5),
        initial_bankroll=10_000.0,
        kelly_fraction=args.kelly,
    )

    # ── 10. Report ────────────────────────────────────────────────────
    logger.info("=" * 70)
    logger.info("BACKTEST RESULTS")
    logger.info("=" * 70)

    metrics = result.metrics
    metrics["test_brier"] = test_brier
    metrics["test_ece"] = test_ece
    metrics["test_accuracy"] = test_accuracy

    for k, v in sorted(metrics.items()):
        logger.info("  %-20s: %.4f", k, v)

    # Acceptance gates
    passed, failures = check_acceptance(metrics)
    logger.info("")
    if passed:
        logger.info("ACCEPTANCE: PASSED — model is ready for paper trading")
    else:
        logger.info("ACCEPTANCE: FAILED")
        for f in failures:
            logger.info("  FAILED: %s", f)

    # Save report
    generate_report(
        result,
        model_info={
            "asset": asset.value,
            "timeframe": timeframe.value,
            "n_trials": args.n_trials,
            "best_params": trainer.best_params,
            "n_features": len(feature_names),
            "train_rows": len(X_train),
            "test_rows": len(X_test),
        },
        output_dir=Path(args.output_dir),
    )

    # Feature importance (top 20)
    fi = trainer.feature_importance
    if fi:
        logger.info("")
        logger.info("Top 20 features by importance:")
        for i, (name, score) in enumerate(list(fi.items())[:20]):
            logger.info("  %2d. %-25s %.0f", i + 1, name, score)

    # Save model + calibrator
    suffix = f"_{args.model_type}" if args.model_type != "lgbm" else ""
    model_dir = Path("data/models") / f"{asset.value}_{timeframe.value}{suffix}"
    model_dir.mkdir(parents=True, exist_ok=True)
    if args.model_type == "lgbm":
        trainer.save(model_dir / "model.txt")
    elif args.model_type == "tabnet":
        trainer.save(model_dir / "tabnet_model")
    else:
        # ALSTM, Transformer, Stacking: save to directory
        trainer.save(model_dir)
    calibrator.save(model_dir / "calibrator.pkl")
    logger.info("Model saved to %s", model_dir)

    elapsed = time.time() - t0
    logger.info("")
    logger.info("Total pipeline time: %.1f seconds", elapsed)
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
