"""Sentinel autoresearch validation: deep holdout split test.

Detects multiple-testing bias by splitting the existing 20% holdout into
two halves (shallow=80-90%, deep=90-100%) and comparing metrics.

If deep ≈ shallow: autoresearch results are honest.
If deep >> shallow: multiple-testing inflated the numbers.

Read-only diagnostic — does NOT modify any models, knobs, or state files.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from qm.backtest.metrics.calibration import brier_score, expected_calibration_error
from qm.features.cross_asset_intrabar import load_and_augment
from qm.model.calibration.calibrator import TimeAwareCalibrator
from qm.model.specialist import SpecialistModelRouter, load_pulse_model
from qm.model.targets.intrabar import IntraBarDataset

logger = logging.getLogger(__name__)

N_TICK_FEATURES = 8

ASSETS = ["BTC", "ETH", "SOL", "XRP"]
TIMEFRAMES = ["5m", "15m", "1h"]
MODEL_DIR = Path("data/models/pulse_v2")
KNOBS_DIR = Path("autoresearch")


def load_best_knobs(asset: str, tf: str) -> dict:
    """Load best_knobs for a specific asset/timeframe pair."""
    path = KNOBS_DIR / f"best_knobs_{asset}_{tf}.json"
    if not path.exists():
        # Fall back to shared knobs
        path = KNOBS_DIR / "knobs.json"
    with open(path) as f:
        return json.load(f)


def validate_pair(asset: str, tf: str) -> list[dict]:
    """Run deep holdout validation for one asset/timeframe pair."""
    sub_dir = MODEL_DIR / f"{asset}_{tf}"
    cache_path = sub_dir / "dataset.npz"

    if not cache_path.exists():
        logger.warning("No dataset at %s — skipping", cache_path)
        return []

    # Load model
    try:
        model = load_pulse_model(sub_dir)
    except FileNotFoundError:
        logger.warning("No model at %s — skipping", sub_dir)
        return []

    # Load calibrator (skip for specialist models which have internal calibrators)
    calibrator = None
    is_specialist = isinstance(model, SpecialistModelRouter)
    if not is_specialist:
        cal_path = sub_dir / "calibrator.pkl"
        if cal_path.exists():
            calibrator = TimeAwareCalibrator()
            calibrator.load(cal_path)

    # Load dataset
    dataset = IntraBarDataset.load(cache_path)

    # Cross-asset augmentation (same as train_pulse_fast.py)
    knobs = load_best_knobs(asset, tf)
    dataset = load_and_augment(dataset, asset, tf, knobs)

    # Feature filtering — replicate train_pulse_fast.py:428-436
    cached_features = set(knobs["cached_features"])
    time_pcts_cfg = knobs["time_pcts"]

    all_names = dataset.feature_names
    keep_indices = list(range(N_TICK_FEATURES))
    for i in range(N_TICK_FEATURES, len(all_names)):
        name = all_names[i]
        if name in cached_features or name.startswith("btc_"):
            keep_indices.append(i)

    feature_names_used = [all_names[i] for i in keep_indices]

    # Verify feature alignment with model
    if not is_specialist:
        model_features = model.feature_name()
        if model_features != feature_names_used:
            logger.warning(
                "%s_%s: Feature mismatch! Model expects %d features, knobs produce %d. "
                "Using model's feature list.",
                asset, tf, len(model_features), len(feature_names_used),
            )
            # Try to match model's expected features from dataset
            name_to_idx = {n: i for i, n in enumerate(all_names)}
            keep_indices = []
            for fname in model_features:
                if fname in name_to_idx:
                    keep_indices.append(name_to_idx[fname])
                else:
                    logger.error("Feature %s not in dataset!", fname)
                    return []
            feature_names_used = model_features

    # Time-pct filtering — replicate train_pulse_fast.py:441-444
    tp_set = np.array(time_pcts_cfg)
    tp_mask = np.zeros(len(dataset.time_pcts), dtype=bool)
    for tp in tp_set:
        tp_mask |= np.isclose(dataset.time_pcts, tp, atol=1e-6)

    X = dataset.X[tp_mask][:, keep_indices]
    y = dataset.y[tp_mask]
    bar_indices = dataset.bar_indices[tp_mask]
    time_pcts = dataset.time_pcts[tp_mask]

    # 3-way split: 0-80% train, 80-90% shallow, 90-100% deep
    unique_bars = np.unique(bar_indices)
    n_bars = len(unique_bars)
    split_80 = int(n_bars * 0.80)
    split_90 = int(n_bars * 0.90)

    shallow_bars = unique_bars[split_80:split_90]
    deep_bars = unique_bars[split_90:]
    full_test_bars = unique_bars[split_80:]

    results = []
    for label, bar_set in [
        ("full_test", full_test_bars),
        ("shallow", shallow_bars),
        ("deep", deep_bars),
    ]:
        mask = np.isin(bar_indices, bar_set)
        X_slice = X[mask]
        y_slice = y[mask]
        tp_slice = time_pcts[mask]

        if len(y_slice) == 0:
            logger.warning("%s_%s %s: no samples", asset, tf, label)
            continue

        # Inference
        raw_preds = model.predict(X_slice)

        # Calibrate
        if calibrator is not None:
            cal_preds = calibrator.transform(raw_preds, tp_slice)
        elif is_specialist:
            cal_preds = raw_preds  # specialist already calibrates internally
        else:
            cal_preds = raw_preds

        # Metrics
        brier = brier_score(cal_preds, y_slice)
        ece = expected_calibration_error(cal_preds, y_slice)
        acc = float(np.mean((cal_preds >= 0.5) == y_slice))
        base = float(y_slice.mean())

        results.append({
            "asset": asset,
            "tf": tf,
            "slice": label,
            "n_bars": len(bar_set),
            "n_samples": len(y_slice),
            "brier": brier,
            "ece": ece,
            "accuracy": acc,
            "base_rate": base,
        })

    return results


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    all_results: list[dict] = []
    for asset in ASSETS:
        for tf in TIMEFRAMES:
            logger.info("Validating %s_%s ...", asset, tf)
            pair_results = validate_pair(asset, tf)
            all_results.extend(pair_results)

    if not all_results:
        print("No results — check that model files exist.")
        return

    # Print table
    print()
    print("=" * 110)
    print("SENTINEL DEEP HOLDOUT VALIDATION")
    print("=" * 110)
    header = f"{'Asset':<6} {'TF':<5} {'Slice':<12} {'Bars':>6} {'Samples':>8} {'Brier':>8} {'ECE':>8} {'Acc':>8} {'Base':>6}"
    print(header)
    print("-" * 110)

    # Group by pair for gap analysis
    pair_gaps: dict[str, dict] = {}

    for r in all_results:
        print(
            f"{r['asset']:<6} {r['tf']:<5} {r['slice']:<12} "
            f"{r['n_bars']:>6} {r['n_samples']:>8} "
            f"{r['brier']:>8.6f} {r['ece']:>8.4f} "
            f"{r['accuracy']:>8.4f} {r['base_rate']:>6.4f}"
        )

        key = f"{r['asset']}_{r['tf']}"
        if key not in pair_gaps:
            pair_gaps[key] = {}
        pair_gaps[key][r["slice"]] = r

    # Gap analysis
    print()
    print("=" * 80)
    print("SELECTION BIAS ANALYSIS (deep vs shallow Brier gap)")
    print("=" * 80)
    print(f"{'Pair':<12} {'Shallow':>10} {'Deep':>10} {'Gap':>10} {'Gap%':>8} {'Verdict':<20}")
    print("-" * 80)

    verdicts = []
    for key in sorted(pair_gaps.keys()):
        slices = pair_gaps[key]
        if "shallow" not in slices or "deep" not in slices:
            continue

        shallow_brier = slices["shallow"]["brier"]
        deep_brier = slices["deep"]["brier"]
        gap = deep_brier - shallow_brier
        gap_pct = (gap / shallow_brier * 100) if shallow_brier > 0 else 0

        if abs(gap_pct) < 5:
            verdict = "HONEST"
        elif gap_pct < 15:
            verdict = "MODERATE BIAS"
        elif gap_pct < 20:
            verdict = "SIGNIFICANT BIAS"
        else:
            verdict = "UNRELIABLE"

        verdicts.append((key, gap_pct, verdict))
        print(f"{key:<12} {shallow_brier:>10.6f} {deep_brier:>10.6f} {gap:>+10.6f} {gap_pct:>+7.1f}% {verdict:<20}")

    # Summary
    print()
    honest_count = sum(1 for _, _, v in verdicts if v == "HONEST")
    total = len(verdicts)
    print(f"Summary: {honest_count}/{total} pairs show minimal selection bias (<5% gap)")

    # Overall assessment
    avg_gap = np.mean([g for _, g, _ in verdicts]) if verdicts else 0
    print(f"Average gap: {avg_gap:+.1f}%")
    if avg_gap < 5:
        print("CONCLUSION: Autoresearch results appear trustworthy.")
    elif avg_gap < 15:
        print("CONCLUSION: Moderate bias detected — results directionally correct but inflated.")
    else:
        print("CONCLUSION: Significant bias — reported numbers may not generalize to live.")


if __name__ == "__main__":
    main()
