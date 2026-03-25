"""Generate comprehensive baseline metrics from Dutch backtest bar JSONL data."""

import json
from collections import defaultdict
from pathlib import Path


def analyze_pair(bars_files):
    """Compute detailed metrics from bar JSONL files."""
    bars = []
    for f in sorted(bars_files):
        with open(f) as fh:
            for line in fh:
                bars.append(json.loads(line))

    if not bars:
        return None

    n = len(bars)
    # Extract nested fields
    pnls = [b.get("pnl", {}).get("profit", 0) if isinstance(b.get("pnl"), dict) else b.get("pnl", 0) for b in bars]
    total_pnl = sum(pnls)

    # Win/loss
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    zeros = [p for p in pnls if p == 0]
    win_rate = len(wins) / n * 100 if n > 0 else 0

    # Volume (from cost dict)
    total_cost = sum(
        b.get("cost", {}).get("total", 0) if isinstance(b.get("cost"), dict) else b.get("total_cost", 0)
        for b in bars
    )
    total_fills = sum(
        b.get("fill_stats", {}).get("orders_filled", 0)
        for b in bars
    )

    # Pair cost
    pcs = []
    for b in bars:
        pc = b.get("cost", {}).get("avg_pair_cost", 0) if isinstance(b.get("cost"), dict) else b.get("pair_cost", 0)
        if 0 < pc < 2:
            pcs.append(pc)
    avg_pc = sum(pcs) / len(pcs) if pcs else 0

    # Matched/unmatched (from inventory dict)
    total_matched = sum(
        b.get("inventory", {}).get("matched", 0) if isinstance(b.get("inventory"), dict) else 0
        for b in bars
    )
    total_up = sum(
        b.get("inventory", {}).get("up_shares", 0) if isinstance(b.get("inventory"), dict) else 0
        for b in bars
    )
    total_dn = sum(
        b.get("inventory", {}).get("dn_shares", 0) if isinstance(b.get("inventory"), dict) else 0
        for b in bars
    )
    total_unmatched = (total_up + total_dn) - 2 * total_matched

    # Max drawdown (running PnL)
    cumsum = 0
    peak = 0
    max_dd_amt = 0
    for p in pnls:
        cumsum += p
        if cumsum > peak:
            peak = cumsum
        dd = peak - cumsum
        if dd > max_dd_amt:
            max_dd_amt = dd
    max_dd_pct = max_dd_amt / total_cost * 100 if total_cost > 0 else 0

    # Profit factor
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = gross_win / gross_loss if gross_loss > 0 else float("inf")

    # Avg win/loss
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = sum(losses) / len(losses) if losses else 0

    # Expectancy
    expectancy = total_pnl / n if n > 0 else 0

    # Date range
    dates = sorted(
        set(b.get("window_start", "")[:10] for b in bars if b.get("window_start"))
    )

    # Model accuracy
    model_correct = 0
    model_total = 0
    for b in bars:
        outcome = b.get("outcome", "")
        ms = b.get("model_stats", {})
        avg_prob = ms.get("avg_prob", 0.5) if isinstance(ms, dict) else 0.5
        if outcome:
            model_total += 1
            predicted_up = avg_prob > 0.5
            actual_up = outcome == "UP"
            if predicted_up == actual_up:
                model_correct += 1
    model_acc = model_correct / model_total * 100 if model_total > 0 else 0

    return {
        "bars": n,
        "dates": f"{dates[0]} to {dates[-1]}" if dates else "?",
        "n_days": len(dates),
        "total_pnl": total_pnl,
        "avg_pnl": expectancy,
        "win_rate": win_rate,
        "n_wins": len(wins),
        "n_losses": len(losses),
        "n_zeros": len(zeros),
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": profit_factor,
        "total_volume": total_cost,
        "avg_volume": total_cost / n if n > 0 else 0,
        "total_fills": total_fills,
        "avg_fills": total_fills / n if n > 0 else 0,
        "avg_pair_cost": avg_pc,
        "matched_shares": total_matched,
        "unmatched_shares": total_unmatched,
        "max_dd_amt": max_dd_amt,
        "max_dd_pct": max_dd_pct,
        "model_acc": model_acc,
        "roi_pct": total_pnl / total_cost * 100 if total_cost > 0 else 0,
    }


def main():
    bar_dir = Path("data/dutch_backtest")
    results = {}

    for asset in ["BTC", "ETH", "SOL", "XRP"]:
        for tf in ["5m", "15m", "1h"]:
            pair = f"{asset}_{tf}"
            pair_dir = bar_dir / pair
            if not pair_dir.exists():
                continue
            files = sorted(pair_dir.glob("bars_*.jsonl"))
            if not files:
                continue
            m = analyze_pair(files)
            if m:
                results[pair] = m

    print("=" * 130)
    print("  DUTCH V7.3 BASELINE - COMPREHENSIVE METRICS (ALL 12 PAIRS)")
    print("=" * 130)
    print()

    h = (
        f"{'Pair':10s} {'Bars':>5s} {'Days':>4s} {'TotalPnL':>10s} {'AvgPnL':>8s} "
        f"{'WinRate':>8s} {'W/L/Z':>10s} {'AvgWin':>8s} {'AvgLoss':>8s} {'PF':>5s} "
        f"{'Volume':>8s} {'Fills':>6s} {'PairCost':>9s} {'MaxDD$':>8s} {'MaxDD%':>7s} "
        f"{'ROI%':>6s} {'ModelAcc':>9s}"
    )
    print(h)
    print("-" * 130)

    totals = defaultdict(float)
    all_pairs = [
        "BTC_5m", "BTC_15m", "BTC_1h",
        "ETH_5m", "ETH_15m", "ETH_1h",
        "SOL_5m", "SOL_15m", "SOL_1h",
        "XRP_5m", "XRP_15m", "XRP_1h",
    ]

    for pair in all_pairs:
        if pair not in results:
            print(f"  {pair:10s} - NO DATA")
            continue
        m = results[pair]
        pf_str = f"{m['profit_factor']:.2f}" if m["profit_factor"] < 100 else "inf"
        wlz = f"{m['n_wins']:3d}/{m['n_losses']:3d}/{m['n_zeros']:2d}"
        print(
            f"  {pair:10s} {m['bars']:5d} {m['n_days']:4d} "
            f"{m['total_pnl']:+10.2f} {m['avg_pnl']:+8.2f} "
            f"{m['win_rate']:7.1f}% {wlz:>10s} "
            f"{m['avg_win']:+8.2f} {m['avg_loss']:+8.2f} {pf_str:>5s} "
            f"{m['total_volume']:8.0f} {m['total_fills']:6.0f} "
            f"{m['avg_pair_cost']:9.4f} "
            f"{m['max_dd_amt']:8.2f} {m['max_dd_pct']:6.1f}% "
            f"{m['roi_pct']:+5.1f}% {m['model_acc']:8.1f}%"
        )

        totals["bars"] += m["bars"]
        totals["total_pnl"] += m["total_pnl"]
        totals["n_wins"] += m["n_wins"]
        totals["n_losses"] += m["n_losses"]
        totals["n_zeros"] += m["n_zeros"]
        totals["total_volume"] += m["total_volume"]
        totals["total_fills"] += m["total_fills"]
        totals["matched"] += m["matched_shares"]
        totals["unmatched"] += m["unmatched_shares"]
        totals["max_dd_amt"] = max(totals["max_dd_amt"], m["max_dd_amt"])

    # Asset subtotals
    print("-" * 130)
    for asset in ["BTC", "ETH", "SOL", "XRP"]:
        asset_pairs = [p for p in results if p.startswith(asset)]
        if not asset_pairs:
            continue
        a_bars = sum(results[p]["bars"] for p in asset_pairs)
        a_pnl = sum(results[p]["total_pnl"] for p in asset_pairs)
        a_wins = sum(results[p]["n_wins"] for p in asset_pairs)
        a_losses = sum(results[p]["n_losses"] for p in asset_pairs)
        a_vol = sum(results[p]["total_volume"] for p in asset_pairs)
        a_wr = a_wins / a_bars * 100 if a_bars > 0 else 0
        a_roi = a_pnl / a_vol * 100 if a_vol > 0 else 0
        wlz = f"{a_wins:3d}/{a_losses:3d}    "
        print(
            f"  {asset + '_ALL':10s} {a_bars:5d}      "
            f"{a_pnl:+10.2f} {a_pnl / a_bars:+8.2f} "
            f"{a_wr:7.1f}% {wlz:>10s} "
            f"{'':>8s} {'':>8s} {'':>5s} "
            f"{a_vol:8.0f} {'':>6s} "
            f"{'':>9s} "
            f"{'':>8s} {'':>7s} "
            f"{a_roi:+5.1f}%"
        )

    # Grand total
    print("=" * 130)
    tb = int(totals["bars"])
    tp = totals["total_pnl"]
    tw = int(totals["n_wins"])
    tl = int(totals["n_losses"])
    tz = int(totals["n_zeros"])
    tv = totals["total_volume"]
    wr = tw / tb * 100 if tb > 0 else 0
    roi = tp / tv * 100 if tv > 0 else 0
    wlz = f"{tw:3d}/{tl:3d}/{tz:2d}"
    print(
        f"  {'GRAND':10s} {tb:5d}    2 "
        f"{tp:+10.2f} {tp / tb:+8.2f} "
        f"{wr:7.1f}% {wlz:>10s} "
        f"{'':>8s} {'':>8s} {'':>5s} "
        f"{tv:8.0f} {totals['total_fills']:6.0f} "
        f"{'':>9s} "
        f"{totals['max_dd_amt']:8.2f} {'':>7s} "
        f"{roi:+5.1f}%"
    )

    print()
    print("=" * 130)
    print("  KEY INSIGHTS")
    print("=" * 130)

    best_pair = max(results.items(), key=lambda x: x[1]["total_pnl"])
    worst_pair = min(results.items(), key=lambda x: x[1]["total_pnl"])
    best_wr = max(results.items(), key=lambda x: x[1]["win_rate"])
    best_pf = max(
        results.items(),
        key=lambda x: x[1]["profit_factor"] if x[1]["profit_factor"] < 100 else 0,
    )

    print(f"  Best P&L:           {best_pair[0]} at ${best_pair[1]['total_pnl']:+.2f}")
    print(f"  Worst P&L:          {worst_pair[0]} at ${worst_pair[1]['total_pnl']:+.2f}")
    print(f"  Best Win Rate:      {best_wr[0]} at {best_wr[1]['win_rate']:.1f}%")
    print(f"  Best Profit Factor: {best_pf[0]} at {best_pf[1]['profit_factor']:.2f}")
    print(f"  Total Volume:       ${tv:,.0f} traded across {tb} bars")
    print(f"  Total Matched:      {totals['matched']:.0f} shares paired")
    print(f"  Total Unmatched:    {totals['unmatched']:.0f} shares one-sided")
    print(f"  Duration:           2 days (2026-03-21 to 2026-03-22)")
    print()

    profitable = [p for p, m in results.items() if m["total_pnl"] > 0]
    unprofitable = [p for p, m in results.items() if m["total_pnl"] <= 0]
    print(
        f"  Profitable pairs ({len(profitable)}/12): {', '.join(sorted(profitable))}"
    )
    print(
        f"  Losing pairs ({len(unprofitable)}/12):   {', '.join(sorted(unprofitable))}"
    )

    print()
    print("  Per-asset summary:")
    for asset in ["BTC", "ETH", "SOL", "XRP"]:
        pairs = [p for p in results if p.startswith(asset)]
        pnl = sum(results[p]["total_pnl"] for p in pairs)
        prof = sum(1 for p in pairs if results[p]["total_pnl"] > 0)
        print(f"    {asset}: ${pnl:+.2f} ({prof}/3 profitable)")

    print()
    print("  Per-timeframe summary:")
    for tf in ["5m", "15m", "1h"]:
        pairs = [p for p in results if p.endswith(tf)]
        pnl = sum(results[p]["total_pnl"] for p in pairs)
        prof = sum(1 for p in pairs if results[p]["total_pnl"] > 0)
        avg_wr = sum(results[p]["win_rate"] for p in pairs) / len(pairs)
        print(f"    {tf}: ${pnl:+.2f} ({prof}/4 profitable, avg WR {avg_wr:.1f}%)")


if __name__ == "__main__":
    main()
