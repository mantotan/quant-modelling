"""Compare live paper trading PnL vs backtest Dutch vs backtest Divergence.

Uses the exact same tick data and bar range from paper trading.
"""

from __future__ import annotations

import json
import glob
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from qm.data.connectors.polymarket_ws import TokenBook
from qm.strategy.engines import create_engine
from qm.strategy.dutch.fill_simulator import LimitOrderSimulator

BAR_SECS = {"5m": 300, "15m": 900, "1h": 3600}


def _depth(price: float) -> float:
    dist = min(price, 1.0 - price)
    return max(5.0, 50.0 * dist / 0.5)


def tick_to_books(t: dict):
    bid_up = t.get("bid_up", 0.01)
    ask_up = t.get("ask_up", 0.99)
    bid_dn = t.get("bid_dn", 0.01)
    ask_dn = t.get("ask_dn", 0.99)
    bu = TokenBook(token_id="up")
    bu.best_bid, bu.best_ask = bid_up, ask_up
    if bid_up > 0:
        bu.bids = {bid_up: _depth(bid_up)}
    if ask_up < 1.0:
        bu.asks = {ask_up: _depth(ask_up)}
    bd = TokenBook(token_id="dn")
    bd.best_bid, bd.best_ask = bid_dn, ask_dn
    if bid_dn > 0:
        bd.bids = {bid_dn: _depth(bid_dn)}
    if ask_dn < 1.0:
        bd.asks = {ask_dn: _depth(ask_dn)}
    return bu, bd


def replay(strategy_name, config, ticks, outcomes, bar_seconds):
    engine = create_engine(strategy_name, config, bar_seconds)
    sk = config.get("fill_simulator", {})
    sim = LimitOrderSimulator(
        fill_ticks=sk.get("fill_ticks", 1),
        chase_threshold=sk.get("chase_threshold", 0.03),
        max_chase=sk.get("max_chase", 2),
        spread_offset=sk.get("spread_offset", 0.01),
        cancel_distance=sk.get("cancel_distance", 0.05),
    )
    summaries = []
    cur_bar = None
    for tick in ticks:
        bar_id = tick.get("bar_id", 0)
        if not tick.get("has_book", False):
            continue
        if bar_id != cur_bar:
            if cur_bar is not None:
                for c in sim.cancel_all():
                    engine.on_order_cancelled(c)
                outcome = outcomes.get(cur_bar, "")
                s = engine.resolve(outcome)
                if outcome:
                    s.compute_pnl(outcome)
                if s.cost.get("total", 0) > 0:
                    summaries.append(s)
            engine.reset()
            sim = LimitOrderSimulator(
                fill_ticks=sk.get("fill_ticks", 1),
                chase_threshold=sk.get("chase_threshold", 0.03),
                max_chase=sk.get("max_chase", 2),
                spread_offset=sk.get("spread_offset", 0.01),
                cancel_distance=sk.get("cancel_distance", 0.05),
            )
            engine.set_bar_info(bar_id, "", "", "")
            cur_bar = bar_id
        bu, bd = tick_to_books(tick)
        tp = tick.get("time_pct", 0)
        cp = tick.get("cal_prob", 0.5)
        orders = engine.on_tick(tp, cp, bu, bd)
        if engine.flip_killed and not orders:
            for c in sim.cancel_all():
                engine.on_order_cancelled(c)
        for o in orders:
            sim.place(o)
        for f in sim.on_tick(tp, bu, bd):
            engine.on_fill(f.order, f.fill_price, f.filled_shares)
    if cur_bar is not None:
        for c in sim.cancel_all():
            engine.on_order_cancelled(c)
        outcome = outcomes.get(cur_bar, "")
        s = engine.resolve(outcome)
        if outcome:
            s.compute_pnl(outcome)
        if s.cost.get("total", 0) > 0:
            summaries.append(s)
    return summaries


# Current live Dutch knob configs (matching what's deployed)
DUTCH_CONFIGS = {
    "BTC_5m": {"max_marginal_pair_cost": 1.02, "risk_ceil": 0.20, "risk_t_start": 0.05, "max_onesided_cost": 10.0, "min_unmatched_shares": 5.0, "unmatched_ratio": 0.15},
    "ETH_5m": {"max_marginal_pair_cost": 1.02, "risk_ceil": 0.20, "risk_t_start": 0.05, "max_onesided_cost": 10.0, "min_unmatched_shares": 5.0, "unmatched_ratio": 0.15},
    "SOL_5m": {"max_marginal_pair_cost": 1.02, "risk_ceil": 0.20, "risk_t_start": 0.05, "max_onesided_cost": 8.0, "min_unmatched_shares": 5.0, "unmatched_ratio": 0.15},
    "XRP_5m": {"max_marginal_pair_cost": 1.02, "risk_ceil": 0.20, "risk_t_start": 0.05, "max_onesided_cost": 8.0, "min_unmatched_shares": 5.0, "unmatched_ratio": 0.15},
    "BTC_15m": {"max_marginal_pair_cost": 1.02, "risk_ceil": 0.25, "risk_t_start": 0.05, "max_onesided_cost": 20.0, "min_unmatched_shares": 8.0, "unmatched_ratio": 0.20},
    "ETH_15m": {"max_marginal_pair_cost": 1.02, "risk_ceil": 0.25, "risk_t_start": 0.05, "max_onesided_cost": 20.0, "min_unmatched_shares": 8.0, "unmatched_ratio": 0.20},
    "SOL_15m": {"max_marginal_pair_cost": 1.02, "risk_ceil": 0.25, "risk_t_start": 0.05, "max_onesided_cost": 20.0, "conviction_buy_skip": 0.60, "min_unmatched_shares": 5.0, "unmatched_ratio": 0.15},
    "XRP_15m": {"max_marginal_pair_cost": 1.02, "risk_ceil": 0.25, "risk_t_start": 0.05, "max_onesided_cost": 20.0, "conviction_buy_skip": 0.60, "min_unmatched_shares": 5.0, "unmatched_ratio": 0.15},
    "BTC_1h": {"max_marginal_pair_cost": 1.02, "risk_ceil": 0.25, "risk_t_start": 0.05, "max_onesided_cost": 20.0},
    "ETH_1h": {"max_marginal_pair_cost": 1.015, "risk_ceil": 0.25, "risk_t_start": 0.05, "max_onesided_cost": 20.0},
    "SOL_1h": {"max_marginal_pair_cost": 1.02, "risk_ceil": 0.25, "risk_t_start": 0.05, "max_onesided_cost": 20.0, "conviction_buy_skip": 0.60},
    "XRP_1h": {"max_marginal_pair_cost": 1.02, "risk_ceil": 0.25, "risk_t_start": 0.05, "max_onesided_cost": 20.0, "conviction_buy_skip": 0.60},
}
DIV_CONFIG = {"min_edge": 0.03, "kelly_fraction": 0.25, "order_size": 5.0}


def main():
    tick_dir = Path("data/dutch_paper")

    print("=" * 90)
    print("  LIVE vs BACKTEST COMPARISON (same tick data, same time range)")
    print("=" * 90)
    print(
        f"  {'Pair':<12s} {'LIVE PnL':>10s} {'BT Dutch':>10s} {'BT Diverg':>10s} "
        f"{'Live/BT':>8s} {'Div WR%':>8s} {'Div PF':>7s} {'L Bars':>7s} {'D Bars':>7s} {'Dv Bars':>7s}"
    )
    print("-" * 90)

    total_live = 0
    total_bt_dutch = 0
    total_bt_div = 0

    for tf in ["5m", "15m", "1h"]:
        for asset in ["BTC", "ETH", "SOL", "XRP"]:
            pair = f"{asset}_{tf}"
            bs = BAR_SECS[tf]

            ticks = []
            outcomes = {}
            for f in sorted((tick_dir / pair).glob("ticks_*.jsonl")):
                with open(f) as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            ticks.append(json.loads(line))
                        except Exception:
                            pass
            for f in sorted((tick_dir / pair).glob("bars_*.jsonl")):
                with open(f) as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            b = json.loads(line)
                            if b.get("bar_id") and b.get("outcome"):
                                outcomes[b["bar_id"]] = b["outcome"]
                        except Exception:
                            pass

            # Live PnL
            live_pnl = 0
            live_bars = 0
            for f in sorted((tick_dir / pair).glob("bars_*.jsonl")):
                with open(f) as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            b = json.loads(line)
                            live_pnl += b.get("pnl", {}).get("profit", 0)
                            live_bars += 1
                        except Exception:
                            pass

            # Backtest Dutch
            dc = dict(DUTCH_CONFIGS.get(pair, {}))
            d_sums = replay("dutch", dc, ticks, outcomes, bs)
            bt_dutch_pnl = sum(s.pnl.get("profit", 0) for s in d_sums if s.pnl)

            # Backtest Divergence
            dv_sums = replay("divergence", dict(DIV_CONFIG), ticks, outcomes, bs)
            bt_div_pnl = sum(s.pnl.get("profit", 0) for s in dv_sums if s.pnl)

            # Divergence metrics
            div_profits = [s.pnl.get("profit", 0) for s in dv_sums if s.pnl]
            div_wins = sum(1 for p in div_profits if p > 0)
            div_wr = (div_wins / len(div_profits) * 100) if div_profits else 0
            div_gross_win = sum(p for p in div_profits if p > 0)
            div_gross_loss = sum(p for p in div_profits if p < 0)
            div_pf = abs(div_gross_win / div_gross_loss) if div_gross_loss else 99.9

            # Live vs BT ratio
            ratio = f"{live_pnl / bt_dutch_pnl:.2f}x" if bt_dutch_pnl != 0 else "-"

            s1 = "+" if live_pnl >= 0 else ""
            s2 = "+" if bt_dutch_pnl >= 0 else ""
            s3 = "+" if bt_div_pnl >= 0 else ""
            print(
                f"  {pair:<12s} {s1}${live_pnl:>8.2f} {s2}${bt_dutch_pnl:>8.2f} {s3}${bt_div_pnl:>8.2f} "
                f"{ratio:>8s} {div_wr:>6.1f}% {div_pf:>6.2f} "
                f"{live_bars:>7d} {len(d_sums):>7d} {len(dv_sums):>7d}"
            )

            total_live += live_pnl
            total_bt_dutch += bt_dutch_pnl
            total_bt_div += bt_div_pnl

        print()

    print("=" * 90)
    s1 = "+" if total_live >= 0 else ""
    s2 = "+" if total_bt_dutch >= 0 else ""
    s3 = "+" if total_bt_div >= 0 else ""
    print(
        f"  {'TOTAL':<12s} {s1}${total_live:>8.2f} {s2}${total_bt_dutch:>8.2f} {s3}${total_bt_div:>8.2f}"
    )

    print()
    print("NOTES:")
    print("  - LIVE PnL includes config changes mid-run (gates were tightened multiple times)")
    print("  - BT Dutch uses CURRENT deployed knobs (post-Phase-2 calibration)")
    print("  - BT Diverg uses default divergence config (min_edge=0.03, kelly=0.25)")
    print("  - BT uses realistic depth model (5-50 shares scaled by price extremity)")
    print("  - Live/BT ratio shows parity: 1.0x = backtest matches live perfectly")


if __name__ == "__main__":
    main()
