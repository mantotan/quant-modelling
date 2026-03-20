#!/usr/bin/env python
"""Replay backtester: compares paper trading results against backtest.

Reads paper trade JSONL logs and reruns IntraBarBacktester on the same bars
with two modes:
  Mode A (real odds):      Uses real Polymarket odds captured during paper trading.
  Mode B (synthetic odds): Uses Black-Scholes synthetic odds for the same bars.

This directly measures the gap between paper trading and backtesting.

Usage:
    uv run scripts/replay_backtest.py --asset ETH --timeframe 5m
    uv run scripts/replay_backtest.py --asset ETH --date 2026-03-20
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from qm.backtest.intrabar_backtest import IntraBarBacktester
from qm.core.types import Timeframe

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("replay_backtest")


TF_MAP = {"5m": Timeframe.M5, "15m": Timeframe.M15, "1h": Timeframe.H1}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Replay backtester")
    p.add_argument("--asset", required=True, choices=["BTC", "ETH", "SOL", "XRP"])
    p.add_argument("--timeframe", default="5m", choices=["5m", "15m", "1h"])
    p.add_argument(
        "--date", default=None,
        help="Specific date (YYYY-MM-DD). If omitted, uses all available logs.",
    )
    p.add_argument(
        "--paper-dir", default="data/paper_trades",
        help="Base directory for paper trade JSONL logs",
    )
    p.add_argument(
        "--output-dir", default="data/reconciliation",
        help="Output directory for reconciliation reports",
    )
    return p.parse_args()


def load_paper_trades(
    paper_dir: Path, asset: str, tf: str, filter_date: str | None,
) -> list[dict]:
    """Load prediction events from JSONL files."""
    log_dir = paper_dir / f"{asset}_{tf}"
    if not log_dir.exists():
        logger.error("No paper trade logs at %s", log_dir)
        return []

    predictions: list[dict] = []
    pattern = f"trades_{filter_date}.jsonl" if filter_date else "trades_*.jsonl"

    for path in sorted(log_dir.glob(pattern)):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                event = json.loads(line)
                if event.get("type") == "prediction":
                    predictions.append(event)

    logger.info("Loaded %d predictions from %s", len(predictions), log_dir)
    return predictions


def load_resolutions(
    paper_dir: Path, asset: str, tf: str, filter_date: str | None,
) -> dict[str, list[dict]]:
    """Load resolution events, keyed by condition_id.

    Multiple predictions can share a condition_id (e.g., predictions at
    different elapsed_pct within the same bar).  We accumulate all
    resolution records per condition_id so that PnL is summed correctly
    instead of being clobbered by a later record.
    """
    log_dir = paper_dir / f"{asset}_{tf}"
    if not log_dir.exists():
        return {}

    resolutions: dict[str, list[dict]] = {}
    pattern = f"trades_{filter_date}.jsonl" if filter_date else "trades_*.jsonl"

    for path in sorted(log_dir.glob(pattern)):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                event = json.loads(line)
                if event.get("type") == "resolution":
                    cid = event["condition_id"]
                    resolutions.setdefault(cid, []).append(event)

    return resolutions


def build_arrays(
    predictions: list[dict], resolutions: dict[str, list[dict]],
) -> dict[str, np.ndarray] | None:
    """Convert paper trade events to numpy arrays for backtester.

    ``resolutions`` maps each condition_id to a *list* of resolution
    records.  PnL is summed across all records for a given condition_id
    so that multi-prediction bars are accounted for correctly.
    """
    if not predictions:
        return None

    # Only use predictions that have resolved
    resolved = [
        p for p in predictions
        if p["condition_id"] in resolutions
    ]

    if not resolved:
        logger.warning(
            "No resolved predictions yet (%d pending)", len(predictions),
        )
        return None

    logger.info(
        "%d/%d predictions have resolutions",
        len(resolved), len(predictions),
    )

    model_probs = np.array([p["model_prob"] for p in resolved])
    market_probs = np.array([p["market_prob"] for p in resolved])
    time_pcts = np.array([p["elapsed_pct"] for p in resolved])
    bar_indices = np.array([p["bar_id"] for p in resolved])

    # Target: 1 if outcome was UP, 0 otherwise
    # All resolution records for a condition_id share the same outcome;
    # take from the first record.
    targets = np.array([
        1.0 if resolutions[p["condition_id"]][0]["outcome"].upper() in ("UP", "YES")
        else 0.0
        for p in resolved
    ])

    # Paper PnL per trade.
    # New logs (with position_id): each resolution record has per-position PnL,
    # so we consume records sequentially per condition_id (1:1 with fills).
    # Old logs (no position_id): dedup by condition_id to avoid double-counting.
    has_position_ids = any(
        r.get("position_id") for recs in resolutions.values() for r in recs
    )
    resolution_idx: dict[str, int] = {}  # tracks next unused record per cid
    seen_cids: set[str] = set()
    paper_pnls_list: list[float] = []
    for p in resolved:
        cid = p["condition_id"]
        if p["fill_status"] != "filled":
            paper_pnls_list.append(0.0)
        elif has_position_ids:
            # New format: each resolution record has correct per-position PnL
            idx = resolution_idx.get(cid, 0)
            records = resolutions[cid]
            pnl = records[idx]["pnl"] if idx < len(records) else 0.0
            paper_pnls_list.append(pnl)
            resolution_idx[cid] = idx + 1
        elif cid not in seen_cids:
            # Old format fallback: sum all records, count once per condition_id
            paper_pnls_list.append(sum(r["pnl"] for r in resolutions[cid]))
            seen_cids.add(cid)
        else:
            paper_pnls_list.append(0.0)
    paper_pnls = np.array(paper_pnls_list)

    # Fill info
    fill_statuses = [p["fill_status"] for p in resolved]
    fill_prices = np.array([p["fill_price"] for p in resolved])
    sizes = np.array([p["size_usd"] for p in resolved])
    spreads = np.array([p["market_spread"] for p in resolved])
    signal_sides = [p.get("signal_side", "") for p in resolved]

    return {
        "model_probs": model_probs,
        "market_probs": market_probs,
        "targets": targets,
        "time_pcts": time_pcts,
        "bar_indices": bar_indices,
        "paper_pnls": paper_pnls,
        "fill_statuses": fill_statuses,
        "fill_prices": fill_prices,
        "sizes": sizes,
        "spreads": spreads,
        "signal_sides": signal_sides,
    }


def replay_paper_pnl(
    arrays: dict[str, np.ndarray],
    fee_bps: float = 0,
) -> dict:
    """Replay PnL using actual paper trade sizes and Portfolio accounting.

    This recomputes PnL from paper trade fills using the same shares-based
    model as Portfolio.on_resolution():
      - shares = size_usd / fill_price
      - win:  pnl = shares * (1 - fill_price) - fee
      - loss: pnl = -size_usd

    Returns metrics in real USD, directly comparable to paper trading PnL.
    """
    fill_statuses = arrays["fill_statuses"]
    sizes = arrays["sizes"]
    fill_prices = arrays["fill_prices"]
    model_probs = arrays["model_probs"]
    market_probs = arrays["market_probs"]
    targets = arrays["targets"]
    spreads = arrays["spreads"]
    signal_sides = arrays.get("signal_sides", [])

    n = len(model_probs)
    pnl_per_trade = np.zeros(n)
    n_trades = 0

    for i in range(n):
        if fill_statuses[i] != "filled" or sizes[i] <= 0:
            continue

        size_usd = sizes[i]
        fp = fill_prices[i]
        if fp <= 0.0 or fp >= 1.0:
            continue

        # Determine side: use logged signal_side if available, else recalculate
        if i < len(signal_sides) and signal_sides[i]:
            bet_up = signal_sides[i].upper() == "UP"
        else:
            mp = model_probs[i]
            mkt = market_probs[i]
            half_spread = spreads[i] / 2
            edge_up = mp - mkt - half_spread
            edge_down = (1 - mp) - (1 - mkt) - half_spread
            bet_up = edge_up > edge_down

        # Was the bet correct?
        correct = (bet_up and targets[i] == 1) or (not bet_up and targets[i] == 0)

        # Shares-based PnL (same as Portfolio.Position)
        shares = size_usd / fp
        if correct:
            gross = shares * (1 - fp)
            fee = gross * (fee_bps / 10_000) if fee_bps > 0 else 0.0
            pnl_per_trade[i] = gross - fee
        else:
            pnl_per_trade[i] = -size_usd

        n_trades += 1

    total_pnl = float(pnl_per_trade.sum())
    traded_pnls = pnl_per_trade[pnl_per_trade != 0]
    win_rate = float((traded_pnls > 0).mean()) if len(traded_pnls) > 0 else 0.0

    return {
        "total_pnl": total_pnl,
        "n_trades": n_trades,
        "win_rate": win_rate,
        "avg_pnl_per_trade": float(traded_pnls.mean()) if len(traded_pnls) > 0 else 0.0,
    }


def run_replay(
    arrays: dict[str, np.ndarray],
    timeframe: Timeframe,
    knobs: dict,
) -> dict:
    """Run backtest replay in three modes and compute divergences.

    Mode A (paper-sized): Replays using actual paper trade sizes and
        Portfolio-compatible shares-based PnL. Produces USD values
        directly comparable to paper trading PnL.
    Mode A' (backtester, real odds): IntraBarBacktester with real market
        odds. PnL in fractional units (for Sharpe/metrics only).
    Mode B (backtester, synthetic): IntraBarBacktester with 0.50 market
        odds. PnL in fractional units (for Sharpe/metrics only).
    """
    bt_cfg = knobs.get("backtest", {})
    fee_bps = bt_cfg.get("fee_bps", 0)

    # Mode A: replay with actual paper trade sizes (real USD)
    metrics_a = replay_paper_pnl(arrays, fee_bps=fee_bps)

    # Mode A' (backtester): real market odds, fractional sizing
    backtester_a = IntraBarBacktester(
        fee_bps=fee_bps,
        spread=float(np.median(arrays["spreads"])),
        min_edge=bt_cfg.get("min_edge", 0.01),
        max_trades_per_bar=bt_cfg.get("max_trades_per_bar", 15),
        max_daily_trades=bt_cfg.get("max_daily_trades", 500),
        fixed_bet_usd=bt_cfg.get("fixed_bet_usd", 100.0),
        timeframe=timeframe,
    )

    metrics_a_bt = backtester_a.evaluate_fast(
        model_probs=arrays["model_probs"],
        targets=arrays["targets"],
        market_probs=arrays["market_probs"],
        time_pcts=arrays["time_pcts"],
        bar_indices=arrays["bar_indices"],
    )

    # Mode B: synthetic backtest (fixed spread from knobs)
    backtester_b = IntraBarBacktester(
        fee_bps=fee_bps,
        spread=bt_cfg.get("spread", 0.02),
        min_edge=bt_cfg.get("min_edge", 0.01),
        max_trades_per_bar=bt_cfg.get("max_trades_per_bar", 15),
        max_daily_trades=bt_cfg.get("max_daily_trades", 500),
        fixed_bet_usd=bt_cfg.get("fixed_bet_usd", 100.0),
        timeframe=timeframe,
    )

    synthetic_probs = np.full_like(arrays["market_probs"], 0.50)

    metrics_b = backtester_b.evaluate_fast(
        model_probs=arrays["model_probs"],
        targets=arrays["targets"],
        market_probs=synthetic_probs,
        time_pcts=arrays["time_pcts"],
        bar_indices=arrays["bar_indices"],
    )

    return {
        "mode_a": metrics_a,
        "mode_a_bt": metrics_a_bt,
        "mode_b": metrics_b,
    }


def compute_divergences(
    arrays: dict[str, np.ndarray],
    replay_metrics: dict,
) -> dict:
    """Compute divergence metrics between paper and backtest.

    Uses mode_a (paper-sized replay in real USD) for PnL comparison
    against paper trading. mode_a_bt and mode_b are fractional-unit
    backtester runs used only for Sharpe and directional metrics.
    """
    # Market odds divergence (real vs 0.50 baseline)
    real_odds = arrays["market_probs"]
    odds_deviation = np.abs(real_odds - 0.50)

    # Edge sign comparison (would backtest agree on trade direction?)
    model_probs = arrays["model_probs"]
    real_edge_up = model_probs - real_odds
    synthetic_edge_up = model_probs - 0.50
    edge_sign_flip = np.mean(np.sign(real_edge_up) != np.sign(synthetic_edge_up))

    # Edge-weighted flip: weights each flip by |synthetic_edge|
    # A flip on a 0.001-edge trade is noise; a flip on 0.10-edge is catastrophic
    flipped = np.sign(real_edge_up) != np.sign(synthetic_edge_up)
    abs_synthetic_edge = np.abs(synthetic_edge_up)
    total_edge = abs_synthetic_edge.sum()
    edge_weighted_flip = float(
        (flipped * abs_synthetic_edge).sum() / total_edge
    ) if total_edge > 0 else 0.0

    # Paper PnL vs replay PnL (both in real USD now)
    paper_total = float(arrays["paper_pnls"].sum())
    replay_a_total = float(replay_metrics["mode_a"].get("total_pnl", 0))
    replay_b_total = float(replay_metrics["mode_b"].get("total_pnl", 0))

    # Backtester metrics (fractional, for Sharpe only)
    replay_a_bt_total = float(replay_metrics["mode_a_bt"].get("total_pnl", 0))

    # Per-trade PnL correlation (paper vs replay_a)
    filled = np.array([s == "filled" for s in arrays["fill_statuses"]])
    n_filled_paper = int(filled.sum())

    # Trade count comparison (paper-sized replay uses same fills)
    n_replay_a = int(replay_metrics["mode_a"].get("n_trades", 0))
    n_replay_b = int(replay_metrics["mode_b"].get("n_trades", 0))
    trade_ratio = n_replay_a / max(n_filled_paper, 1)

    return {
        "market_odds_mae": float(odds_deviation.mean()),
        "market_odds_max_dev": float(odds_deviation.max()),
        "market_odds_mean": float(real_odds.mean()),
        "edge_sign_flip_pct": float(edge_sign_flip * 100),
        "edge_weighted_flip_pct": float(edge_weighted_flip * 100),
        "pnl_paper": paper_total,
        "pnl_replay_real_odds": replay_a_total,
        "pnl_replay_synthetic_odds": replay_b_total,
        "pnl_replay_bt_fractional": replay_a_bt_total,
        "n_paper_filled": n_filled_paper,
        "n_replay_a_trades": n_replay_a,
        "n_replay_b_trades": n_replay_b,
        "trade_count_ratio": round(trade_ratio, 3),
        "median_spread_observed": float(np.median(arrays["spreads"])),
        "replay_a_bt_sharpe": float(replay_metrics["mode_a_bt"].get("sharpe", 0)),
    }


def assess_trust(divergences: dict) -> dict:
    """Classify trust level based on divergence thresholds."""
    checks = {
        "market_odds_mae_ok": divergences["market_odds_mae"] < 0.03,
        "edge_sign_flip_ok": divergences["edge_weighted_flip_pct"] < 5.0,
        "pnl_sign_match": (
            (divergences["pnl_paper"] >= 0) == (divergences["pnl_replay_real_odds"] >= 0)
            if divergences["pnl_paper"] != 0 else True
        ),
        "trade_count_ok": 0.8 <= divergences["trade_count_ratio"] <= 1.2,
    }

    n_pass = sum(checks.values())
    if n_pass == len(checks):
        trust = "TRUSTWORTHY"
    elif n_pass >= len(checks) - 1:
        trust = "SUSPICIOUS"
    else:
        trust = "UNRELIABLE"

    return {
        "thresholds_passed": checks,
        "trust_level": trust,
        "n_checks_passed": n_pass,
        "n_checks_total": len(checks),
    }


def main() -> None:
    args = parse_args()
    tf = TF_MAP[args.timeframe]

    knobs_path = Path("autoresearch/best_knobs.json")
    knobs = json.loads(knobs_path.read_text()) if knobs_path.exists() else {}

    paper_dir = Path(args.paper_dir)

    # Load paper trades
    predictions = load_paper_trades(
        paper_dir, args.asset, args.timeframe, args.date,
    )
    if not predictions:
        logger.error("No paper trade predictions found. Exiting.")
        sys.exit(1)

    resolutions = load_resolutions(
        paper_dir, args.asset, args.timeframe, args.date,
    )
    logger.info("Found %d resolutions", len(resolutions))

    # Build arrays
    arrays = build_arrays(predictions, resolutions)
    if arrays is None:
        logger.error("Cannot build arrays (no resolved trades). Exiting.")
        sys.exit(1)

    # Run replay
    replay_metrics = run_replay(arrays, tf, knobs)
    logger.info(
        "Mode A (paper-sized, real USD): %s",
        json.dumps(replay_metrics["mode_a"], indent=2),
    )
    logger.info(
        "Mode A' (backtester, fractional): %s",
        json.dumps(replay_metrics["mode_a_bt"], indent=2),
    )
    logger.info(
        "Mode B (backtester, synthetic): %s",
        json.dumps(replay_metrics["mode_b"], indent=2),
    )

    # Compute divergences
    divergences = compute_divergences(arrays, replay_metrics)
    trust = assess_trust(divergences)

    # Build report
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "asset": args.asset,
        "timeframe": args.timeframe,
        "date_filter": args.date,
        "n_predictions": len(predictions),
        "n_resolved": len(arrays["model_probs"]),
        "n_resolutions": len(resolutions),
        "divergences": divergences,
        **trust,
        "replay_mode_a": replay_metrics["mode_a"],
        "replay_mode_a_bt": replay_metrics["mode_a_bt"],
        "replay_mode_b": replay_metrics["mode_b"],
    }

    # Write report
    out_dir = Path(args.output_dir) / f"{args.asset}_{args.timeframe}"
    out_dir.mkdir(parents=True, exist_ok=True)
    today = args.date or date.today().isoformat()
    out_path = out_dir / f"report_{today}.json"
    out_path.write_text(json.dumps(report, indent=2, default=str))
    logger.info("Report written: %s", out_path)

    # Summary
    logger.info("=" * 60)
    logger.info("RECONCILIATION SUMMARY")
    logger.info("=" * 60)
    logger.info("  Trust level:       %s", trust["trust_level"])
    logger.info("  Checks passed:     %d/%d", trust["n_checks_passed"], trust["n_checks_total"])
    logger.info("  Market odds MAE:   %.4f", divergences["market_odds_mae"])
    logger.info("  Edge sign flip %%:  %.1f%%", divergences["edge_sign_flip_pct"])
    logger.info("  Edge wt flip %%:   %.1f%%", divergences["edge_weighted_flip_pct"])
    logger.info("  Paper PnL:         $%.2f", divergences["pnl_paper"])
    logger.info("  Replay PnL (real): $%.2f", divergences["pnl_replay_real_odds"])
    logger.info("  Replay PnL (syn):  $%.2f", divergences["pnl_replay_synthetic_odds"])
    logger.info("  Trade count ratio: %.2f", divergences["trade_count_ratio"])
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
