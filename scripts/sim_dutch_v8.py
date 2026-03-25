"""Simulate Dutch V8: pair-cost-targeted bilateral accumulation.

Instead of conviction-based direction betting, place resting orders for BOTH
sides at target prices where pair_cost < target. Model determines the split
between sides, not which side to skip.

Compares V8 (bilateral resting) vs V7 (directional reactive) on raw tick data.
"""

import polars as pl
import glob
import random
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class V8Config:
    """Dutch V8 simulation parameters."""
    target_pair_cost: float = 0.90      # only buy when total < this
    order_size_usd: float = 5.0         # dollars per order attempt
    max_orders_per_side: int = 4        # max resting orders per side per bar
    fallback_time: float = 0.60         # switch to reactive if no fills by this
    fallback_enabled: bool = True       # allow reactive fallback for missing side
    fill_ticks: int = 10                # consecutive ticks for fill
    model_accuracy: float = 0.84        # simulated model accuracy
    split_mode: str = "model"           # "model" or "equal"
    min_price: float = 0.05             # don't place orders below this


@dataclass
class BarResult:
    """Result from simulating one bar."""
    outcome: str = ""
    up_fills: int = 0
    dn_fills: int = 0
    up_shares: float = 0.0
    dn_shares: float = 0.0
    up_cost: float = 0.0
    dn_cost: float = 0.0
    matched: float = 0.0
    pair_cost: float = 0.0
    pnl: float = 0.0
    mode: str = ""  # "paired", "one_sided_win", "one_sided_lose", "no_fill"


def consecutive_fill(prices, limit, start, end, n_ticks=10, sweep=0.01):
    """Check if price stays at/below limit for n consecutive ticks."""
    consec = 0
    for i in range(start, min(end, len(prices))):
        if prices[i] <= limit:
            consec += 1
            if (limit - prices[i]) >= sweep:
                return i  # sweep fill
            if consec >= n_ticks:
                return i
        else:
            consec = 0
    return -1


def simulate_v8_bar(asks_up, asks_dn, bids_up, bids_dn, outcome,
                     model_prob, cfg: V8Config):
    """Simulate one bar with V8 pair-cost targeting."""
    n = len(asks_up)
    if n < 20:
        return BarResult(outcome=outcome, mode="no_fill")

    result = BarResult(outcome=outcome)

    # Compute target prices based on model and target pair_cost
    if cfg.split_mode == "model":
        # Model-weighted split: allocate more of the budget to favored side
        p_up = max(0.1, min(0.9, model_prob))
        p_dn = 1.0 - p_up
        target_up = cfg.target_pair_cost * p_up / (p_up + p_dn)  # simplified: just p_up * target
        target_dn = cfg.target_pair_cost - target_up
    else:
        # Equal split
        target_up = cfg.target_pair_cost / 2
        target_dn = cfg.target_pair_cost / 2

    target_up = max(cfg.min_price, min(target_up, 0.95))
    target_dn = max(cfg.min_price, min(target_dn, 0.95))

    # Phase 1: Place resting orders at target prices for BOTH sides
    # Try multiple order times spread across the bar
    order_times = [0.05, 0.15, 0.30, 0.45]
    shares_per_order = cfg.order_size_usd  # ~$5 per order

    up_filled_shares = 0.0
    up_filled_cost = 0.0
    dn_filled_shares = 0.0
    dn_filled_cost = 0.0
    up_fills = 0
    dn_fills = 0

    for i, t in enumerate(order_times):
        if i >= cfg.max_orders_per_side:
            break
        idx = int(t * n)
        if idx >= n:
            continue

        # UP resting order at target_up
        if up_fills < cfg.max_orders_per_side:
            # Adjust target based on current market — don't place above current ask
            eff_target_up = min(target_up, asks_up[idx] - 0.01) if asks_up[idx] > target_up else target_up
            if eff_target_up >= cfg.min_price:
                fill_idx = consecutive_fill(asks_up, eff_target_up, idx, n, cfg.fill_ticks)
                if fill_idx >= 0:
                    shares = shares_per_order / eff_target_up
                    up_filled_shares += shares
                    up_filled_cost += shares * eff_target_up
                    up_fills += 1

        # DN resting order at target_dn
        if dn_fills < cfg.max_orders_per_side:
            eff_target_dn = min(target_dn, asks_dn[idx] - 0.01) if asks_dn[idx] > target_dn else target_dn
            if eff_target_dn >= cfg.min_price:
                fill_idx = consecutive_fill(asks_dn, eff_target_dn, idx, n, cfg.fill_ticks)
                if fill_idx >= 0:
                    shares = shares_per_order / eff_target_dn
                    dn_filled_shares += shares
                    dn_filled_cost += shares * eff_target_dn
                    dn_fills += 1

    # Phase 2: Fallback — if only one side filled by fallback_time, try reactive on other
    if cfg.fallback_enabled:
        fb_idx = int(cfg.fallback_time * n)
        if up_fills > 0 and dn_fills == 0 and fb_idx < n:
            # Try reactive DN at current bid
            bid_dn = bids_dn[fb_idx]
            if bid_dn > cfg.min_price and (up_filled_cost / up_filled_shares + bid_dn) < cfg.target_pair_cost * 1.05:
                fill_idx = consecutive_fill(asks_dn, bid_dn, fb_idx, min(fb_idx + 30, n), cfg.fill_ticks)
                if fill_idx >= 0:
                    shares = shares_per_order / bid_dn
                    dn_filled_shares += shares
                    dn_filled_cost += shares * bid_dn
                    dn_fills += 1

        elif dn_fills > 0 and up_fills == 0 and fb_idx < n:
            bid_up = bids_up[fb_idx]
            if bid_up > cfg.min_price and (dn_filled_cost / dn_filled_shares + bid_up) < cfg.target_pair_cost * 1.05:
                fill_idx = consecutive_fill(asks_up, bid_up, fb_idx, min(fb_idx + 30, n), cfg.fill_ticks)
                if fill_idx >= 0:
                    shares = shares_per_order / bid_up
                    up_filled_shares += shares
                    up_filled_cost += shares * bid_up
                    up_fills += 1

    # Compute results
    result.up_fills = up_fills
    result.dn_fills = dn_fills
    result.up_shares = up_filled_shares
    result.dn_shares = dn_filled_shares
    result.up_cost = up_filled_cost
    result.dn_cost = dn_filled_cost

    total_cost = up_filled_cost + dn_filled_cost

    if up_fills > 0 and dn_fills > 0:
        # Paired — compute pair cost
        matched = min(up_filled_shares, dn_filled_shares)
        result.matched = matched
        avg_up = up_filled_cost / up_filled_shares
        avg_dn = dn_filled_cost / dn_filled_shares
        result.pair_cost = avg_up + avg_dn

        # PnL: matched pairs pay $1 per share, unmatched pay $1 if correct else $0
        matched_pnl = matched * (1.0 - result.pair_cost)
        unmatched_up = up_filled_shares - matched
        unmatched_dn = dn_filled_shares - matched
        if outcome == "UP":
            unmatched_pnl = unmatched_up * (1.0 - avg_up) - unmatched_dn * avg_dn
        else:
            unmatched_pnl = unmatched_dn * (1.0 - avg_dn) - unmatched_up * avg_up
        result.pnl = matched_pnl + unmatched_pnl
        result.mode = "paired"

    elif up_fills > 0:
        # One-sided UP
        if outcome == "UP":
            result.pnl = up_filled_shares - up_filled_cost
            result.mode = "one_sided_win"
        else:
            result.pnl = -up_filled_cost
            result.mode = "one_sided_lose"

    elif dn_fills > 0:
        # One-sided DN
        if outcome == "DN":
            result.pnl = dn_filled_shares - dn_filled_cost
            result.mode = "one_sided_win"
        else:
            result.pnl = -dn_filled_cost
            result.mode = "one_sided_lose"

    else:
        result.mode = "no_fill"

    return result


def simulate_v7_bar(asks_up, asks_dn, bids_up, bids_dn, outcome,
                     model_prob, model_correct, cfg: V8Config):
    """Simulate current V7 directional approach for comparison."""
    n = len(asks_up)
    if n < 20:
        return BarResult(outcome=outcome, mode="no_fill")

    result = BarResult(outcome=outcome)

    # V7: buy model-favored side at bid (reactive)
    model_says_up = model_prob > 0.5
    order_times = [0.10, 0.25, 0.45, 0.65]
    total_cost = 0.0
    total_shares = 0.0
    fills = 0

    for t in order_times:
        idx = int(t * n)
        if idx >= n:
            continue

        if model_says_up:
            bid = bids_up[idx]
            asks = asks_up
        else:
            bid = bids_dn[idx]
            asks = asks_dn

        if bid <= 0.01:
            continue

        fill_idx = consecutive_fill(asks, bid, idx, min(idx + 30, n), cfg.fill_ticks)
        if fill_idx >= 0:
            shares = cfg.order_size_usd / bid
            total_cost += shares * bid
            total_shares += shares
            fills += 1

    if fills == 0:
        result.mode = "no_fill"
        return result

    if model_says_up:
        result.up_fills = fills
        result.up_shares = total_shares
        result.up_cost = total_cost
        if outcome == "UP":
            result.pnl = total_shares - total_cost
            result.mode = "one_sided_win"
        else:
            result.pnl = -total_cost
            result.mode = "one_sided_lose"
    else:
        result.dn_fills = fills
        result.dn_shares = total_shares
        result.dn_cost = total_cost
        if outcome == "DN":
            result.pnl = total_shares - total_cost
            result.mode = "one_sided_win"
        else:
            result.pnl = -total_cost
            result.mode = "one_sided_lose"

    return result


def run_simulation():
    """Run V8 vs V7 simulation across all pairs."""
    random.seed(42)

    print("=" * 100)
    print("  DUTCH V8 SIMULATION: Pair-Cost Targeted Bilateral vs V7 Directional")
    print("=" * 100)

    # Test different target pair costs
    configs = [
        ("V8 target=0.85", V8Config(target_pair_cost=0.85, fill_ticks=10)),
        ("V8 target=0.90", V8Config(target_pair_cost=0.90, fill_ticks=10)),
        ("V8 target=0.92", V8Config(target_pair_cost=0.92, fill_ticks=10)),
        ("V8 target=0.95", V8Config(target_pair_cost=0.95, fill_ticks=10)),
        ("V8 t=0.90 ft=1", V8Config(target_pair_cost=0.90, fill_ticks=1)),
        ("V8 t=0.92 ft=1", V8Config(target_pair_cost=0.92, fill_ticks=1)),
        ("V8 equal split", V8Config(target_pair_cost=0.90, split_mode="equal", fill_ticks=10)),
        ("V7 directional", V8Config()),  # placeholder, uses v7 sim
    ]

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
            bars = df.group_by("window_start").agg([
                pl.col("ts"),
                pl.col("ask_up"), pl.col("ask_dn"),
                pl.col("bid_up"), pl.col("bid_dn"),
            ]).sort("window_start").to_dicts()

            # Filter to settled bars
            settled = []
            for b in bars:
                au, ad = b["ask_up"], b["ask_dn"]
                if len(au) < 20:
                    continue
                final_up = au[-1]
                if final_up <= 0.10:
                    settled.append((b, "DN"))
                elif final_up >= 0.90:
                    settled.append((b, "UP"))

            if len(settled) < 5:
                continue

            print(f"\n{'=' * 100}")
            print(f"  {pair}: {len(settled)} settled bars")
            print(f"{'=' * 100}")
            header = (
                f"  {'Strategy':22s} {'PnL':>8s} {'$/bar':>7s} {'WR':>6s} "
                f"{'Paired':>7s} {'1sWin':>6s} {'1sLose':>7s} {'NoFill':>7s} "
                f"{'AvgPC':>7s} {'Match%':>7s} {'Volume':>8s} {'Fills':>6s}"
            )
            print(header)
            print("  " + "-" * 98)

            for cfg_name, cfg in configs:
                random.seed(42)  # reset for each config
                results = []

                for bar_data, outcome in settled:
                    au = bar_data["ask_up"]
                    ad = bar_data["ask_dn"]
                    bu = bar_data["bid_up"]
                    bd = bar_data["bid_dn"]

                    # Simulate model prediction
                    actual_up = outcome == "UP"
                    correct = random.random() < cfg.model_accuracy
                    model_prob = (
                        0.5 + random.uniform(0.05, 0.35)
                        if (actual_up == correct) or (not actual_up and not correct)
                        else 0.5 - random.uniform(0.05, 0.35)
                    )
                    # Clamp
                    if correct:
                        model_prob = model_prob if actual_up else 1.0 - model_prob
                        model_prob = max(0.55, min(0.90, model_prob)) if actual_up else min(0.45, max(0.10, model_prob))
                    else:
                        model_prob = model_prob if not actual_up else 1.0 - model_prob
                        model_prob = max(0.55, min(0.90, model_prob)) if not actual_up else min(0.45, max(0.10, model_prob))

                    if cfg_name == "V7 directional":
                        r = simulate_v7_bar(au, ad, bu, bd, outcome, model_prob, correct, cfg)
                    else:
                        r = simulate_v8_bar(au, ad, bu, bd, outcome, model_prob, cfg)
                    results.append(r)

                # Aggregate
                n = len(results)
                total_pnl = sum(r.pnl for r in results)
                wins = sum(1 for r in results if r.pnl > 0)
                paired = sum(1 for r in results if r.mode == "paired")
                one_win = sum(1 for r in results if r.mode == "one_sided_win")
                one_lose = sum(1 for r in results if r.mode == "one_sided_lose")
                no_fill = sum(1 for r in results if r.mode == "no_fill")
                total_vol = sum(r.up_cost + r.dn_cost for r in results)
                total_fills = sum(r.up_fills + r.dn_fills for r in results)
                paired_results = [r for r in results if r.mode == "paired"]
                avg_pc = (
                    sum(r.pair_cost for r in paired_results) / len(paired_results)
                    if paired_results else 0
                )
                total_matched = sum(r.matched for r in results)
                total_shares = sum(r.up_shares + r.dn_shares for r in results)
                match_pct = total_matched * 2 / total_shares * 100 if total_shares > 0 else 0

                wr = wins / n * 100 if n > 0 else 0
                avg_pnl = total_pnl / n if n > 0 else 0

                print(
                    f"  {cfg_name:22s} {total_pnl:+8.1f} {avg_pnl:+7.2f} {wr:5.1f}% "
                    f"{paired:7d} {one_win:6d} {one_lose:7d} {no_fill:7d} "
                    f"{avg_pc:7.3f} {match_pct:6.1f}% {total_vol:8.0f} {total_fills:6d}"
                )

    # Grand totals across all pairs
    print(f"\n{'=' * 100}")
    print("  GRAND TOTALS (all pairs combined)")
    print(f"{'=' * 100}")

    for cfg_name, cfg in configs:
        random.seed(42)
        grand_pnl = 0
        grand_bars = 0
        grand_paired = 0
        grand_matched = 0
        grand_shares = 0
        grand_vol = 0

        for asset in ["BTC", "ETH", "SOL", "XRP"]:
            for tf in ["5m", "15m", "1h"]:
                files = sorted(glob.glob(
                    f"data/raw/polymarket_ticks/asset={asset}/timeframe={tf}/**/*.parquet",
                    recursive=True,
                ))
                if not files:
                    continue
                df = pl.read_parquet(files)
                bars = df.group_by("window_start").agg([
                    pl.col("ts"), pl.col("ask_up"), pl.col("ask_dn"),
                    pl.col("bid_up"), pl.col("bid_dn"),
                ]).sort("window_start").to_dicts()

                for b in bars:
                    au, ad = b["ask_up"], b["ask_dn"]
                    bu, bd = b["bid_up"], b["bid_dn"]
                    if len(au) < 20:
                        continue
                    final_up = au[-1]
                    if final_up > 0.10 and final_up < 0.90:
                        continue
                    outcome = "UP" if final_up >= 0.90 else "DN"
                    actual_up = outcome == "UP"
                    correct = random.random() < cfg.model_accuracy
                    if correct:
                        model_prob = max(0.55, min(0.90, 0.5 + random.uniform(0.05, 0.35))) if actual_up else min(0.45, max(0.10, 0.5 - random.uniform(0.05, 0.35)))
                    else:
                        model_prob = max(0.55, min(0.90, 0.5 + random.uniform(0.05, 0.35))) if not actual_up else min(0.45, max(0.10, 0.5 - random.uniform(0.05, 0.35)))

                    if cfg_name == "V7 directional":
                        r = simulate_v7_bar(au, ad, bu, bd, outcome, model_prob, correct, cfg)
                    else:
                        r = simulate_v8_bar(au, ad, bu, bd, outcome, model_prob, cfg)

                    grand_pnl += r.pnl
                    grand_bars += 1
                    if r.mode == "paired":
                        grand_paired += 1
                    grand_matched += r.matched
                    grand_shares += r.up_shares + r.dn_shares
                    grand_vol += r.up_cost + r.dn_cost

        match_pct = grand_matched * 2 / grand_shares * 100 if grand_shares > 0 else 0
        avg = grand_pnl / grand_bars if grand_bars > 0 else 0
        print(
            f"  {cfg_name:22s}: PnL={grand_pnl:+8.1f}  $/bar={avg:+.2f}  "
            f"bars={grand_bars}  paired={grand_paired}  match%={match_pct:.1f}%  "
            f"vol=${grand_vol:.0f}"
        )


if __name__ == "__main__":
    run_simulation()
