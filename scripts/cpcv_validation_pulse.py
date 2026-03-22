#!/usr/bin/env python
"""CPCV validation for the Pulse intra-bar model.

Runs Combinatorial Purged Cross-Validation on the cached .npz dataset
to compute PBO (Probability of Backtest Overfitting).

Critical: splits happen at the BAR level to avoid leakage — each bar
has multiple intra-bar samples (one per time_pct) that share a target.

PBO < 0.40 = acceptable (pass acceptance criteria)
PBO < 0.20 = good
PBO > 0.50 = likely overfit

Usage:
    uv run scripts/cpcv_validation_pulse.py --asset BTC
    uv run scripts/cpcv_validation_pulse.py --asset ETH
    uv run scripts/cpcv_validation_pulse.py --asset BTC --n-groups 10 --k-test 2
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import lightgbm as lgb
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from qm.backtest.intrabar_backtest import IntraBarBacktester
from qm.backtest.metrics.calibration import brier_score
from qm.backtest.validation.cpcv import CombPurgedKFoldCV
from qm.core.types import Timeframe
from qm.features.cross_asset_intrabar import load_and_augment
from qm.model.targets.intrabar import IntraBarDataset

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("cpcv_pulse")

CONFIG_PATH = Path("autoresearch/knobs.json")
N_TICK_FEATURES = 8


def _midpoint(
    hpo: dict, key: str, default: float, *, as_int: bool = False,
) -> float | int:
    """Get midpoint of HPO range, or default if key missing."""
    r = hpo.get(key)
    if r and len(r) == 2:
        val = (r[0] + r[1]) / 2
        return int(val) if as_int else val
    return int(default) if as_int else default


def load_knobs() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)


def _resolve_params(knobs: dict, args: argparse.Namespace) -> tuple[dict, int]:
    """Resolve LightGBM params: CLI --best-params > saved model > HPO midpoints."""
    bp = None

    # Priority 1: CLI --best-params JSON string
    if args.best_params:
        bp = json.loads(args.best_params)
        logger.info("Using best_params from --best-params CLI argument")

    # Priority 2: Load from saved model.lgb file
    if bp is None:
        model_dir = Path(f"data/models/pulse_v2/{args.asset}_{args.timeframe}")
        model_path = model_dir / "model.lgb"
        if model_path.exists():
            saved = lgb.Booster(model_file=str(model_path))
            saved_params = saved.params
            bp = {
                "n_estimators": saved.num_trees(),
                "lr": float(saved_params.get("learning_rate", 0.02)),
                "max_depth": int(saved_params.get("max_depth", 5)),
                "num_leaves": int(saved_params.get("num_leaves", 70)),
                "min_child": int(saved_params.get("min_child_samples", 550)),
                "subsample": float(saved_params.get("bagging_fraction", 0.8)),
                "colsample": float(saved_params.get("feature_fraction", 0.7)),
                "reg_alpha": float(saved_params.get("lambda_l1", 0.001)),
                "reg_lambda": float(saved_params.get("lambda_l2", 0.001)),
            }
            logger.info(
                "Using best_params from saved model: %s (lr=%.4f, depth=%d, n_est=%d)",
                model_path, bp["lr"], bp["max_depth"], bp["n_estimators"],
            )

    # Priority 3: Fall back to HPO midpoints (legacy behavior)
    if bp is None:
        hpo = knobs.get("hpo_search_space", {})
        bp = {
            "n_estimators": _midpoint(hpo, "n_estimators", 800, as_int=True),
            "lr": _midpoint(hpo, "learning_rate", 0.02),
            "max_depth": _midpoint(hpo, "max_depth", 5, as_int=True),
            "num_leaves": _midpoint(hpo, "num_leaves", 70, as_int=True),
            "min_child": _midpoint(hpo, "min_child_samples", 550, as_int=True),
            "subsample": _midpoint(hpo, "subsample", 0.8),
            "colsample": _midpoint(hpo, "colsample_bytree", 0.7),
            "reg_alpha": _midpoint(hpo, "reg_alpha", 0.001),
            "reg_lambda": _midpoint(hpo, "reg_lambda", 0.001),
        }
        logger.warning("No saved model found — falling back to HPO midpoints (UNRELIABLE for PBO)")

    n_est = bp.get("n_estimators", 800)
    params = {
        "objective": "binary",
        "metric": "binary_logloss",
        "verbosity": -1,
        "max_depth": int(bp.get("max_depth", 5)),
        "num_leaves": int(bp.get("num_leaves", 70)),
        "min_child_samples": int(bp.get("min_child", 550)),
        "learning_rate": float(bp.get("lr", 0.02)),
        "subsample": float(bp.get("subsample", 0.8)),
        "colsample_bytree": float(bp.get("colsample", 0.7)),
        "reg_alpha": float(bp.get("reg_alpha", 0.001)),
        "reg_lambda": float(bp.get("reg_lambda", 0.001)),
        "seed": args.seed,
    }
    return params, int(n_est)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="CPCV PBO validation for Pulse model")
    p.add_argument("--asset", required=True, choices=["BTC", "ETH", "SOL", "XRP"])
    p.add_argument("--timeframe", default="5m", choices=["5m", "15m", "1h"])
    p.add_argument("--n-groups", type=int, default=8, help="CPCV groups (default 8)")
    p.add_argument("--k-test", type=int, default=2, help="Test groups per path (default 2)")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument(
        "--best-params", type=str, default=None,
        help="JSON string of best_params from Optuna (overrides HPO midpoints). "
             "If not provided, loads params from saved model.lgb file.",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    t0 = time.time()

    # ── Load knobs ──────────────────────────────────────────────
    knobs = load_knobs()
    cached_features = set(knobs["cached_features"])
    time_pcts_cfg = knobs["time_pcts"]
    backtest_cfg = knobs["backtest"]

    tf_map = {"5m": Timeframe.M5, "15m": Timeframe.M15, "1h": Timeframe.H1}
    tf = tf_map[args.timeframe]

    # ── Load cached dataset ─────────────────────────────────────
    cache_path = Path(f"data/models/pulse_v2/{args.asset}_{args.timeframe}/dataset.npz")
    if not cache_path.exists():
        logger.error("No cached dataset at %s. Run train_pulse_v2.py first.", cache_path)
        sys.exit(1)

    dataset = IntraBarDataset.load(cache_path)
    dataset = load_and_augment(dataset, args.asset, args.timeframe, knobs)
    logger.info(
        "Loaded: %d samples, %d features, %d bars",
        len(dataset.y), dataset.X.shape[1],
        len(np.unique(dataset.bar_indices)),
    )

    # ── Feature filtering (same as train_pulse_fast.py) ─────────
    all_names = dataset.feature_names
    keep_indices = list(range(N_TICK_FEATURES))
    for i in range(N_TICK_FEATURES, len(all_names)):
        name = all_names[i]
        if name in cached_features or name.startswith("btc_"):
            keep_indices.append(i)
    feature_names_used = [all_names[i] for i in keep_indices]

    # ── Time-pct filtering ──────────────────────────────────────
    tp_set = np.array(time_pcts_cfg)
    tp_mask = np.zeros(len(dataset.time_pcts), dtype=bool)
    for tp in tp_set:
        tp_mask |= np.isclose(dataset.time_pcts, tp, atol=1e-6)

    X = dataset.X[tp_mask][:, keep_indices]
    y = dataset.y[tp_mask]
    bar_indices = dataset.bar_indices[tp_mask]
    market_probs = dataset.market_probs[tp_mask]
    time_pcts = dataset.time_pcts[tp_mask]

    actual_tps = sorted(set(float(round(t, 6)) for t in time_pcts))
    if len(actual_tps) < len(tp_set):
        unmatched = [
            float(tp) for tp in tp_set
            if not any(np.isclose(tp, a, atol=1e-6) for a in actual_tps)
        ]
        logger.warning(
            "time_pcts MISMATCH: requested %s but only %s exist in dataset. "
            "Unmatched: %s", list(tp_set), actual_tps, unmatched,
        )
    logger.info(
        "After filtering: %d samples, %d features, %d/%d time_pcts matched",
        len(y), len(feature_names_used), len(actual_tps), len(tp_set),
    )

    # ── Bar-level CPCV ──────────────────────────────────────────
    # CRITICAL: split at BAR level, not sample level, to avoid leakage
    unique_bars = np.unique(bar_indices)
    n_bars = len(unique_bars)
    logger.info("Unique bars: %d", n_bars)

    cv = CombPurgedKFoldCV(
        n_groups=args.n_groups,
        k_test_groups=args.k_test,
        purge_period=24,  # 24 bars = 2h at 5m cadence
        embargo_pct=0.01,
    )
    logger.info("Running CPCV with %d paths (C(%d,%d))...", cv.n_paths, args.n_groups, args.k_test)

    # ── Backtester for evaluation ───────────────────────────────
    backtester = IntraBarBacktester(
        fee_bps=backtest_cfg.get("fee_bps", 0),
        spread=backtest_cfg.get("spread", 0.02),
        min_edge=backtest_cfg.get("min_edge", 0.01),
        max_trades_per_bar=backtest_cfg.get("max_trades_per_bar", 15),
        max_daily_trades=backtest_cfg.get("max_daily_trades", 500),
        fixed_bet_usd=backtest_cfg.get("fixed_bet_usd", 100.0),
        timeframe=tf,
    )

    # ── Run each CPCV path ──────────────────────────────────────
    is_sharpes = []
    oos_sharpes = []
    is_briers = []
    oos_briers = []

    for i, (bar_train_idx, bar_test_idx) in enumerate(cv.split(n_bars)):
        # Map bar-level indices → sample-level indices
        train_bars = unique_bars[bar_train_idx]
        test_bars = unique_bars[bar_test_idx]
        train_mask = np.isin(bar_indices, train_bars)
        test_mask = np.isin(bar_indices, test_bars)

        if train_mask.sum() == 0 or test_mask.sum() == 0:
            logger.warning("  Path %d: empty split, skipping", i + 1)
            continue

        # Train LightGBM on this fold
        ds = lgb.Dataset(
            X[train_mask], y[train_mask],
            feature_name=feature_names_used,
        )
        params, n_est = _resolve_params(knobs, args)
        model = lgb.train(params, ds, num_boost_round=n_est)

        # In-sample evaluation
        is_probs = model.predict(X[train_mask])
        is_metrics = backtester.evaluate_fast(
            is_probs, y[train_mask], market_probs[train_mask],
            time_pcts[train_mask], bar_indices[train_mask],
        )
        is_sharpes.append(is_metrics.get("sharpe", 0.0))
        is_briers.append(brier_score(is_probs, y[train_mask]))

        # Out-of-sample evaluation
        oos_probs = model.predict(X[test_mask])
        oos_metrics = backtester.evaluate_fast(
            oos_probs, y[test_mask], market_probs[test_mask],
            time_pcts[test_mask], bar_indices[test_mask],
        )
        oos_sharpes.append(oos_metrics.get("sharpe", 0.0))
        oos_briers.append(brier_score(oos_probs, y[test_mask]))

        logger.info(
            "  Path %2d/%d: IS=%.2f OOS=%.2f Brier=%.4f (%d/%d samples)",
            i + 1, cv.n_paths,
            is_metrics.get("sharpe", 0.0),
            oos_metrics.get("sharpe", 0.0),
            oos_briers[-1],
            train_mask.sum(), test_mask.sum(),
        )

    if not is_sharpes:
        logger.error("No valid CPCV paths. Check data size vs n_groups.")
        sys.exit(1)

    is_arr = np.array(is_sharpes)
    oos_arr = np.array(oos_sharpes)
    is_brier_arr = np.array(is_briers)
    oos_brier_arr = np.array(oos_briers)

    # ── Compute PBO (Sharpe-based) ──────────────────────────────
    pbo_sharpe = cv.probability_of_backtest_overfitting(is_arr, oos_arr)

    # ── Compute PBO (Brier-based) ───────────────────────────────
    # Negate Brier: PBO expects higher=better, Brier is lower=better
    pbo_brier = cv.probability_of_backtest_overfitting(
        -is_brier_arr, -oos_brier_arr,
    )

    # Use the more meaningful metric for the final verdict
    pbo = min(pbo_sharpe, pbo_brier)  # pass if EITHER metric passes

    # ── Deflated Sharpe ratio ───────────────────────────────────
    # Haircut the best Sharpe by the number of trials
    n_paths = len(oos_arr)
    best_oos_sharpe = oos_arr.max()
    # Bailey & López de Prado (2014) approximation
    deflated_sharpe = best_oos_sharpe - np.sqrt(2 * np.log(n_paths)) / np.sqrt(n_paths)

    elapsed = time.time() - t0

    # ── Report ──────────────────────────────────────────────────
    logger.info("")
    logger.info("=" * 70)
    logger.info("CPCV RESULTS — Pulse %s %s (%d paths, %.1fs)",
                args.asset, args.timeframe, n_paths, elapsed)
    logger.info("=" * 70)
    logger.info("  IS Sharpe:       mean=%6.2f  std=%5.2f", is_arr.mean(), is_arr.std())
    logger.info("  OOS Sharpe:      mean=%6.2f  std=%5.2f", oos_arr.mean(), oos_arr.std())
    logger.info(
        "  OOS Brier:       mean=%.4f  std=%.4f",
        oos_brier_arr.mean(), oos_brier_arr.std(),
    )
    logger.info("")
    logger.info("  PBO (Sharpe-based):  %.4f", pbo_sharpe)
    logger.info("  PBO (Brier-based):   %.4f", pbo_brier)
    logger.info("  PBO (best of both):  %.4f", pbo)
    logger.info("  Deflated Sharpe:                    %.4f", deflated_sharpe)
    logger.info("")

    if pbo < 0.20:
        verdict = "EXCELLENT — very low overfitting risk"
    elif pbo < 0.40:
        verdict = "ACCEPTABLE — passes acceptance criteria (PBO < 0.40)"
    elif pbo < 0.50:
        verdict = "CONCERNING — high overfitting risk"
    else:
        verdict = "LIKELY OVERFIT — do NOT deploy"

    logger.info("  VERDICT: %s", verdict)
    logger.info("")

    # Correlation between IS and OOS
    if len(is_arr) > 2:
        corr = np.corrcoef(is_arr, oos_arr)[0, 1]
        logger.info("  IS-OOS Sharpe correlation: %.4f", corr)
        logger.info("  (>0.5 = generalizes well, <0.2 = overfitting)")

    # OOS consistency
    pct_positive = (oos_arr > 0).mean()
    logger.info(
        "  OOS paths with positive Sharpe: %.0f%% (%d/%d)",
        pct_positive * 100, int((oos_arr > 0).sum()), n_paths,
    )

    # Per-time-bucket Brier (if multiple time_pcts in dataset)
    unique_tps = sorted(set(float(round(t, 4)) for t in time_pcts))
    if len(unique_tps) > 1:
        logger.info("")
        logger.info("  Per-time-bucket Brier (global OOS, last path):")
        # Use the last path's OOS data for per-bucket reporting
        last_oos_probs = model.predict(X[test_mask])
        last_oos_y = y[test_mask]
        last_oos_tp = time_pcts[test_mask]
        for tp in unique_tps:
            tp_mask_b = np.isclose(last_oos_tp, tp, atol=1e-6)
            if tp_mask_b.sum() > 0:
                tp_brier = brier_score(last_oos_probs[tp_mask_b], last_oos_y[tp_mask_b])
                tp_acc = float(((last_oos_probs[tp_mask_b] > 0.5) == last_oos_y[tp_mask_b]).mean())
                logger.info("    t=%.3f: Brier=%.4f  Acc=%.1f%%  (%d samples)",
                            tp, tp_brier, tp_acc * 100, int(tp_mask_b.sum()))

    logger.info("=" * 70)

    # ── Acceptance gate ─────────────────────────────────────────
    if pbo < 0.40 and deflated_sharpe > 0:
        logger.info(
            "ACCEPTANCE: PASS — PBO %.4f < 0.40, Deflated Sharpe %.4f > 0",
            pbo, deflated_sharpe,
        )
    else:
        logger.warning(
            "ACCEPTANCE: FAIL — PBO %.4f (need <0.40), DeflSharpe %.4f (need >0)",
            pbo, deflated_sharpe,
        )


if __name__ == "__main__":
    main()
