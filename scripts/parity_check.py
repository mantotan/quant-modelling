"""Exact parity check: backtest only on bars that live paper trading processed."""

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


def tick_to_books(t):
    bid_up, ask_up = t.get("bid_up", 0.01), t.get("ask_up", 0.99)
    bid_dn, ask_dn = t.get("bid_dn", 0.01), t.get("ask_dn", 0.99)
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


def replay_divergence(ticks, outcomes, bar_seconds, only_bar_ids=None):
    config = {
        "min_edge": 0.03, "kelly_fraction": 0.25,
        "order_size": 5.0, "min_buy_price": 0.02,
    }
    engine = create_engine("divergence", config, bar_seconds)
    sim = LimitOrderSimulator(
        fill_ticks=1, chase_threshold=0.03, max_chase=2,
        spread_offset=0.01, cancel_distance=0.05,
    )
    summaries = {}
    cur_bar = None
    for tick in ticks:
        bar_id = tick.get("bar_id", 0)
        if only_bar_ids and bar_id not in only_bar_ids:
            continue
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
                if s.cost.get("total", 0) != 0 or len(s.orders) > 0:
                    summaries[cur_bar] = s
            engine.reset()
            sim = LimitOrderSimulator(
                fill_ticks=1, chase_threshold=0.03, max_chase=2,
                spread_offset=0.01, cancel_distance=0.05,
            )
            engine.set_bar_info(bar_id, "", "", "")
            cur_bar = bar_id
        bu, bd = tick_to_books(tick)
        orders = engine.on_tick(tick.get("time_pct", 0), tick.get("cal_prob", 0.5), bu, bd)
        if engine.flip_killed and not orders:
            for c in sim.cancel_all():
                engine.on_order_cancelled(c)
        for o in orders:
            sim.place(o)
        for f in sim.on_tick(tick.get("time_pct", 0), bu, bd):
            engine.on_fill(f.order, f.fill_price, f.filled_shares)
    if cur_bar is not None:
        for c in sim.cancel_all():
            engine.on_order_cancelled(c)
        outcome = outcomes.get(cur_bar, "")
        s = engine.resolve(outcome)
        if outcome:
            s.compute_pnl(outcome)
        if s.cost.get("total", 0) != 0 or len(s.orders) > 0:
            summaries[cur_bar] = s
    return summaries


def main():
    tick_dir = Path("data/dutch_paper")

    print("=" * 120)
    print("EXACT PARITY: Backtest only on bars that live paper trading processed")
    print("=" * 120)
    print()
    header = (
        f"{'Pair':<12} {'Live PnL':>10} {'BT PnL':>10} {'Parity':>8} "
        f"{'Live WR':>8} {'BT WR':>8} {'Bars':>6}  Per-bar diff"
    )
    print(header)
    print("-" * 100)

    total_live = 0
    total_bt = 0
    total_bars = 0
    match_count = 0
    mismatch_count = 0

    for asset in ["ETH", "SOL", "XRP"]:
        for tf in ["5m", "15m", "1h"]:
            pair = f"{asset}_{tf}"
            bs = BAR_SECS[tf]

            # Load LIVE divergence bars
            live_bars = {}
            for f in sorted(glob.glob(f"data/divergence_paper/{pair}/bars_*.jsonl")):
                with open(f) as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            b = json.loads(line)
                            bid = b.get("bar_id", 0)
                            if bid:
                                live_bars[bid] = b
                        except Exception:
                            pass

            if not live_bars:
                continue

            live_bar_ids = set(live_bars.keys())

            # Load ticks + outcomes
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

            # Backtest ONLY on exact bar_ids
            bt_summaries = replay_divergence(ticks, outcomes, bs, only_bar_ids=live_bar_ids)

            live_pnl = 0
            bt_pnl = 0
            live_wins = 0
            bt_wins = 0
            matched_bars = 0
            bar_diffs = []

            for bid in sorted(live_bar_ids):
                lb = live_bars.get(bid)
                bs_bar = bt_summaries.get(bid)

                lp = lb.get("pnl", {}).get("profit", 0) if lb else 0
                bp = bs_bar.pnl.get("profit", 0) if bs_bar and bs_bar.pnl else 0

                live_pnl += lp
                bt_pnl += bp
                if lp > 0:
                    live_wins += 1
                if bp > 0:
                    bt_wins += 1
                matched_bars += 1

                if (lp > 0) == (bp > 0):
                    match_count += 1
                else:
                    mismatch_count += 1
                bar_diffs.append(lp - bp)

            parity = f"{live_pnl / bt_pnl:.2f}x" if bt_pnl != 0 else "N/A"
            live_wr = f"{live_wins / matched_bars * 100:.0f}%" if matched_bars > 0 else "-"
            bt_wr = f"{bt_wins / matched_bars * 100:.0f}%" if matched_bars > 0 else "-"
            avg_diff = sum(bar_diffs) / len(bar_diffs) if bar_diffs else 0

            s1 = "+" if live_pnl >= 0 else ""
            s2 = "+" if bt_pnl >= 0 else ""
            print(
                f"{pair:<12} {s1}${live_pnl:>8.2f} {s2}${bt_pnl:>8.2f} {parity:>8} "
                f"{live_wr:>8} {bt_wr:>8} {matched_bars:>6}  avg_diff=${avg_diff:>+.2f}/bar"
            )

            total_live += live_pnl
            total_bt += bt_pnl
            total_bars += matched_bars

    print("-" * 100)
    s1 = "+" if total_live >= 0 else ""
    s2 = "+" if total_bt >= 0 else ""
    parity_total = f"{total_live / total_bt:.2f}x" if total_bt != 0 else "N/A"
    print(
        f"{'TOTAL':<12} {s1}${total_live:>8.2f} {s2}${total_bt:>8.2f} {parity_total:>8} "
        f"{'':>8} {'':>8} {total_bars:>6}"
    )
    print()
    total_compared = match_count + mismatch_count
    if total_compared > 0:
        print(f"Direction match (both win or both lose): {match_count}/{total_compared} ({match_count / total_compared * 100:.0f}%)")
        print(f"Direction mismatch: {mismatch_count}/{total_compared} ({mismatch_count / total_compared * 100:.0f}%)")


if __name__ == "__main__":
    main()
