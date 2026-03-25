#!/usr/bin/env python
"""Validate alpha features via TabNet attention masks.

Trains 4 configurations and compares:
  A: TabNet  + all features (including alpha)
  B: TabNet  + non-alpha features only
  C: LightGBM + all features (reference)
  D: LightGBM + non-alpha features only (reference)

The key deliverable is the attention mask analysis: do funding/OI/IV
features receive more attention than random in TabNet?  If yes, these
features contain signal that LightGBM structurally cannot exploit.

Requires: pytorch-tabnet (gpu optional dependency).

Usage:
    python scripts/validate_alpha_tabnet.py --asset BTC --timeframe 5m
    python scripts/validate_alpha_tabnet.py --asset ETH --timeframe 15m --n-trials 20
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
from qm.model.calibration.calibrator import IsotonicCalibrator
from qm.model.targets.binary import BinaryDirectionTarget

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("validate_alpha")

# Alpha feature prefixes to test
ALPHA_PREFIXES = ["funding_", "liquidation_", "oi_", "iv_", "leverage_", "pm_"]

# Also include interaction features that involve alpha columns
ALPHA_INTERACTION_PREFIXES = [
    "funding_x_", "oi_div_x_", "leverage_x_", "regime_x_funding",
]


def _is_alpha_feature(name: str) -> bool:
    return any(name.startswith(p) for p in ALPHA_PREFIXES + ALPHA_INTERACTION_PREFIXES)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Validate alpha features via TabNet")
    p.add_argument("--asset", default="BTC", choices=["BTC", "ETH", "SOL", "XRP"])
    p.add_argument("--timeframe", default="5m", choices=["5m", "15m", "1h"])
    p.add_argument("--n-trials", type=int, default=20)
    p.add_argument("--data-dir", default="data/raw/ohlcv")
    p.add_argument("--train-pct", type=float, default=0.80)
    return p.parse_args()


def _evaluate_config(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_test: np.ndarray,
    y_test: np.ndarray,
    feature_names: list[str],
    n_trials: int,
    model_type: str,
    label: str,
) -> dict:
    """Train model, calibrate, evaluate, return metrics + attention info."""
    logger.info("[%s] Training %s with %d features...", label, model_type, len(feature_names))

    if model_type == "tabnet":
        from qm.model.trainers.tabnet_trainer import TabNetTrainer

        trainer = TabNetTrainer(
            n_trials=n_trials, n_splits=3,
            train_period=min(len(X_train) // 2, 30000),
            test_period=min(len(X_train) // 6, 5000),
            backtest_engine=BacktestEngine(min_edge=0.03),
            seed=42,
        )
        trainer.fit(X_train, y_train.astype(np.int64), feature_names=feature_names)
    else:
        from qm.model.trainers.lgbm_trainer import LGBMTrainer

        trainer = LGBMTrainer(
            n_trials=n_trials, n_splits=3,
            train_period=min(len(X_train) // 2, 30000),
            test_period=min(len(X_train) // 6, 5000),
            backtest_engine=BacktestEngine(min_edge=0.03),
            seed=42,
        )
        trainer.fit(X_train, y_train, feature_names=feature_names)

    # Calibrate + evaluate
    raw_probs = trainer.predict_proba(X_test)
    # Simple calibration on test (for comparison purposes)
    raw_train = trainer.predict_proba(X_train)
    cal = IsotonicCalibrator()
    cal.fit(raw_train, y_train.astype(np.float64))
    cal_probs = cal.transform(raw_probs)

    result = {
        "label": label,
        "model_type": model_type,
        "n_features": len(feature_names),
        "brier": brier_score(cal_probs, y_test),
        "ece": expected_calibration_error(cal_probs, y_test),
        "accuracy": float(np.mean((cal_probs > 0.5) == (y_test == 1))),
        "feature_importance": trainer.feature_importance,
    }

    # TabNet attention analysis
    if model_type == "tabnet" and hasattr(trainer, "attention_masks"):
        masks = trainer.attention_masks(X_test[:2000])  # sample for speed
        alpha_idx = [i for i, n in enumerate(feature_names) if _is_alpha_feature(n)]
        non_alpha_idx = [
            i for i, n in enumerate(feature_names) if not _is_alpha_feature(n)
        ]

        if alpha_idx:
            alpha_attention = masks[:, alpha_idx].mean()
            non_alpha_attention = masks[:, non_alpha_idx].mean()
            expected_random = 1.0 / len(feature_names)

            result["alpha_mean_attention"] = float(alpha_attention)
            result["non_alpha_mean_attention"] = float(non_alpha_attention)
            result["expected_random_attention"] = expected_random
            result["alpha_attention_ratio"] = float(
                alpha_attention / expected_random
            )

            # Per-feature attention for alpha features
            alpha_names = [
                n for n in feature_names if _is_alpha_feature(n)
            ]
            alpha_attentions = {
                n: float(masks[:, i].mean())
                for n, i in zip(alpha_names, alpha_idx, strict=False)
            }
            result["alpha_per_feature_attention"] = alpha_attentions

    return result


def main() -> None:
    args = parse_args()
    asset = Asset(args.asset)
    timeframe = {
        "5m": Timeframe.M5, "15m": Timeframe.M15, "1h": Timeframe.H1,
    }[args.timeframe]

    logger.info("=" * 70)
    logger.info("ALPHA FEATURE VALIDATION: %s %s", asset.value, timeframe.value)
    logger.info("=" * 70)

    # 1. Load + compute features
    store = ParquetStore(base_dir=Path(args.data_dir))
    bars_df = store.read_bars(asset, timeframe)
    if bars_df.is_empty():
        logger.error("No data for %s/%s", asset.value, timeframe.value)
        sys.exit(1)

    pipeline = FeaturePipeline()
    featured_df = pipeline.compute(bars_df)
    all_features = pipeline.feature_names

    target_builder = BinaryDirectionTarget(horizon_bars=1)
    target = target_builder.compute(featured_df)
    featured_df = featured_df.with_columns(target)
    lookback = pipeline.max_lookback
    clean_df = featured_df.slice(lookback).drop_nulls(subset=["target"])

    # 2. Identify alpha vs non-alpha
    alpha_features = [f for f in all_features if _is_alpha_feature(f)]
    non_alpha_features = [f for f in all_features if not _is_alpha_feature(f)]
    logger.info(
        "Features: %d total, %d alpha, %d non-alpha",
        len(all_features), len(alpha_features), len(non_alpha_features),
    )
    logger.info("Alpha features: %s", alpha_features)

    # 3. Train/test split
    split_idx = int(len(clean_df) * args.train_pct)
    train_df = clean_df.slice(0, split_idx)
    test_df = clean_df.slice(split_idx)
    y_train = train_df["target"].to_numpy().astype(np.float64)
    y_test = test_df["target"].to_numpy().astype(np.float64)

    # 4. Run 4 configs
    results = []

    # A: TabNet + all
    X_tr = train_df.select(all_features).fill_null(0).to_numpy().astype(np.float64)
    X_te = test_df.select(all_features).fill_null(0).to_numpy().astype(np.float64)
    results.append(_evaluate_config(
        X_tr, y_train, X_te, y_test, all_features,
        args.n_trials, "tabnet", "TabNet+ALL",
    ))

    # B: TabNet - alpha
    X_tr_na = train_df.select(non_alpha_features).fill_null(0).to_numpy().astype(np.float64)
    X_te_na = test_df.select(non_alpha_features).fill_null(0).to_numpy().astype(np.float64)
    results.append(_evaluate_config(
        X_tr_na, y_train, X_te_na, y_test, non_alpha_features,
        args.n_trials, "tabnet", "TabNet-ALPHA",
    ))

    # C: LightGBM + all
    results.append(_evaluate_config(
        X_tr, y_train, X_te, y_test, all_features,
        args.n_trials, "lgbm", "LGBM+ALL",
    ))

    # D: LightGBM - alpha
    results.append(_evaluate_config(
        X_tr_na, y_train, X_te_na, y_test, non_alpha_features,
        args.n_trials, "lgbm", "LGBM-ALPHA",
    ))

    # 5. Report
    logger.info("")
    logger.info("=" * 70)
    logger.info("RESULTS COMPARISON")
    logger.info("=" * 70)
    logger.info(
        "%-20s %8s %8s %8s %8s",
        "Config", "Brier", "ECE", "Acc", "N_Feat",
    )
    logger.info("-" * 56)
    for r in results:
        logger.info(
            "%-20s %8.4f %8.4f %8.4f %8d",
            r["label"], r["brier"], r["ece"], r["accuracy"], r["n_features"],
        )

    # 6. Attention mask analysis
    tabnet_all = results[0]
    if "alpha_mean_attention" in tabnet_all:
        logger.info("")
        logger.info("── Attention Mask Analysis (TabNet+ALL) ──")
        logger.info(
            "  Alpha mean attention:     %.4f",
            tabnet_all["alpha_mean_attention"],
        )
        logger.info(
            "  Non-alpha mean attention: %.4f",
            tabnet_all["non_alpha_mean_attention"],
        )
        logger.info(
            "  Expected random:          %.4f",
            tabnet_all["expected_random_attention"],
        )
        logger.info(
            "  Alpha / Random ratio:     %.2fx",
            tabnet_all["alpha_attention_ratio"],
        )

        logger.info("")
        logger.info("  Per-feature alpha attention:")
        for name, attn in sorted(
            tabnet_all["alpha_per_feature_attention"].items(),
            key=lambda x: -x[1],
        ):
            expected = tabnet_all["expected_random_attention"]
            flag = " << ABOVE RANDOM" if attn > expected * 1.5 else ""
            logger.info("    %-30s %.4f%s", name, attn, flag)

    # 7. Verdict
    logger.info("")
    brier_tabnet_delta = results[1]["brier"] - results[0]["brier"]
    brier_lgbm_delta = results[3]["brier"] - results[2]["brier"]

    alpha_ratio = tabnet_all.get("alpha_attention_ratio", 0)
    if alpha_ratio > 1.5 and brier_tabnet_delta > 0.001:
        logger.info(
            "VERDICT: Alpha features have SIGNAL in TabNet "
            "(attention %.2fx random, Brier improvement %.4f). "
            "UNBLOCK for TabNet/neural models.",
            alpha_ratio, brier_tabnet_delta,
        )
    elif alpha_ratio > 1.0:
        logger.info(
            "VERDICT: Alpha features get SOME attention (%.2fx random) "
            "but Brier impact is marginal. INVESTIGATE further.",
            alpha_ratio,
        )
    else:
        logger.info(
            "VERDICT: Alpha features get <= random attention (%.2fx). "
            "Auditor BLOCK confirmed.",
            alpha_ratio,
        )

    logger.info(
        "  TabNet Brier delta (all vs no-alpha): %+.4f", -brier_tabnet_delta,
    )
    logger.info(
        "  LightGBM Brier delta (all vs no-alpha): %+.4f", -brier_lgbm_delta,
    )


if __name__ == "__main__":
    main()
