#!/usr/bin/env python
"""Diagnose what's causing the suspicious 74-75% uniform accuracy.

Tests:
1. Target definition check: is our target actually what Polymarket resolves?
2. Single-feature baselines: can ONE feature achieve 75% alone?
3. Shuffled target: does accuracy drop to 50%? (sanity check)
4. Trivial rules: "if current bar went up, target=1" — what accuracy?
5. Information leakage audit: which features know about the target?
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from qm.core.types import Asset, Timeframe
from qm.data.storage.parquet import ParquetStore
from qm.features.pipeline import FeaturePipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("diagnose")


def main() -> None:
    logger.info("=" * 80)
    logger.info("DIAGNOSIS: Why is accuracy uniformly ~75%?")
    logger.info("=" * 80)

    store = ParquetStore(base_dir=Path("data/raw/ohlcv"))
    bars = store.read_bars(Asset.BTC, Timeframe.M5)
    logger.info("Loaded %d BTC 5m bars", len(bars))

    # ═══════════════════════════════════════════════════════════════
    # TEST 1: Examine the target definition
    # ═══════════════════════════════════════════════════════════════
    logger.info("")
    logger.info("TEST 1: Target definition analysis")
    logger.info("-" * 80)

    # Our current target: close[t+1] >= open[t]
    # Polymarket actual: close[t+1] >= open[t+1]  (did the NEXT bar go up?)

    current_target = (bars["close"].shift(-1) >= bars["open"]).drop_nulls()
    correct_target = (bars["close"].shift(-1) >= bars["open"].shift(-1)).drop_nulls()

    logger.info("Current target  (close[t+1] >= open[t]):   base rate = %.4f",
                current_target.mean())
    logger.info("Correct target  (close[t+1] >= open[t+1]): base rate = %.4f",
                correct_target.mean())

    # How often do they agree?
    min_len = min(len(current_target), len(correct_target))
    agreement = (current_target[:min_len] == correct_target[:min_len]).mean()
    logger.info("Agreement between targets: %.4f", agreement)

    logger.info("")
    logger.info("INSIGHT: Current target includes the CURRENT bar's move.")
    logger.info("  close[t+1] >= open[t] is TRUE whenever:")
    logger.info("  - Current bar went up AND next bar doesn't fully reverse it")
    logger.info("  - Current bar went down but next bar more than reverses it")
    logger.info("  This makes the target EASIER to predict because it partly")
    logger.info("  depends on already-known information (current bar's move).")

    # ═══════════════════════════════════════════════════════════════
    # TEST 2: How much does knowing the current bar help?
    # ═══════════════════════════════════════════════════════════════
    logger.info("")
    logger.info("TEST 2: Trivial rule baselines")
    logger.info("-" * 80)

    close = bars["close"].to_numpy()
    open_ = bars["open"].to_numpy()
    high = bars["high"].to_numpy()
    low = bars["low"].to_numpy()

    # Current (wrong) target
    target_wrong = (close[1:] >= open_[:-1]).astype(float)
    # Correct target (Polymarket)
    target_correct = (close[1:] >= open_[1:]).astype(float)

    n = len(target_wrong)

    # Rule 1: "current bar went up" → predict target=1
    current_bar_up = (close[:-1] > open_[:-1]).astype(float)
    rule1_acc_wrong = float(np.mean(current_bar_up == target_wrong))
    rule1_acc_correct = float(np.mean(current_bar_up == target_correct))
    logger.info("Rule: 'current bar went up'")
    logger.info("  vs wrong target:   %.4f", rule1_acc_wrong)
    logger.info("  vs correct target: %.4f", rule1_acc_correct)

    # Rule 2: always predict 1
    always_up_wrong = float(target_wrong.mean())
    always_up_correct = float(target_correct.mean())
    logger.info("Rule: 'always predict Up'")
    logger.info("  vs wrong target:   %.4f", always_up_wrong)
    logger.info("  vs correct target: %.4f", always_up_correct)

    # Rule 3: bar_position > 0.5 → predict 1
    bar_pos = (close[:-1] - low[:-1]) / (high[:-1] - low[:-1] + 1e-10)
    rule3_pred = (bar_pos > 0.5).astype(float)
    rule3_acc_wrong = float(np.mean(rule3_pred == target_wrong))
    rule3_acc_correct = float(np.mean(rule3_pred == target_correct))
    logger.info("Rule: 'bar_position > 0.5'")
    logger.info("  vs wrong target:   %.4f", rule3_acc_wrong)
    logger.info("  vs correct target: %.4f", rule3_acc_correct)

    # ═══════════════════════════════════════════════════════════════
    # TEST 3: Train model with CORRECT target
    # ═══════════════════════════════════════════════════════════════
    logger.info("")
    logger.info("TEST 3: Model with CORRECT target (close[t+1] >= open[t+1])")
    logger.info("-" * 80)

    pipeline = FeaturePipeline()
    featured = pipeline.compute(bars)
    feature_names = [f for f in pipeline.feature_names
                     if f not in {"return_1", "log_return_1", "gap"}]

    # Add CORRECT target
    correct_tgt = (pl.col("close").shift(-1) >= pl.col("open").shift(-1)).cast(pl.Int8).alias("target_correct")
    # Add WRONG target for comparison
    wrong_tgt = (pl.col("close").shift(-1) >= pl.col("open")).cast(pl.Int8).alias("target_wrong")

    featured = featured.with_columns(correct_tgt, wrong_tgt)

    lookback = pipeline.max_lookback
    clean = featured.slice(lookback).drop_nulls(subset=["target_correct", "target_wrong"])

    split = int(len(clean) * 0.80)
    X_train = clean.slice(0, split).select(feature_names).fill_null(0).to_numpy().astype(np.float64)
    X_test = clean.slice(split).select(feature_names).fill_null(0).to_numpy().astype(np.float64)

    import lightgbm as lgb
    params = {
        "objective": "binary", "metric": "binary_logloss", "verbosity": -1,
        "learning_rate": 0.01, "max_depth": 4, "num_leaves": 15,
        "min_child_samples": 200, "subsample": 0.7, "colsample_bytree": 0.5,
        "reg_alpha": 1.0, "reg_lambda": 5.0, "seed": 42,
    }

    # Train on WRONG target
    y_train_wrong = clean.slice(0, split)["target_wrong"].to_numpy().astype(np.float64)
    y_test_wrong = clean.slice(split)["target_wrong"].to_numpy().astype(np.float64)
    ds_wrong = lgb.Dataset(X_train, y_train_wrong, feature_name=feature_names)
    model_wrong = lgb.train(params, ds_wrong, num_boost_round=300)
    pred_wrong = model_wrong.predict(X_test)
    acc_wrong = float(np.mean((pred_wrong > 0.5) == (y_test_wrong == 1)))

    # Train on CORRECT target
    y_train_correct = clean.slice(0, split)["target_correct"].to_numpy().astype(np.float64)
    y_test_correct = clean.slice(split)["target_correct"].to_numpy().astype(np.float64)
    ds_correct = lgb.Dataset(X_train, y_train_correct, feature_name=feature_names)
    model_correct = lgb.train(params, ds_correct, num_boost_round=300)
    pred_correct = model_correct.predict(X_test)
    acc_correct = float(np.mean((pred_correct > 0.5) == (y_test_correct == 1)))

    logger.info("Model with WRONG target  (close[t+1] >= open[t]):   %.4f", acc_wrong)
    logger.info("Model with CORRECT target (close[t+1] >= open[t+1]): %.4f", acc_correct)

    # ═══════════════════════════════════════════════════════════════
    # TEST 4: Shuffled target sanity check
    # ═══════════════════════════════════════════════════════════════
    logger.info("")
    logger.info("TEST 4: Shuffled target (should be ~50%%)")
    logger.info("-" * 80)

    rng = np.random.RandomState(42)
    y_shuffled = y_train_correct.copy()
    rng.shuffle(y_shuffled)
    ds_shuffled = lgb.Dataset(X_train, y_shuffled, feature_name=feature_names)
    model_shuffled = lgb.train(params, ds_shuffled, num_boost_round=300)
    pred_shuffled = model_shuffled.predict(X_test)
    acc_shuffled = float(np.mean((pred_shuffled > 0.5) == (y_test_correct == 1)))
    logger.info("Shuffled target accuracy: %.4f (should be ~0.50)", acc_shuffled)

    # ═══════════════════════════════════════════════════════════════
    # TEST 5: Per-feature correlation with both targets
    # ═══════════════════════════════════════════════════════════════
    logger.info("")
    logger.info("TEST 5: Feature correlation with targets (top 10)")
    logger.info("-" * 80)

    all_X = clean.select(feature_names).fill_null(0).to_numpy().astype(np.float64)
    all_y_wrong = clean["target_wrong"].to_numpy().astype(np.float64)
    all_y_correct = clean["target_correct"].to_numpy().astype(np.float64)

    corr_wrong = []
    corr_correct = []
    for i, fname in enumerate(feature_names):
        cw = abs(np.corrcoef(all_X[:, i], all_y_wrong)[0, 1])
        cc = abs(np.corrcoef(all_X[:, i], all_y_correct)[0, 1])
        corr_wrong.append((fname, cw if not np.isnan(cw) else 0))
        corr_correct.append((fname, cc if not np.isnan(cc) else 0))

    corr_wrong.sort(key=lambda x: -x[1])
    corr_correct.sort(key=lambda x: -x[1])

    logger.info("%-25s  %10s  %10s", "Feature", "|corr_wrong|", "|corr_correct|")
    # Show features sorted by wrong-target correlation
    shown = set()
    for fname, cw in corr_wrong[:15]:
        cc = dict(corr_correct).get(fname, 0)
        flag = " ← LEAKY" if cw > 0.1 and cc < 0.02 else ""
        logger.info("%-25s  %10.4f  %12.4f%s", fname, cw, cc, flag)
        shown.add(fname)

    # ═══════════════════════════════════════════════════════════════
    # TEST 6: Feature importance comparison
    # ═══════════════════════════════════════════════════════════════
    logger.info("")
    logger.info("TEST 6: Feature importance (wrong vs correct target)")
    logger.info("-" * 80)

    fi_wrong = dict(zip(model_wrong.feature_name(), model_wrong.feature_importance(importance_type="gain")))
    fi_correct = dict(zip(model_correct.feature_name(), model_correct.feature_importance(importance_type="gain")))

    # Sort by wrong-target importance
    fi_sorted = sorted(fi_wrong.items(), key=lambda x: -x[1])

    logger.info("%-25s  %12s  %12s  %s", "Feature", "Imp(wrong)", "Imp(correct)", "Ratio")
    for fname, imp_w in fi_sorted[:15]:
        imp_c = fi_correct.get(fname, 0)
        ratio = imp_w / (imp_c + 1) if imp_c > 0 else 999
        flag = " ← SUSPICIOUS" if ratio > 5 else ""
        logger.info("%-25s  %12.0f  %12.0f  %5.1fx%s", fname, imp_w, imp_c, ratio, flag)

    # ═══════════════════════════════════════════════════════════════
    # SUMMARY
    # ═══════════════════════════════════════════════════════════════
    logger.info("")
    logger.info("=" * 80)
    logger.info("DIAGNOSIS SUMMARY")
    logger.info("=" * 80)
    logger.info("")
    logger.info("Wrong target accuracy:    %.4f (what we've been measuring)", acc_wrong)
    logger.info("Correct target accuracy:  %.4f (what Polymarket actually resolves)", acc_correct)
    logger.info("Shuffled target accuracy: %.4f (random baseline)", acc_shuffled)
    logger.info("")

    if acc_wrong > acc_correct + 0.05:
        logger.info("DIAGNOSIS: TARGET LEAKAGE CONFIRMED")
        logger.info("  The wrong target (close[t+1] >= open[t]) includes information")
        logger.info("  from the current bar that features can see. The model is partly")
        logger.info("  predicting the present, not the future.")
        logger.info("")
        logger.info("  FIX: Use close[t+1] >= open[t+1] as target (next bar's own move)")
    elif acc_correct > 0.52:
        logger.info("FINDING: Model has genuine predictive signal with correct target")
        logger.info("  Accuracy %.4f is above the 50%% baseline.", acc_correct)
    else:
        logger.info("FINDING: No genuine signal with correct target")
        logger.info("  All apparent accuracy came from target leakage.")


if __name__ == "__main__":
    main()
