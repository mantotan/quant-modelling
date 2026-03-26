#!/usr/bin/env python
"""Analyze multi-model agreement: does accuracy improve when models agree?

Loads LightGBM, ALSTM, and Transformer saved models, predicts on the
test set, and reports accuracy conditioned on agreement.

Usage:
    python scripts/analyze_agreement.py --asset BTC --timeframe 5m
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from qm.backtest.metrics.calibration import brier_score
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
logger = logging.getLogger("agreement")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Multi-model agreement analysis")
    p.add_argument("--asset", default="BTC", choices=["BTC", "ETH", "SOL", "XRP"])
    p.add_argument("--timeframe", default="5m", choices=["5m", "15m", "1h"])
    p.add_argument("--data-dir", default="data/raw/ohlcv")
    p.add_argument("--model-dir", default="data/models")
    p.add_argument("--train-pct", type=float, default=0.80)
    return p.parse_args()


def _load_lgbm(model_dir: Path, cal_dir: Path):
    """Load LightGBM model + calibrator."""
    import lightgbm as lgb
    model = lgb.Booster(model_file=str(model_dir / "model.txt"))
    cal = IsotonicCalibrator()
    cal.load(cal_dir / "calibrator.pkl")
    return model, cal


def _load_neural(model_dir: Path, trainer_cls):
    """Load ALSTM or Transformer model."""
    trainer = trainer_cls(use_gpu=True)
    trainer.load(model_dir)
    cal = IsotonicCalibrator()
    cal_path = model_dir / "calibrator.pkl"
    if cal_path.exists():
        cal.load(cal_path)
    return trainer, cal


def main() -> None:
    args = parse_args()
    asset = Asset(args.asset)
    timeframe = {
        "5m": Timeframe.M5, "15m": Timeframe.M15, "1h": Timeframe.H1,
    }[args.timeframe]
    base = Path(args.model_dir)
    pair = f"{asset.value}_{timeframe.value}"

    logger.info("=" * 70)
    logger.info("MULTI-MODEL AGREEMENT ANALYSIS: %s %s", asset.value, timeframe.value)
    logger.info("=" * 70)

    # Load data + compute features
    store = ParquetStore(base_dir=Path(args.data_dir))
    bars_df = store.read_bars(asset, timeframe)
    pipeline = FeaturePipeline()
    featured_df = pipeline.compute(bars_df)
    feature_names = [f for f in pipeline.feature_names if f in featured_df.columns]

    target_builder = BinaryDirectionTarget(horizon_bars=1)
    target = target_builder.compute(featured_df)
    featured_df = featured_df.with_columns(target)
    lookback = pipeline.max_lookback
    clean_df = featured_df.slice(lookback).drop_nulls(subset=["target"])

    # Use test set only
    split_idx = int(len(clean_df) * args.train_pct)
    test_df = clean_df.slice(split_idx)
    X_test = test_df.select(feature_names).fill_null(0).to_numpy().astype(np.float64)
    y_test = test_df["target"].to_numpy().astype(np.float64)

    logger.info("Test set: %d bars", len(y_test))

    # Load models and predict
    predictions = {}

    # LightGBM
    lgbm_dir = base / pair
    if (lgbm_dir / "model.txt").exists():
        model, cal = _load_lgbm(lgbm_dir, lgbm_dir)
        raw = model.predict(X_test)
        predictions["lgbm"] = cal.transform(raw)
        logger.info("Loaded LightGBM from %s", lgbm_dir)

    # ALSTM
    alstm_dir = base / f"{pair}_alstm"
    if (alstm_dir / "model.pt").exists():
        from qm.model.trainers.alstm_trainer import ALSTMTrainer
        trainer, cal = _load_neural(alstm_dir, ALSTMTrainer)
        raw = trainer.predict_proba(X_test)
        # Pad front for sequence offset
        if len(raw) < len(y_test):
            pad = np.full(len(y_test) - len(raw), 0.5)
            raw = np.concatenate([pad, raw])
        predictions["alstm"] = cal.transform(raw)
        logger.info("Loaded ALSTM from %s", alstm_dir)

    # Transformer
    tf_dir = base / f"{pair}_transformer"
    if (tf_dir / "model.pt").exists():
        from qm.model.trainers.transformer_trainer import TransformerTrainer
        trainer, cal = _load_neural(tf_dir, TransformerTrainer)
        raw = trainer.predict_proba(X_test)
        if len(raw) < len(y_test):
            pad = np.full(len(y_test) - len(raw), 0.5)
            raw = np.concatenate([pad, raw])
        predictions["transformer"] = cal.transform(raw)
        logger.info("Loaded Transformer from %s", tf_dir)

    if len(predictions) < 2:
        logger.error(
            "Need at least 2 models. Found: %s", list(predictions.keys()),
        )
        sys.exit(1)

    # Compute agreement
    model_names = list(predictions.keys())
    directions = {}
    for name, probs in predictions.items():
        directions[name] = (probs > 0.5).astype(int)

    # All models agree
    dir_stack = np.stack([directions[n] for n in model_names], axis=0)
    all_up = dir_stack.sum(axis=0) == len(model_names)
    all_down = dir_stack.sum(axis=0) == 0
    all_agree = all_up | all_down
    disagree = ~all_agree

    agree_rate = all_agree.mean()
    logger.info("")
    logger.info("Models: %s", model_names)
    logger.info("Agreement rate: %.1f%%", agree_rate * 100)
    logger.info("")

    # Accuracy and Brier on agreement vs disagreement subsets
    logger.info(
        "%-20s %8s %8s %8s %8s",
        "Subset", "N", "Brier", "Acc", "Avg Prob",
    )
    logger.info("-" * 56)

    for subset_name, mask in [("All", np.ones(len(y_test), dtype=bool)),
                               ("Agree", all_agree),
                               ("Disagree", disagree)]:
        if mask.sum() == 0:
            continue
        # Use average of all model probabilities
        avg_probs = np.mean([predictions[n] for n in model_names], axis=0)
        sub_probs = avg_probs[mask]
        sub_y = y_test[mask]
        sub_brier = brier_score(sub_probs, sub_y)
        sub_acc = float(np.mean((sub_probs > 0.5) == (sub_y == 1)))
        avg_p = float(sub_probs.mean())
        logger.info(
            "%-20s %8d %8.4f %8.4f %8.4f",
            subset_name, int(mask.sum()), sub_brier, sub_acc, avg_p,
        )

    # Per-direction agreement
    logger.info("")
    logger.info("Direction breakdown:")
    for direction_name, mask in [("Agree UP", all_up),
                                  ("Agree DOWN", all_down)]:
        if mask.sum() == 0:
            continue
        sub_y = y_test[mask]
        actual_up_rate = float(sub_y.mean())
        logger.info(
            "  %-15s N=%d, actual UP rate=%.1f%%",
            direction_name, int(mask.sum()), actual_up_rate * 100,
        )

    # Verdict
    logger.info("")
    if all_agree.sum() > 0 and disagree.sum() > 0:
        avg_probs = np.mean([predictions[n] for n in model_names], axis=0)
        agree_brier = brier_score(avg_probs[all_agree], y_test[all_agree])
        disagree_brier = brier_score(avg_probs[disagree], y_test[disagree])
        improvement = disagree_brier - agree_brier

        if improvement > 0.005:
            logger.info(
                "VERDICT: Agreement subset has Brier %.4f better than "
                "disagreement — USE as trading filter",
                improvement,
            )
        elif improvement > 0.001:
            logger.info(
                "VERDICT: Agreement subset marginally better (%.4f) — "
                "INVESTIGATE further",
                improvement,
            )
        else:
            logger.info(
                "VERDICT: Agreement does NOT improve Brier (delta=%.4f) — "
                "multi-model filter not useful",
                improvement,
            )


if __name__ == "__main__":
    main()
