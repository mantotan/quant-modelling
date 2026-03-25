"""Study market microstructure for Dutch accumulation feasibility.

Key questions:
1. How cheap does pair_ask get within bars?
2. Can sequential pairing work (buy cheap side first, wait for other)?
3. What are real Dutch traders likely doing differently?
"""

import polars as pl
import glob
from collections import defaultdict


def analyze_pair_ask_dynamics(settled, pair_name):
    """Analyze pair_ask (ask_up + ask_dn) dynamics within bars."""
    print(f"\n{'=' * 90}")
    print(f"  {pair_name}: {len(settled)} settled bars")
    print(f"{'=' * 90}")

    # Q1: pair_ask at different times
    print("\n  --- Pair ask at different bar times ---")
    for t_pct in [0.05, 0.10, 0.20, 0.30, 0.50, 0.70, 0.90]:
        pair_asks = []
        for b, outcome in settled:
            au, ad = b["ask_up"], b["ask_dn"]
            idx = int(t_pct * len(au))
            if idx < len(au):
                pair_asks.append(au[idx] + ad[idx])
        if not pair_asks:
            continue
        n = len(pair_asks)
        avg = sum(pair_asks) / n
        b90 = sum(1 for p in pair_asks if p < 0.90) / n * 100
        b95 = sum(1 for p in pair_asks if p < 0.95) / n * 100
        b100 = sum(1 for p in pair_asks if p < 1.00) / n * 100
        print(f"    t={t_pct:.0%}: avg={avg:.3f}  <0.90={b90:.0f}%  <0.95={b95:.0f}%  <1.00={b100:.0f}%")

    # Q2: minimum pair_ask per bar
    print("\n  --- Minimum pair_ask per bar (best Dutch moment) ---")
    min_pas = []
    min_times = []
    for b, outcome in settled:
        au, ad = b["ask_up"], b["ask_dn"]
        n = len(au)
        best_pa = 2.0
        best_t = 0
        for i in range(n):
            pa = au[i] + ad[i]
            if pa < best_pa:
                best_pa = pa
                best_t = i / n
        min_pas.append(best_pa)
        min_times.append(best_t)

    n = len(min_pas)
    print(f"    Avg min pair_ask: {sum(min_pas)/n:.3f}")
    print(f"    Median: {sorted(min_pas)[n//2]:.3f}")
    for thresh in [0.70, 0.80, 0.85, 0.90, 0.95, 1.00]:
        ct = sum(1 for p in min_pas if p < thresh)
        print(f"    < {thresh}: {ct}/{n} ({ct/n*100:.0f}%)")
    print(f"    Avg time of min: {sum(min_times)/n:.2f} of bar")

    # Q3: How long does pair_ask stay below thresholds?
    print("\n  --- Duration pair_ask stays below threshold (% of bar) ---")
    for thresh in [0.90, 0.95, 1.00]:
        durations = []
        for b, outcome in settled:
            au, ad = b["ask_up"], b["ask_dn"]
            n_ticks = len(au)
            below = sum(1 for i in range(n_ticks) if au[i] + ad[i] < thresh)
            durations.append(below / n_ticks * 100)
        avg_dur = sum(durations) / len(durations)
        never = sum(1 for d in durations if d == 0)
        print(f"    < {thresh}: avg {avg_dur:.1f}% of bar, never={never}/{len(durations)}")

    return min_pas


def analyze_sequential_pairing(settled, pair_name):
    """Simulate sequential pairing: buy cheap side, wait for other."""
    print(f"\n  --- Sequential Pairing Strategy ---")

    results = []
    for b, outcome in settled:
        au, ad = b["ask_up"], b["ask_dn"]
        bu, bd = b["bid_up"], b["bid_dn"]
        n = len(au)

        first_fill = None  # (side, price, idx)
        completed = False

        for i in range(n):
            pair_ask = au[i] + ad[i]

            # If pair is already cheap, instant pair
            if pair_ask < 0.92 and first_fill is None:
                results.append({
                    "mode": "instant",
                    "pair_cost": pair_ask,
                    "up_price": au[i],
                    "dn_price": ad[i],
                    "outcome": outcome,
                    "fill_time": i / n,
                })
                completed = True
                break

            # Buy the cheaper side if < 0.42 (potential pair with other at 0.50)
            if first_fill is None:
                if au[i] < 0.42:
                    first_fill = ("UP", au[i], i)
                elif ad[i] < 0.42:
                    first_fill = ("DN", ad[i], i)

            # If we have one side, look for the other to complete pair
            if first_fill is not None and not completed:
                side, price, fill_idx = first_fill
                if side == "UP":
                    other_price = ad[i]
                else:
                    other_price = au[i]

                if price + other_price < 0.95:
                    results.append({
                        "mode": "sequential",
                        "pair_cost": price + other_price,
                        "first_side": side,
                        "first_price": price,
                        "second_price": other_price,
                        "outcome": outcome,
                        "wait_ticks": i - fill_idx,
                        "fill_time": fill_idx / n,
                    })
                    completed = True
                    break

        if not completed:
            if first_fill is not None:
                side, price, _ = first_fill
                results.append({
                    "mode": "one_sided",
                    "first_side": side,
                    "first_price": price,
                    "outcome": outcome,
                })
            else:
                results.append({"mode": "no_trade", "outcome": outcome})

    # Summarize
    instant = [r for r in results if r["mode"] == "instant"]
    sequential = [r for r in results if r["mode"] == "sequential"]
    one_sided = [r for r in results if r["mode"] == "one_sided"]
    no_trade = [r for r in results if r["mode"] == "no_trade"]
    total = len(settled)

    print(f"    Instant pairs: {len(instant)}/{total} ({len(instant)/total*100:.0f}%)")
    print(f"    Sequential pairs: {len(sequential)}/{total} ({len(sequential)/total*100:.0f}%)")
    print(f"    One-sided (failed): {len(one_sided)}/{total} ({len(one_sided)/total*100:.0f}%)")
    print(f"    No trade: {len(no_trade)}/{total} ({len(no_trade)/total*100:.0f}%)")

    # P&L
    total_pnl = 0.0
    shares = 5.0  # $5 per side

    if instant:
        pnl = sum(shares * (1.0 - r["pair_cost"]) for r in instant)
        avg_pc = sum(r["pair_cost"] for r in instant) / len(instant)
        total_pnl += pnl
        print(f"    Instant: avg_pc={avg_pc:.3f}, PnL=${pnl:+.1f}")

    if sequential:
        pnl = sum(shares * (1.0 - r["pair_cost"]) for r in sequential)
        avg_pc = sum(r["pair_cost"] for r in sequential) / len(sequential)
        avg_wait = sum(r["wait_ticks"] for r in sequential) / len(sequential)
        total_pnl += pnl
        print(f"    Sequential: avg_pc={avg_pc:.3f}, wait={avg_wait:.0f} ticks, PnL=${pnl:+.1f}")

    if one_sided:
        pnl = 0
        correct = 0
        for r in one_sided:
            is_correct = (
                (r["first_side"] == "UP" and r["outcome"] == "UP")
                or (r["first_side"] == "DN" and r["outcome"] == "DN")
            )
            if is_correct:
                pnl += shares / r["first_price"] - shares  # pays $1/share
                correct += 1
            else:
                pnl -= shares  # worthless
        total_pnl += pnl
        print(f"    One-sided: correct={correct}/{len(one_sided)} ({correct/len(one_sided)*100:.0f}%), PnL=${pnl:+.1f}")

    avg_pnl = total_pnl / total if total > 0 else 0
    print(f"    TOTAL: ${total_pnl:+.1f} (${avg_pnl:+.2f}/bar)")

    return total_pnl


def analyze_selective_dutch(settled, pair_name):
    """What if we ONLY trade bars where pair_ask starts cheap?"""
    print(f"\n  --- Selective Dutch (only trade when pair_ask < threshold) ---")

    for entry_thresh in [0.90, 0.92, 0.95, 0.98]:
        traded = 0
        paired = 0
        pair_pnl = 0
        skip_pnl = 0  # what we'd make directionally on skipped bars

        for b, outcome in settled:
            au, ad = b["ask_up"], b["ask_dn"]
            n = len(au)

            # Check opening pair_ask
            open_pa = au[0] + ad[0]
            if open_pa >= entry_thresh:
                continue  # skip this bar

            traded += 1

            # Find best moment to buy both
            best_pa = 2.0
            best_i = 0
            for i in range(n // 2):  # only look in first half
                pa = au[i] + ad[i]
                if pa < best_pa:
                    best_pa = pa
                    best_i = i

            if best_pa < entry_thresh:
                paired += 1
                pair_pnl += 5.0 * (1.0 - best_pa)

        if traded > 0:
            wr = paired / traded * 100
            avg = pair_pnl / traded
            print(
                f"    entry<{entry_thresh}: traded={traded}/{len(settled)} "
                f"paired={paired} ({wr:.0f}%) "
                f"PnL=${pair_pnl:+.1f} (${avg:+.2f}/bar)"
            )
        else:
            print(f"    entry<{entry_thresh}: 0 bars qualify")


def analyze_adverse_selection(settled, pair_name):
    """The key question: when one side is cheap, is it because it's losing?"""
    print(f"\n  --- Adverse Selection Analysis ---")
    print(f"    When UP is cheapest (ask_up < ask_dn), what's the outcome?")

    up_cheap_up_wins = 0
    up_cheap_dn_wins = 0
    dn_cheap_up_wins = 0
    dn_cheap_dn_wins = 0

    # Check at different bar times
    for t_pct in [0.10, 0.30, 0.50]:
        up_cheap_wins = 0
        dn_cheap_wins = 0
        total = 0

        for b, outcome in settled:
            au, ad = b["ask_up"], b["ask_dn"]
            idx = int(t_pct * len(au))
            if idx >= len(au):
                continue
            total += 1

            up_cheaper = au[idx] < ad[idx]

            if up_cheaper:
                if outcome == "UP":
                    up_cheap_wins += 1
            else:
                if outcome == "DN":
                    dn_cheap_wins += 1

        cheap_correct = up_cheap_wins + dn_cheap_wins
        print(
            f"    t={t_pct:.0%}: cheap side wins {cheap_correct}/{total} "
            f"({cheap_correct/total*100:.1f}%) — "
            f"{'ADVERSE' if cheap_correct/total < 0.50 else 'FAVORABLE'}"
        )


def main():
    print("=" * 90)
    print("  DUTCH ACCUMULATION MICROSTRUCTURE STUDY")
    print("  Why do real traders profit? What are we missing?")
    print("=" * 90)

    grand_seq_pnl = 0
    grand_bars = 0

    for asset in ["BTC", "ETH", "SOL", "XRP"]:
        for tf in ["5m", "15m", "1h"]:
            pair = f"{asset}_{tf}"
            files = sorted(glob.glob(
                f"data/raw/polymarket_ticks/asset={asset}/timeframe={tf}/**/*.parquet",
                recursive=True,
            ))
            if not files:
                continue

            df = pl.read_parquet(files)
            bars = (
                df.group_by("window_start")
                .agg([
                    pl.col("ts"),
                    pl.col("ask_up"),
                    pl.col("ask_dn"),
                    pl.col("bid_up"),
                    pl.col("bid_dn"),
                ])
                .sort("window_start")
                .to_dicts()
            )

            settled = [
                (b, "UP" if b["ask_up"][-1] >= 0.90 else "DN")
                for b in bars
                if len(b["ask_up"]) >= 20
                and (b["ask_up"][-1] <= 0.10 or b["ask_up"][-1] >= 0.90)
            ]

            if len(settled) < 10:
                continue

            analyze_pair_ask_dynamics(settled, pair)
            analyze_adverse_selection(settled, pair)
            pnl = analyze_sequential_pairing(settled, pair)
            analyze_selective_dutch(settled, pair)

            grand_seq_pnl += pnl
            grand_bars += len(settled)

    print(f"\n{'=' * 90}")
    print(f"  GRAND TOTAL: Sequential pairing PnL=${grand_seq_pnl:+.1f} across {grand_bars} bars (${grand_seq_pnl/grand_bars:+.2f}/bar)")
    print(f"{'=' * 90}")


if __name__ == "__main__":
    main()
