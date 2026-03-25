#!/usr/bin/env python
"""Experiment harness: test 9 structural improvement ideas for the Pulse model.

Tests each idea against a baseline using fixed hyperparameters (no HPO)
for fast iteration. Uses walk-forward evaluation on the held-out test set.

Usage:
    uv run scripts/experiment_pulse_ideas.py --asset BTC --timeframe 15m
    uv run scripts/experiment_pulse_ideas.py --asset ETH --timeframe 5m
    uv run scripts/experiment_pulse_ideas.py --asset BTC --timeframe 15m --experiments 1,2,3
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
import polars as pl

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from qm.backtest.intrabar_backtest import IntraBarBacktester
from qm.backtest.metrics.calibration import brier_score, expected_calibration_error
from qm.backtest.validation.walk_forward import WalkForwardSplitter
from qm.core.types import Asset, Timeframe
from qm.data.storage.parquet import ParquetStore
from qm.model.calibration.calibrator import TimeAwareCalibrator
from qm.model.targets.intrabar import IntraBarDataset
from qm.model.trainers.device import detect_device

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stderr,
)
logger = logging.getLogger("experiment")

TF_MAP = {"5m": Timeframe.M5, "15m": Timeframe.M15, "1h": Timeframe.H1}
TF_MINUTES = {"5m": 5, "15m": 15, "1h": 60}
N_TICK = 8  # first 8 features are tick features


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--asset", required=True, choices=["BTC", "ETH", "SOL", "XRP"])
    p.add_argument("--timeframe", default="15m", choices=["5m", "15m", "1h"])
    p.add_argument("--experiments", default="all",
                   help="Comma-separated experiment numbers (1-9) or 'all'")
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args()


def extract_params_from_model(model_path: Path) -> dict:
    """Extract best hyperparameters from a saved LightGBM model."""
    model = lgb.Booster(model_file=str(model_path))
    p = model.params
    return {
        "n_estimators": model.num_trees(),
        "learning_rate": float(p.get("learning_rate", 0.02)),
        "max_depth": int(p.get("max_depth", 5)),
        "num_leaves": int(p.get("num_leaves", 70)),
        "min_child_samples": int(p.get("min_child_samples", 550)),
        "subsample": float(p.get("bagging_fraction", 0.8)),
        "colsample_bytree": float(p.get("feature_fraction", 0.7)),
        "reg_alpha": float(p.get("lambda_l1", 0.001)),
        "reg_lambda": float(p.get("lambda_l2", 0.001)),
    }


ASSET_MAP = {"BTC": Asset.BTC, "ETH": Asset.ETH, "SOL": Asset.SOL, "XRP": Asset.XRP}
_store = ParquetStore(Path("data/raw/ohlcv"))


def load_raw_bars(asset: str, timeframe: str) -> pl.DataFrame:
    """Load raw OHLCV bars from Hive-partitioned parquet."""
    return _store.read_bars(ASSET_MAP[asset], TF_MAP[timeframe])


def load_1m_bars(asset: str) -> pl.DataFrame:
    """Load 1-minute bars."""
    return _store.read_bars(ASSET_MAP[asset], Timeframe.M1)


def prepare_base_data(asset: str, timeframe: str):
    """Load cached dataset, raw bars, extract params. Returns everything needed."""
    cache_path = Path(f"data/models/pulse_v2/{asset}_{timeframe}/dataset.npz")
    model_path = Path(f"data/models/pulse_v2/{asset}_{timeframe}/model.lgb")

    dataset = IntraBarDataset.load(cache_path)
    params = extract_params_from_model(model_path)

    # Load raw bars for actual returns
    raw_bars = load_raw_bars(asset, timeframe)
    returns = ((raw_bars["close"] - raw_bars["open"]) / raw_bars["open"]).to_numpy()

    return dataset, params, raw_bars, returns


def filter_time_pcts(dataset, time_pcts=(0.10, 0.20, 0.40, 0.60, 0.80)):
    """Filter dataset to only the configured time_pcts."""
    tp_mask = np.zeros(len(dataset.time_pcts), dtype=bool)
    for tp in time_pcts:
        tp_mask |= np.isclose(dataset.time_pcts, tp, atol=1e-6)
    return tp_mask


def temporal_split(bar_indices, train_frac=0.80):
    """80/20 temporal split at bar level."""
    unique_bars = np.unique(bar_indices)
    n_bars = len(unique_bars)
    split_idx = int(n_bars * train_frac)
    train_bars = unique_bars[:split_idx]
    train_mask = np.isin(bar_indices, train_bars)
    return train_mask, ~train_mask


def train_and_evaluate(
    X_train, y_train, X_test, y_test, mp_test, tp_test, bi_test,
    params, feature_names, tf, seed=42,
    sample_weight_train=None,
    bar_indices_train=None, tp_train=None,
):
    """Train LightGBM with fixed params, calibrate, evaluate. Returns metrics dict."""
    device = detect_device(prefer_gpu=True)
    n_est = params["n_estimators"]
    lgb_params = {
        "objective": "binary",
        "metric": "binary_logloss",
        "verbosity": -1,
        "device": device,
        "seed": seed,
        "learning_rate": params["learning_rate"],
        "max_depth": params["max_depth"],
        "num_leaves": params["num_leaves"],
        "min_child_samples": params["min_child_samples"],
        "subsample": params["subsample"],
        "colsample_bytree": params["colsample_bytree"],
        "reg_alpha": params["reg_alpha"],
        "reg_lambda": params["reg_lambda"],
    }

    # Train final model
    ds = lgb.Dataset(X_train, y_train, feature_name=feature_names,
                     weight=sample_weight_train)
    model = lgb.train(lgb_params, ds, num_boost_round=n_est)

    # Walk-forward OOS calibration on training set
    if bar_indices_train is not None and tp_train is not None:
        unique_bars = np.unique(bar_indices_train)
        n_bars = len(unique_bars)
        splitter = WalkForwardSplitter(
            n_splits=8, train_period=min(14000, n_bars // 2),
            test_period=min(2000, n_bars // 10),
            purge_period=24, embargo_period=6,
        )
        oos_probs = np.zeros(len(y_train))
        oos_mask = np.zeros(len(y_train), dtype=bool)
        for bar_tr_idx, bar_te_idx in splitter.split(n_bars):
            bars_tr = unique_bars[bar_tr_idx]
            bars_te = unique_bars[bar_te_idx]
            tr_m = np.isin(bar_indices_train, bars_tr)
            te_m = np.isin(bar_indices_train, bars_te)
            if tr_m.sum() == 0 or te_m.sum() == 0:
                continue
            ds_f = lgb.Dataset(X_train[tr_m], y_train[tr_m],
                               weight=sample_weight_train[tr_m] if sample_weight_train is not None else None)
            m = lgb.train(lgb_params, ds_f, num_boost_round=n_est)
            oos_probs[te_m] = m.predict(X_train[te_m])
            oos_mask[te_m] = True

        cal = TimeAwareCalibrator()
        if oos_mask.any():
            cal.fit(oos_probs[oos_mask], y_train[oos_mask], tp_train[oos_mask])
        else:
            cal.fit(model.predict(X_train), y_train, tp_train)
    else:
        cal = TimeAwareCalibrator()
        cal.fit(model.predict(X_train), y_train, tp_train if tp_train is not None else np.full(len(y_train), 0.5))

    # Predict + calibrate test set
    raw_test = model.predict(X_test)
    cal_test = cal.transform(raw_test, tp_test)

    # Metrics
    brier = brier_score(cal_test, y_test)
    ece = expected_calibration_error(cal_test, y_test)
    acc = float(np.mean((cal_test > 0.5) == (y_test == 1)))

    # Backtest
    backtester = IntraBarBacktester(
        fee_bps=0, spread=0.02, min_edge=0.01, impact_bps=0,
        max_trades_per_bar=15, max_daily_trades=500,
        fixed_bet_usd=100.0, timeframe=tf,
    )
    bt = backtester.evaluate_fast(cal_test, y_test, mp_test, tp_test, bi_test)

    # Feature importance
    fi = dict(zip(model.feature_name(), model.feature_importance(importance_type="gain")))
    top5 = sorted(fi.items(), key=lambda x: -x[1])[:5]

    return {
        "brier": round(brier, 6),
        "ece": round(ece, 4),
        "accuracy": round(acc, 4),
        "pnl": round(bt.get("total_pnl", 0), 2),
        "sharpe": round(bt.get("sharpe", 0), 2),
        "win_rate": round(bt.get("win_rate", 0), 4),
        "n_trades": bt.get("n_trades", 0),
        "max_dd": round(bt.get("max_dd", 0), 4),
        "top5_features": [f"{n}={v:.0f}" for n, v in top5],
    }


# ══════════════════════════════════════════════════════════════════
# EXPERIMENT DEFINITIONS
# ══════════════════════════════════════════════════════════════════

def compute_path_features(dataset, asset, timeframe):
    """Compute path features from 1m bar data. Returns (X_augmented, new_feature_names)."""
    logger.info("Computing path features from 1m data...")
    minutes = TF_MINUTES[timeframe]

    # Load 1m bars
    m1_bars = load_1m_bars(asset)

    # Load parent bars for alignment
    raw_bars = load_raw_bars(asset, timeframe)

    # Build 1m close matrix aligned to parent bars
    # We need to map bar_indices in the dataset to actual bars
    # The dataset was generated from these bars, so bar_indices are sequential
    parent_times = raw_bars["time"].to_list()
    m1_close_arr = m1_bars["close"].to_numpy().astype(np.float64)
    m1_time_to_idx = {}
    from datetime import timedelta
    for i, t in enumerate(m1_bars["time"].to_list()):
        m1_time_to_idx[int(t.timestamp() * 1_000_000)] = i

    # For each bar_index in the dataset, get the 1m constituent closes
    unique_bi = np.unique(dataset.bar_indices)
    n_bars = len(unique_bi)
    # Map bar_index -> 1m close array (or None if incomplete)
    bar_m1_closes = {}
    bar_opens = {}

    opens_arr = raw_bars["open"].to_numpy().astype(np.float64)
    for bi in unique_bi:
        if bi >= len(parent_times):
            continue
        pt = parent_times[bi]
        closes_1m = []
        complete = True
        for offset_min in range(minutes):
            t_1m = pt + timedelta(minutes=offset_min)
            key = int(t_1m.timestamp() * 1_000_000)
            idx = m1_time_to_idx.get(key)
            if idx is None:
                complete = False
                break
            closes_1m.append(m1_close_arr[idx])
        if complete:
            bar_m1_closes[bi] = np.array(closes_1m)
            bar_opens[bi] = opens_arr[bi]

    # Compute path features for each sample
    n_samples = len(dataset.y)
    n_new = 10  # number of path features
    path_feats = np.zeros((n_samples, n_new), dtype=np.float64)

    for i in range(n_samples):
        bi = dataset.bar_indices[i]
        tp = dataset.time_pcts[i]

        if bi not in bar_m1_closes:
            continue  # leave as zeros

        m1c = bar_m1_closes[bi]
        opn = bar_opens[bi]
        n_complete = min(int(tp * minutes), minutes - 1)

        if n_complete <= 0:
            continue

        # Price path: open, then 1m closes up to n_complete
        path = np.concatenate([[opn], m1c[:n_complete]])
        current = dataset.X[i, 0] * opn + opn  # reconstruct current price from distance_from_open

        # 1. zero_crossings: how many times price crossed open
        above = path > opn
        crossings = int(np.sum(np.abs(np.diff(above.astype(int)))))
        path_feats[i, 0] = crossings

        # 2. max_favorable_excursion (MFE) relative to open
        path_feats[i, 1] = (np.max(path) - opn) / (opn + 1e-10)

        # 3. max_adverse_excursion (MAE) relative to open
        path_feats[i, 2] = (opn - np.min(path)) / (opn + 1e-10)

        # 4. mfe_to_current_ratio: how much of peak move is retained
        mfe = np.max(path) - opn
        current_dist = current - opn
        if abs(mfe) > 1e-10:
            path_feats[i, 3] = current_dist / mfe
        else:
            path_feats[i, 3] = 0.0

        # 5. retrace_ratio: (peak - current) / (peak - trough)
        peak = np.max(path)
        trough = np.min(path)
        total_range = peak - trough
        if total_range > 1e-10:
            path_feats[i, 4] = (peak - current) / total_range
        else:
            path_feats[i, 4] = 0.5

        # 6. path_efficiency: |start-end| / sum(|diffs|) -- 1.0 = straight line
        diffs = np.abs(np.diff(path))
        total_path = np.sum(diffs)
        if total_path > 1e-10:
            path_feats[i, 5] = abs(current - opn) / total_path
        else:
            path_feats[i, 5] = 0.0

        # 7. price_velocity: rate of change over last segment
        if len(path) >= 2:
            path_feats[i, 6] = (path[-1] - path[-2]) / (opn + 1e-10)

        # 8. price_acceleration: change in velocity
        if len(path) >= 3:
            v1 = path[-1] - path[-2]
            v0 = path[-2] - path[-3]
            path_feats[i, 7] = (v1 - v0) / (opn + 1e-10)

        # 9. volume_weighted_position (TWAP proxy) - use equal weights since we have closes
        twap = np.mean(path)
        path_feats[i, 8] = (current - twap) / (opn + 1e-10)

        # 10. path_skewness: skew of 1m returns
        if len(path) >= 4:
            rets = np.diff(path) / (opn + 1e-10)
            mu = np.mean(rets)
            std = np.std(rets)
            if std > 1e-10:
                path_feats[i, 9] = np.mean(((rets - mu) / std) ** 3)

    new_names = [
        "zero_crossings", "mfe", "mae", "mfe_to_current_ratio",
        "retrace_ratio", "path_efficiency", "price_velocity",
        "price_acceleration", "twap_position", "path_skewness",
    ]

    X_aug = np.column_stack([dataset.X, path_feats])
    aug_names = dataset.feature_names + new_names

    logger.info("Path features computed: %d samples, %d new features", n_samples, n_new)
    return X_aug, aug_names


def get_bar_returns(dataset, asset, timeframe):
    """Get actual (close-open)/open returns per bar_index. Returns array aligned to dataset."""
    raw_bars = load_raw_bars(asset, timeframe)
    opens = raw_bars["open"].to_numpy().astype(np.float64)
    closes = raw_bars["close"].to_numpy().astype(np.float64)
    returns = (closes - opens) / (opens + 1e-10)

    # Map bar_indices to returns
    sample_returns = np.zeros(len(dataset.y))
    for i in range(len(dataset.y)):
        bi = dataset.bar_indices[i]
        if bi < len(returns):
            sample_returns[i] = returns[bi]
    return sample_returns


def run_experiment_0_baseline(X, y, mp, tp, bi, params, feat_names, tf, seed):
    """Baseline: current model with fixed best params."""
    train_mask, test_mask = temporal_split(bi)
    return train_and_evaluate(
        X[train_mask], y[train_mask], X[test_mask], y[test_mask],
        mp[test_mask], tp[test_mask], bi[test_mask],
        params, feat_names, tf, seed,
        bar_indices_train=bi[train_mask], tp_train=tp[train_mask],
    )


def run_experiment_1_path_features(X_aug, y, mp, tp, bi, params, aug_names, tf, seed):
    """Add 10 path features computed from 1m data."""
    train_mask, test_mask = temporal_split(bi)
    return train_and_evaluate(
        X_aug[train_mask], y[train_mask], X_aug[test_mask], y[test_mask],
        mp[test_mask], tp[test_mask], bi[test_mask],
        params, aug_names, tf, seed,
        bar_indices_train=bi[train_mask], tp_train=tp[train_mask],
    )


def run_experiment_2_sample_weight(X, y, mp, tp, bi, params, feat_names, tf, seed, sample_returns):
    """Weight training samples by |return| magnitude."""
    train_mask, test_mask = temporal_split(bi)

    # Weight by absolute return (bars that move more get more weight)
    weights = np.abs(sample_returns[train_mask])
    # Normalize: floor at 10th percentile to avoid zeroing out flat bars entirely
    floor = np.percentile(weights[weights > 0], 10) if (weights > 0).any() else 1e-6
    weights = np.clip(weights, floor, None)
    weights = weights / weights.mean()  # normalize to mean=1

    return train_and_evaluate(
        X[train_mask], y[train_mask], X[test_mask], y[test_mask],
        mp[test_mask], tp[test_mask], bi[test_mask],
        params, feat_names, tf, seed,
        sample_weight_train=weights,
        bar_indices_train=bi[train_mask], tp_train=tp[train_mask],
    )


def run_experiment_3_cross_asset(X, y, mp, tp, bi, params, feat_names, tf, seed, asset, timeframe):
    """Add BTC intra-bar features as cross-asset signal (for non-BTC assets)."""
    if asset == "BTC":
        logger.info("Skipping cross-asset for BTC (it IS the leader)")
        return {"skipped": True, "reason": "BTC is the leader asset"}

    # Load BTC dataset
    btc_path = Path(f"data/models/pulse_v2/BTC_{timeframe}/dataset.npz")
    if not btc_path.exists():
        return {"skipped": True, "reason": f"No BTC dataset at {btc_path}"}
    btc_ds = IntraBarDataset.load(btc_path)

    # Align by bar_index and time_pct: for each sample in target asset,
    # find matching BTC sample (same bar_index, same time_pct)
    # Problem: bar_indices aren't aligned across assets (different bar counts)
    # Solution: align by TIME. Load raw bars, match by timestamp.
    logger.info("Aligning BTC data to %s by timestamp...", asset)

    raw_bars = load_raw_bars(asset, timeframe)
    btc_bars = load_raw_bars("BTC", timeframe)

    target_times = raw_bars["time"].to_list()
    btc_times = btc_bars["time"].to_list()

    # Build BTC time -> bar_index mapping
    btc_time_to_bi = {}
    for i, t in enumerate(btc_times):
        btc_time_to_bi[int(t.timestamp())] = i

    # For each target bar_index, find matching BTC bar_index
    target_to_btc_bi = {}
    for i, t in enumerate(target_times):
        btc_bi = btc_time_to_bi.get(int(t.timestamp()))
        if btc_bi is not None:
            target_to_btc_bi[i] = btc_bi

    # Build BTC feature lookup: (btc_bar_idx, time_pct) -> BTC tick features
    btc_tp_mask = filter_time_pcts(btc_ds)
    btc_X = btc_ds.X[btc_tp_mask]
    btc_bi_arr = btc_ds.bar_indices[btc_tp_mask]
    btc_tp_arr = btc_ds.time_pcts[btc_tp_mask]

    btc_lookup = {}
    for j in range(len(btc_bi_arr)):
        key = (int(btc_bi_arr[j]), round(float(btc_tp_arr[j]), 4))
        btc_lookup[key] = btc_X[j, :N_TICK]  # first 8 tick features

    # Add BTC features to each sample
    n_btc_feats = 4  # distance, vol_norm, range, bar_position
    btc_feats = np.zeros((len(y), n_btc_feats), dtype=np.float64)
    matched = 0
    for i in range(len(y)):
        target_bi = int(bi[i])
        btc_bi = target_to_btc_bi.get(target_bi)
        if btc_bi is None:
            continue
        key = (btc_bi, round(float(tp[i]), 4))
        btc_tick = btc_lookup.get(key)
        if btc_tick is not None:
            btc_feats[i, 0] = btc_tick[0]  # btc_distance_from_open
            btc_feats[i, 1] = btc_tick[1]  # btc_vol_norm_distance
            btc_feats[i, 2] = btc_tick[4]  # btc_partial_range
            btc_feats[i, 3] = btc_tick[5]  # btc_partial_bar_position
            matched += 1

    logger.info("BTC cross-asset: matched %d/%d samples (%.1f%%)",
                matched, len(y), 100 * matched / len(y))

    X_aug = np.column_stack([X, btc_feats])
    aug_names = feat_names + [
        "btc_distance_from_open", "btc_vol_norm_distance",
        "btc_partial_range", "btc_partial_bar_position",
    ]

    train_mask, test_mask = temporal_split(bi)
    return train_and_evaluate(
        X_aug[train_mask], y[train_mask], X_aug[test_mask], y[test_mask],
        mp[test_mask], tp[test_mask], bi[test_mask],
        params, aug_names, tf, seed,
        bar_indices_train=bi[train_mask], tp_train=tp[train_mask],
    )


def run_experiment_4_filter_coinflips(X, y, mp, tp, bi, params, feat_names, tf, seed, sample_returns):
    """Remove bars with |return| < threshold from training."""
    train_mask, test_mask = temporal_split(bi)

    # Filter: remove coin-flip bars from training (keep all test bars for fair comparison)
    # Threshold: bars with |return| < 0.0002 (0.02%) for 5m, scale by timeframe
    threshold = 0.0002  # conservative
    abs_ret = np.abs(sample_returns)
    significant_mask = abs_ret >= threshold

    combined_train = train_mask & significant_mask
    n_removed = train_mask.sum() - combined_train.sum()
    logger.info("Coin-flip filter: removed %d/%d training samples (%.1f%%)",
                n_removed, train_mask.sum(), 100 * n_removed / train_mask.sum())

    if combined_train.sum() < 1000:
        return {"skipped": True, "reason": "Too few samples after filtering"}

    return train_and_evaluate(
        X[combined_train], y[combined_train], X[test_mask], y[test_mask],
        mp[test_mask], tp[test_mask], bi[test_mask],
        params, feat_names, tf, seed,
        bar_indices_train=bi[combined_train], tp_train=tp[combined_train],
    )


def run_experiment_5_specialists(X, y, mp, tp, bi, params, feat_names, tf, seed):
    """Train separate early (t<=0.20) and late (t>=0.40) models."""
    train_mask, test_mask = temporal_split(bi)

    early_tps = {0.10, 0.20}
    late_tps = {0.40, 0.60, 0.80}

    # Split test set into early and late
    early_test = np.zeros(len(y), dtype=bool)
    late_test = np.zeros(len(y), dtype=bool)
    for i in range(len(y)):
        t = round(float(tp[i]), 2)
        if test_mask[i]:
            if t in early_tps:
                early_test[i] = True
            elif t in late_tps:
                late_test[i] = True

    early_train = np.zeros(len(y), dtype=bool)
    late_train = np.zeros(len(y), dtype=bool)
    for i in range(len(y)):
        t = round(float(tp[i]), 2)
        if train_mask[i]:
            if t in early_tps:
                early_train[i] = True
            elif t in late_tps:
                late_train[i] = True

    results = {}

    # Train early specialist
    if early_train.sum() > 0 and early_test.sum() > 0:
        logger.info("Training early specialist (t<=0.20): %d train, %d test",
                     early_train.sum(), early_test.sum())
        early_res = train_and_evaluate(
            X[early_train], y[early_train], X[early_test], y[early_test],
            mp[early_test], tp[early_test], bi[early_test],
            params, feat_names, tf, seed,
            bar_indices_train=bi[early_train], tp_train=tp[early_train],
        )
        results["early"] = early_res

    # Train late specialist
    if late_train.sum() > 0 and late_test.sum() > 0:
        logger.info("Training late specialist (t>=0.40): %d train, %d test",
                     late_train.sum(), late_test.sum())
        late_res = train_and_evaluate(
            X[late_train], y[late_train], X[late_test], y[late_test],
            mp[late_test], tp[late_test], bi[late_test],
            params, feat_names, tf, seed,
            bar_indices_train=bi[late_train], tp_train=tp[late_train],
        )
        results["late"] = late_res

    # Combined metrics: weighted average by trade count
    if "early" in results and "late" in results:
        e, l = results["early"], results["late"]
        n_e = e.get("n_trades", 0)
        n_l = l.get("n_trades", 0)
        n_tot = n_e + n_l
        if n_tot > 0:
            w_e = n_e / n_tot
            w_l = n_l / n_tot
            results["combined"] = {
                "brier": round(e["brier"] * w_e + l["brier"] * w_l, 6),
                "accuracy": round(e["accuracy"] * w_e + l["accuracy"] * w_l, 4),
                "pnl": round(e["pnl"] + l["pnl"], 2),
                "sharpe": round(e["sharpe"] * w_e + l["sharpe"] * w_l, 2),
                "win_rate": round(e["win_rate"] * w_e + l["win_rate"] * w_l, 4),
                "n_trades": n_tot,
            }

    return results


def run_experiment_6_continuous_target(X, y, mp, tp, bi, params, feat_names, tf, seed, sample_returns):
    """Train with regression target (return magnitude), convert to binary prob."""
    train_mask, test_mask = temporal_split(bi)

    # Regression target: (close - open) / open
    y_reg = sample_returns.copy()

    # Modify params for regression
    reg_params = params.copy()

    # Train regression model
    device = detect_device(prefer_gpu=True)
    n_est = reg_params["n_estimators"]
    lgb_params = {
        "objective": "regression",
        "metric": "mse",
        "verbosity": -1,
        "device": device,
        "seed": seed,
        "learning_rate": reg_params["learning_rate"],
        "max_depth": reg_params["max_depth"],
        "num_leaves": reg_params["num_leaves"],
        "min_child_samples": reg_params["min_child_samples"],
        "subsample": reg_params["subsample"],
        "colsample_bytree": reg_params["colsample_bytree"],
        "reg_alpha": reg_params["reg_alpha"],
        "reg_lambda": reg_params["reg_lambda"],
    }

    ds = lgb.Dataset(X[train_mask], y_reg[train_mask], feature_name=feat_names)
    model = lgb.train(lgb_params, ds, num_boost_round=n_est)

    # Predict returns on test set
    pred_returns = model.predict(X[test_mask])

    # Convert to probability: sigmoid(return / scale)
    # Scale: use training set return std as normalization
    scale = max(np.std(y_reg[train_mask]), 1e-6)
    raw_probs = 1.0 / (1.0 + np.exp(-pred_returns / scale))
    cal_test = np.clip(raw_probs, 0.01, 0.99)

    # Evaluate
    y_test = y[test_mask]
    brier = brier_score(cal_test, y_test)
    ece = expected_calibration_error(cal_test, y_test)
    acc = float(np.mean((cal_test > 0.5) == (y_test == 1)))

    backtester = IntraBarBacktester(
        fee_bps=0, spread=0.02, min_edge=0.01, impact_bps=0,
        max_trades_per_bar=15, max_daily_trades=500,
        fixed_bet_usd=100.0, timeframe=tf,
    )
    bt = backtester.evaluate_fast(cal_test, y_test, mp[test_mask], tp[test_mask], bi[test_mask])

    fi = dict(zip(model.feature_name(), model.feature_importance(importance_type="gain")))
    top5 = sorted(fi.items(), key=lambda x: -x[1])[:5]

    return {
        "brier": round(brier, 6),
        "ece": round(ece, 4),
        "accuracy": round(acc, 4),
        "pnl": round(bt.get("total_pnl", 0), 2),
        "sharpe": round(bt.get("sharpe", 0), 2),
        "win_rate": round(bt.get("win_rate", 0), 4),
        "n_trades": bt.get("n_trades", 0),
        "max_dd": round(bt.get("max_dd", 0), 4),
        "top5_features": [f"{n}={v:.0f}" for n, v in top5],
        "return_scale": round(scale, 6),
    }


def run_experiment_7_trinomial(X, y, mp, tp, bi, params, feat_names, tf, seed, sample_returns):
    """Trinomial target: UP/FLAT/DOWN with sample weighting (zero weight for FLAT)."""
    train_mask, test_mask = temporal_split(bi)

    # Define flat zone: |return| < threshold
    threshold = 0.0003
    flat_mask = np.abs(sample_returns) < threshold

    # Weighted approach: give flat bars zero weight (effectively removes them)
    # but keeps dataset size the same for bar-level splitting
    weights = np.ones(train_mask.sum())
    flat_in_train = flat_mask[train_mask]
    weights[flat_in_train] = 0.01  # near-zero weight for flat bars

    n_flat = flat_in_train.sum()
    logger.info("Trinomial: %d/%d training samples classified as FLAT (%.1f%%)",
                n_flat, train_mask.sum(), 100 * n_flat / train_mask.sum())

    return train_and_evaluate(
        X[train_mask], y[train_mask], X[test_mask], y[test_mask],
        mp[test_mask], tp[test_mask], bi[test_mask],
        params, feat_names, tf, seed,
        sample_weight_train=weights,
        bar_indices_train=bi[train_mask], tp_train=tp[train_mask],
    )


def run_experiment_8_conditional_betting(X, y, mp, tp, bi, params, feat_names, tf, seed, sample_returns):
    """Conditional betting: only bet on bars where model is likely to be accurate.
    Uses volatility regime + volume features as confidence gate."""
    train_mask, test_mask = temporal_split(bi)

    # Train main model
    main_result = train_and_evaluate(
        X[train_mask], y[train_mask], X[test_mask], y[test_mask],
        mp[test_mask], tp[test_mask], bi[test_mask],
        params, feat_names, tf, seed,
        bar_indices_train=bi[train_mask], tp_train=tp[train_mask],
    )

    # Now filter: only bet on bars with |return| > median (higher magnitude = more predictable)
    # This simulates a meta-model that identifies "worth betting" bars
    abs_ret_test = np.abs(sample_returns[test_mask])
    median_ret = np.median(abs_ret_test[abs_ret_test > 0])

    # Keep only samples where the bar has significant movement
    significant = abs_ret_test >= median_ret

    if significant.sum() < 100:
        return {"skipped": True, "reason": "Too few significant bars in test"}

    # Re-evaluate on filtered test set (this is an oracle filter - shows ceiling)
    device = detect_device(prefer_gpu=True)
    n_est = params["n_estimators"]
    lgb_params = {
        "objective": "binary", "metric": "binary_logloss",
        "verbosity": -1, "device": device, "seed": seed,
        "learning_rate": params["learning_rate"],
        "max_depth": params["max_depth"],
        "num_leaves": params["num_leaves"],
        "min_child_samples": params["min_child_samples"],
        "subsample": params["subsample"],
        "colsample_bytree": params["colsample_bytree"],
        "reg_alpha": params["reg_alpha"],
        "reg_lambda": params["reg_lambda"],
    }
    ds = lgb.Dataset(X[train_mask], y[train_mask], feature_name=feat_names)
    model = lgb.train(lgb_params, ds, num_boost_round=n_est)
    raw_test = model.predict(X[test_mask])

    # Calibrate
    cal = TimeAwareCalibrator()
    cal.fit(model.predict(X[train_mask]), y[train_mask], tp[train_mask])
    cal_test = cal.transform(raw_test, tp[test_mask])

    # Metrics on significant bars only
    y_sig = y[test_mask][significant]
    cal_sig = cal_test[significant]
    mp_sig = mp[test_mask][significant]
    tp_sig = tp[test_mask][significant]
    bi_sig = bi[test_mask][significant]

    brier = brier_score(cal_sig, y_sig)
    acc = float(np.mean((cal_sig > 0.5) == (y_sig == 1)))

    backtester = IntraBarBacktester(
        fee_bps=0, spread=0.02, min_edge=0.01, impact_bps=0,
        max_trades_per_bar=15, max_daily_trades=500,
        fixed_bet_usd=100.0, timeframe=tf,
    )
    bt = backtester.evaluate_fast(cal_sig, y_sig, mp_sig, tp_sig, bi_sig)

    return {
        "note": "ORACLE FILTER (uses future |return|) - shows ceiling, not achievable",
        "full_brier": main_result["brier"],
        "filtered_brier": round(brier, 6),
        "filtered_accuracy": round(acc, 4),
        "filtered_pnl": round(bt.get("total_pnl", 0), 2),
        "filtered_sharpe": round(bt.get("sharpe", 0), 2),
        "filtered_win_rate": round(bt.get("win_rate", 0), 4),
        "filtered_n_trades": bt.get("n_trades", 0),
        "pct_bars_kept": round(100 * significant.mean(), 1),
    }


def run_experiment_9_combined(X_aug, y, mp, tp, bi, params, aug_names, tf, seed, sample_returns):
    """Combine best ideas: path features + sample weighting + coin-flip filter."""
    train_mask, test_mask = temporal_split(bi)

    # Coin-flip filter
    threshold = 0.0002
    significant = np.abs(sample_returns) >= threshold
    combined_train = train_mask & significant

    # Sample weighting by |return|
    weights = np.abs(sample_returns[combined_train])
    floor = np.percentile(weights[weights > 0], 10) if (weights > 0).any() else 1e-6
    weights = np.clip(weights, floor, None)
    weights = weights / weights.mean()

    n_removed = train_mask.sum() - combined_train.sum()
    logger.info("Combined: %d training samples after coin-flip filter, path features added",
                combined_train.sum())

    return train_and_evaluate(
        X_aug[combined_train], y[combined_train], X_aug[test_mask], y[test_mask],
        mp[test_mask], tp[test_mask], bi[test_mask],
        params, aug_names, tf, seed,
        sample_weight_train=weights,
        bar_indices_train=bi[combined_train], tp_train=tp[combined_train],
    )


# ══════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════

def main():
    args = parse_args()
    tf = TF_MAP[args.timeframe]

    if args.experiments == "all":
        exp_nums = list(range(10))
    else:
        exp_nums = [int(x) for x in args.experiments.split(",")]

    logger.info("=" * 60)
    logger.info("PULSE EXPERIMENT HARNESS: %s/%s", args.asset, args.timeframe)
    logger.info("Experiments to run: %s", exp_nums)
    logger.info("=" * 60)

    # Load base data
    t0 = time.time()
    dataset, params, raw_bars, _ = prepare_base_data(args.asset, args.timeframe)
    logger.info("Model params: %s", json.dumps(params, indent=2))

    # Filter time_pcts
    tp_mask = filter_time_pcts(dataset)
    X = dataset.X[tp_mask]
    y = dataset.y[tp_mask]
    mp = dataset.market_probs[tp_mask]
    tp_arr = dataset.time_pcts[tp_mask]
    bi = dataset.bar_indices[tp_mask]
    feat_names = dataset.feature_names

    logger.info("Dataset: %d samples, %d features, %d bars",
                len(y), X.shape[1], len(np.unique(bi)))

    # Get actual returns (needed by experiments 2, 4, 6, 7, 8, 9)
    sample_returns = None
    needs_returns = {2, 4, 6, 7, 8, 9}
    if needs_returns & set(exp_nums):
        sample_returns = get_bar_returns(dataset, args.asset, args.timeframe)
        sample_returns = sample_returns[tp_mask]
        logger.info("Loaded bar returns: mean=%.6f, std=%.6f",
                     sample_returns.mean(), sample_returns.std())

    # Path features (needed by experiments 1, 9)
    X_aug, aug_names = None, None
    if {1, 9} & set(exp_nums):
        X_aug_full, aug_names = compute_path_features(dataset, args.asset, args.timeframe)
        X_aug = X_aug_full[tp_mask]

    results = {}

    experiments = {
        0: ("BASELINE (fixed best params)", lambda: run_experiment_0_baseline(X, y, mp, tp_arr, bi, params, feat_names, tf, args.seed)),
        1: ("PATH FEATURES (+10 from 1m data)", lambda: run_experiment_1_path_features(X_aug, y, mp, tp_arr, bi, params, aug_names, tf, args.seed)),
        2: ("SAMPLE WEIGHT by |return|", lambda: run_experiment_2_sample_weight(X, y, mp, tp_arr, bi, params, feat_names, tf, args.seed, sample_returns)),
        3: ("CROSS-ASSET BTC lead", lambda: run_experiment_3_cross_asset(X, y, mp, tp_arr, bi, params, feat_names, tf, args.seed, args.asset, args.timeframe)),
        4: ("FILTER COIN-FLIPS", lambda: run_experiment_4_filter_coinflips(X, y, mp, tp_arr, bi, params, feat_names, tf, args.seed, sample_returns)),
        5: ("PER-TIMEPOINT SPECIALISTS", lambda: run_experiment_5_specialists(X, y, mp, tp_arr, bi, params, feat_names, tf, args.seed)),
        6: ("CONTINUOUS TARGET (regression)", lambda: run_experiment_6_continuous_target(X, y, mp, tp_arr, bi, params, feat_names, tf, args.seed, sample_returns)),
        7: ("TRINOMIAL (downweight flat)", lambda: run_experiment_7_trinomial(X, y, mp, tp_arr, bi, params, feat_names, tf, args.seed, sample_returns)),
        8: ("CONDITIONAL BETTING (oracle)", lambda: run_experiment_8_conditional_betting(X, y, mp, tp_arr, bi, params, feat_names, tf, args.seed, sample_returns)),
        9: ("COMBINED (path + weight + filter)", lambda: run_experiment_9_combined(X_aug, y, mp, tp_arr, bi, params, aug_names, tf, args.seed, sample_returns)),
    }

    for exp_num in exp_nums:
        if exp_num not in experiments:
            logger.warning("Unknown experiment %d, skipping", exp_num)
            continue

        name, func = experiments[exp_num]
        logger.info("\n" + "=" * 60)
        logger.info("EXPERIMENT %d: %s", exp_num, name)
        logger.info("=" * 60)

        t_start = time.time()
        try:
            result = func()
            elapsed = time.time() - t_start
            result["elapsed_s"] = round(elapsed, 1)
            results[f"exp{exp_num}_{name}"] = result
            logger.info("Result: %s", json.dumps(result, indent=2, default=str))
        except Exception as e:
            elapsed = time.time() - t_start
            results[f"exp{exp_num}_{name}"] = {"error": str(e), "elapsed_s": round(elapsed, 1)}
            logger.error("FAILED: %s", e, exc_info=True)

    # Summary
    total_elapsed = time.time() - t0
    logger.info("\n" + "=" * 60)
    logger.info("SUMMARY: %s/%s (%.0fs total)", args.asset, args.timeframe, total_elapsed)
    logger.info("=" * 60)

    # Print comparison table
    print(f"\n{'='*80}")
    print(f"RESULTS: {args.asset}/{args.timeframe}")
    print(f"{'='*80}")
    print(f"{'Experiment':<40} {'Brier':>8} {'Acc':>6} {'PnL':>10} {'Sharpe':>7} {'WR':>6} {'Trades':>7}")
    print("-" * 80)

    baseline_brier = None
    for key, res in results.items():
        if "error" in res or res.get("skipped"):
            print(f"{key[:40]:<40} {'ERROR' if 'error' in res else 'SKIP':>8}")
            continue

        brier = res.get("brier", res.get("filtered_brier", "?"))
        acc = res.get("accuracy", res.get("filtered_accuracy", "?"))
        pnl = res.get("pnl", res.get("filtered_pnl", "?"))
        sharpe = res.get("sharpe", res.get("filtered_sharpe", "?"))
        wr = res.get("win_rate", res.get("filtered_win_rate", "?"))
        trades = res.get("n_trades", res.get("filtered_n_trades", "?"))

        if isinstance(brier, (int, float)):
            if baseline_brier is None:
                baseline_brier = brier
            delta = f" ({(brier - baseline_brier) / baseline_brier * 100:+.1f}%)" if baseline_brier else ""
        else:
            delta = ""

        # Handle specialist experiment with nested results
        if "combined" in res:
            c = res["combined"]
            print(f"{key[:40]:<40} {c['brier']:>8.6f} {c['accuracy']:>6.4f} {c['pnl']:>10.2f} {c['sharpe']:>7.2f} {c['win_rate']:>6.4f} {c['n_trades']:>7}")
            continue

        if isinstance(brier, (int, float)):
            print(f"{key[:40]:<40} {brier:>8.6f}{delta:>0} {acc:>6.4f} {pnl:>10.2f} {sharpe:>7.2f} {wr:>6.4f} {trades:>7}")
        else:
            print(f"{key[:40]:<40} {brier:>8}")

    print(f"\n{'='*80}")

    # Write results to file
    out_path = Path(f"autoresearch/experiments/pulse_ideas_{args.asset}_{args.timeframe}.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Results saved to {out_path}")


if __name__ == "__main__":
    main()
