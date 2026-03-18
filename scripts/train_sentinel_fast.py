#!/usr/bin/env python
"""Fast single-asset Sentinel trainer for autoresearch iterations.

Reads experiment config from autoresearch/knobs.json (never hardcoded).
Outputs structured JSON results to stdout for agent parsing.
Exit code 0 = success, 1 = crash.

Usage:
    uv run scripts/train_sentinel_fast.py --asset BTC --timeframe 5m
    uv run scripts/train_sentinel_fast.py --asset ETH --timeframe 15m --trials 60
    uv run scripts/train_sentinel_fast.py --asset BTC --timeframe 5m --mode verify
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import time
import traceback
from pathlib import Path

import lightgbm as lgb
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from qm.backtest.engine import BacktestEngine
from qm.backtest.metrics.calibration import brier_score, expected_calibration_error
from qm.backtest.validation.walk_forward import WalkForwardSplitter
from qm.core.types import Asset, Timeframe
from qm.data.storage.parquet import ParquetStore
from qm.features.cross_asset import CrossAssetPipeline
from qm.features.pipeline import FeaturePipeline
from qm.features.selection import select_features
from qm.model.calibration.calibrator import IsotonicCalibrator
from qm.model.targets.binary import BinaryDirectionTarget

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stderr,  # logs to stderr, structured output to stdout
)
logger = logging.getLogger("train_fast")

CONFIG_PATH = Path("autoresearch/knobs.json")


def load_knobs() -> dict:
    """Load research knobs from config file."""
    with open(CONFIG_PATH) as f:
        return json.load(f)


def config_hash() -> str:
    """MD5 hash of current knobs.json for result correlation."""
    return hashlib.md5(CONFIG_PATH.read_bytes()).hexdigest()[:8]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fast Sentinel trainer")
    p.add_argument("--asset", required=True, choices=["BTC", "ETH", "SOL", "XRP"])
    p.add_argument("--timeframe", default="5m", choices=["5m", "15m", "1h"])
    p.add_argument("--trials", type=int, default=40, help="Optuna trials (default 40)")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--timeout", type=int, default=420, help="Wall-clock budget in seconds")
    p.add_argument("--mode", default="fast", choices=["fast", "verify"])
    return p.parse_args()


def run(args: argparse.Namespace) -> dict:
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)

    t0 = time.time()
    cfg_hash = config_hash()

    # ── Load knobs from config ────────────────────────────────────
    knobs = load_knobs()
    EXCLUDE_FEATURES = set(knobs["exclude_features"])
    FEATURE_SELECTION = knobs["feature_selection"]
    HPO_SEARCH_SPACE = {k: tuple(v) for k, v in knobs["hpo_search_space"].items()}
    WALK_FORWARD = knobs["walk_forward"]
    BACKTEST = knobs["backtest"]

    asset = Asset[args.asset]
    tf_map = {"5m": Timeframe.M5, "15m": Timeframe.M15, "1h": Timeframe.H1}
    tf = tf_map[args.timeframe]

    # ── Mode-dependent trial/timeout ──────────────────────────────
    if args.mode == "verify":
        n_trials = max(args.trials, 100)
        hpo_timeout = max(args.timeout - 90, 120)
    else:
        n_trials = args.trials
        hpo_timeout = max(args.timeout - 60, 60)

    # ── Load data + cross-asset features ──────────────────────────
    store = ParquetStore(base_dir=Path("data/raw/ohlcv"))
    pipeline = FeaturePipeline()
    cross_pipeline = CrossAssetPipeline(store, tf, pipeline=pipeline)

    featured = cross_pipeline.compute(asset)
    if featured.is_empty():
        return {"status": "error", "reason": "no data"}

    # Defensive: only use feature names that exist as columns
    all_names = cross_pipeline.feature_names(asset)
    feature_names = [f for f in all_names if f not in EXCLUDE_FEATURES and f in featured.columns]

    target = BinaryDirectionTarget(horizon_bars=1).compute(featured)
    featured = featured.with_columns(target)

    clean = featured.slice(cross_pipeline.max_lookback).drop_nulls(subset=["target"])

    # 80/20 temporal split
    split = int(len(clean) * 0.80)
    train_df = clean.slice(0, split)
    test_df = clean.slice(split)

    # ── Feature selection ────────────────────────────────────────
    fs = FEATURE_SELECTION
    selected = select_features(
        train_df.select(feature_names).fill_null(0),
        train_df["target"],
        missing_threshold=fs["missing_threshold"],
        min_target_corr=fs["min_target_corr"],
        max_pairwise_corr=fs["max_pairwise_corr"],
    )
    if len(selected) < fs.get("min_features_fallback", 5):
        selected = feature_names
    logger.info("Selected %d/%d features", len(selected), len(feature_names))

    X_train = train_df.select(selected).fill_null(0).to_numpy().astype(np.float64)
    y_train = train_df["target"].to_numpy().astype(np.float64)
    X_test = test_df.select(selected).fill_null(0).to_numpy().astype(np.float64)
    y_test = test_df["target"].to_numpy().astype(np.float64)

    base_rate = float(y_train.mean())
    logger.info("Data: %d train, %d test, %d feats, base=%.4f", len(X_train), len(X_test), len(selected), base_rate)

    # ── Walk-forward splitter ────────────────────────────────────
    wf = WALK_FORWARD
    splitter = WalkForwardSplitter(
        n_splits=wf["n_splits"],
        train_period=min(len(X_train) // 2, 50000),
        test_period=min(len(X_train) // 10, 10000),
        purge_period=wf["purge_period"],
        embargo_period=wf["embargo_period"],
    )

    # ── Optuna HPO ───────────────────────────────────────────────
    ss = HPO_SEARCH_SPACE

    def objective(trial: optuna.Trial) -> float:
        params = {
            "objective": "binary",
            "metric": "binary_logloss",
            "verbosity": -1,
            "seed": args.seed,
            "n_estimators": trial.suggest_int("n_estimators", *ss["n_estimators"]),
            "learning_rate": trial.suggest_float("lr", *ss["learning_rate"], log=True),
            "max_depth": trial.suggest_int("max_depth", *ss["max_depth"]),
            "num_leaves": trial.suggest_int("num_leaves", *ss["num_leaves"]),
            "min_child_samples": trial.suggest_int("min_child", *ss["min_child_samples"]),
            "subsample": trial.suggest_float("subsample", *ss["subsample"]),
            "colsample_bytree": trial.suggest_float("colsample", *ss["colsample_bytree"]),
            "reg_alpha": trial.suggest_float("reg_alpha", *ss["reg_alpha"], log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", *ss["reg_lambda"], log=True),
            "min_split_gain": trial.suggest_float("min_gain", *ss["min_split_gain"]),
        }

        n_est = params.pop("n_estimators")
        for alias, real in [("lr", "learning_rate"), ("min_child", "min_child_samples"),
                            ("colsample", "colsample_bytree"), ("min_gain", "min_split_gain")]:
            if alias in params:
                params[real] = params.pop(alias)

        briers = []
        for train_idx, test_idx in splitter.split(len(X_train)):
            ds = lgb.Dataset(X_train[train_idx], y_train[train_idx])
            model = lgb.train(params, ds, num_boost_round=n_est)
            preds = model.predict(X_train[test_idx])
            briers.append(float(np.mean((preds - y_train[test_idx]) ** 2)))

        return float(np.mean(briers))

    study = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=args.seed))
    study.optimize(objective, n_trials=n_trials, n_jobs=1, timeout=hpo_timeout)

    logger.info("Best HPO Brier: %.6f (%d/%d trials, %s mode)", study.best_value, len(study.trials), n_trials, args.mode)

    # ── Retrain best ─────────────────────────────────────────────
    bp = study.best_params.copy()
    n_est = bp.pop("n_estimators", 500)
    for alias, real in [("lr", "learning_rate"), ("min_child", "min_child_samples"),
                        ("colsample", "colsample_bytree"), ("min_gain", "min_split_gain")]:
        if alias in bp:
            bp[real] = bp.pop(alias)

    final_params = {"objective": "binary", "metric": "binary_logloss", "verbosity": -1, "seed": args.seed, **bp}
    ds_final = lgb.Dataset(X_train, y_train, feature_name=selected)
    model_final = lgb.train(final_params, ds_final, num_boost_round=n_est)

    # ── Calibrate ────────────────────────────────────────────────
    oos_probs = np.zeros(len(y_train))
    oos_mask = np.zeros(len(y_train), dtype=bool)
    for train_idx, test_idx in splitter.split(len(X_train)):
        ds = lgb.Dataset(X_train[train_idx], y_train[train_idx])
        m = lgb.train(final_params, ds, num_boost_round=n_est)
        oos_probs[test_idx] = m.predict(X_train[test_idx])
        oos_mask[test_idx] = True

    cal = IsotonicCalibrator()
    cal.fit(oos_probs[oos_mask], y_train[oos_mask])

    # ── Evaluate ─────────────────────────────────────────────────
    raw_test = model_final.predict(X_test)
    cal_test = cal.transform(raw_test)

    acc = float(np.mean((cal_test > 0.5) == (y_test == 1)))
    brier = brier_score(cal_test, y_test)
    ece = expected_calibration_error(cal_test, y_test)

    bt = BACKTEST
    engine = BacktestEngine(fee_bps=bt["fee_bps"], spread=bt["spread"], min_edge=bt["min_edge"], timeframe=tf)
    result = engine.run_full_simulation(
        model_probs=cal_test,
        targets=y_test,
        timestamps=np.arange(len(y_test)),
        market_probs=np.full(len(y_test), base_rate),
        initial_bankroll=bt["initial_bankroll"],
        kelly_fraction=bt["kelly_fraction"],
    )
    metrics = result.metrics

    # ── Feature importance ───────────────────────────────────────
    fi = dict(zip(model_final.feature_name(), model_final.feature_importance(importance_type="gain")))
    top_features = sorted(fi.items(), key=lambda x: -x[1])[:10]

    elapsed = time.time() - t0

    return {
        "status": "ok",
        "mode": args.mode,
        "config_hash": cfg_hash,
        "asset": args.asset,
        "timeframe": args.timeframe,
        "elapsed_s": round(elapsed, 1),
        "n_train": len(X_train),
        "n_test": len(X_test),
        "n_features": len(selected),
        "base_rate": round(base_rate, 4),
        "hpo_brier": round(study.best_value, 6),
        "hpo_trials": len(study.trials),
        "oos_accuracy": round(acc, 4),
        "oos_brier": round(brier, 6),
        "oos_ece": round(ece, 4),
        "backtest_pnl": round(metrics["total_pnl"], 2),
        "backtest_trades": metrics["n_trades"],
        "backtest_win_rate": round(metrics["win_rate"], 4),
        "backtest_sharpe": round(metrics["sharpe"], 2),
        "top_features": [f[0] for f in top_features],
        "best_params": {k: round(v, 6) if isinstance(v, float) else v for k, v in study.best_params.items()},
    }


def main() -> None:
    args = parse_args()
    try:
        results = run(args)
    except Exception:
        traceback.print_exc(file=sys.stderr)
        results = {"status": "crash", "reason": traceback.format_exc()[-500:]}

    # Structured output to stdout — this is what the agent parses
    print("===RESULTS_JSON===")
    print(json.dumps(results, indent=2))
    print("===END_RESULTS===")

    sys.exit(0 if results["status"] == "ok" else 1)


if __name__ == "__main__":
    main()
