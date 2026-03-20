"""Deep analysis of any Polymarket trader's strategy. Reusable for trader_b, trader_a, etc."""
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np


def compute_elapsed_seconds(trade_ts: int, title: str) -> float | None:
    """Compute seconds into the window when this trade was placed."""
    m = re.search(r"(\w+) (\d+),", title)
    if not m:
        return None

    month_name = m.group(1)
    day = int(m.group(2))

    tm = re.search(r"(\d+):(\d+)(AM|PM)-", title)
    if not tm:
        return None

    sh, sm, sampm = int(tm.group(1)), int(tm.group(2)), tm.group(3)
    if sampm == "PM" and sh != 12:
        sh += 12
    if sampm == "AM" and sh == 12:
        sh = 0

    dt = datetime.fromtimestamp(trade_ts, tz=timezone.utc)
    year = dt.year

    months = {"January": 1, "February": 2, "March": 3, "April": 4,
              "May": 5, "June": 6, "July": 7, "August": 8,
              "September": 9, "October": 10, "November": 11, "December": 12}
    month_num = months.get(month_name)
    if not month_num:
        return None

    # EDT = UTC-4
    window_start_et = datetime(year, month_num, day, sh, sm, 0, tzinfo=timezone.utc)
    window_start_utc = window_start_et + timedelta(hours=4)

    elapsed = trade_ts - int(window_start_utc.timestamp())
    return elapsed


def get_window_duration(slug: str) -> int:
    """Get window duration in seconds from slug."""
    if "5m" in slug:
        return 300
    elif "15m" in slug:
        return 900
    elif "1h" in slug:
        return 3600
    return 300


def analyze(name: str, trades: list):
    print(f"{'='*70}")
    print(f"  {name.upper()} STRATEGY ANALYSIS — {len(trades)} total trades")
    print(f"{'='*70}")

    # Categorize trades
    btc_5m = [t for t in trades if "btc-updown-5m" in t.get("slug", "")]
    btc_15m = [t for t in trades if "btc-updown-15m" in t.get("slug", "")]
    crypto_short = [t for t in trades if any(x in t.get("slug", "") for x in [
        "btc-updown-5m", "btc-updown-15m", "eth-updown", "sol-updown",
        "bitcoin-up-or-down", "ethereum-up-or-down", "solana-up-or-down", "xrp-up-or-down",
    ])]

    print(f"\n--- MARKET BREAKDOWN ---")
    market_cats = defaultdict(int)
    for t in trades:
        slug = t.get("slug", "")
        if "btc-updown-5m" in slug: market_cats["BTC 5m"] += 1
        elif "btc-updown-15m" in slug: market_cats["BTC 15m"] += 1
        elif "btc-updown-1h" in slug or "bitcoin-up-or-down" in slug: market_cats["BTC 1h"] += 1
        elif "eth-updown" in slug or "ethereum-up-or-down" in slug: market_cats["ETH"] += 1
        elif "sol-updown" in slug or "solana-up-or-down" in slug: market_cats["SOL"] += 1
        elif "xrp-updown" in slug or "xrp-up-or-down" in slug: market_cats["XRP"] += 1
        else: market_cats["Other"] += 1

    for cat, count in sorted(market_cats.items(), key=lambda x: -x[1]):
        pct = count / len(trades) * 100
        print(f"  {cat:>10}: {count:>6} ({pct:5.1f}%)")

    # Focus on crypto short-term trades
    focus = crypto_short if len(crypto_short) > 100 else trades
    focus_name = "crypto short-term" if len(crypto_short) > 100 else "all"
    print(f"\n--- DETAILED ANALYSIS ON {focus_name.upper()} ({len(focus)} trades) ---")

    # 1. TIMING
    print(f"\n{'='*60}")
    print(f"1. TIMING WITHIN WINDOW")
    print(f"{'='*60}")

    elapsed_list = []
    for t in focus:
        elapsed = compute_elapsed_seconds(int(t["timestamp"]), t.get("title", ""))
        dur = get_window_duration(t.get("slug", ""))
        if elapsed is not None and -30 <= elapsed <= dur + 60:
            elapsed_list.append((elapsed, dur))

    if elapsed_list:
        # Normalize to % of window
        elapsed_pct = np.array([e / d * 100 for e, d in elapsed_list])
        elapsed_sec = np.array([e for e, _ in elapsed_list])

        print(f"Trades with valid timing: {len(elapsed_pct)}")
        print(f"Mean elapsed: {elapsed_sec.mean():.0f}s ({elapsed_pct.mean():.1f}% of window)")
        print(f"Median elapsed: {np.median(elapsed_sec):.0f}s ({np.median(elapsed_pct):.1f}%)")

        buckets_pct = [(0, 10), (10, 20), (20, 30), (30, 40), (40, 50),
                       (50, 60), (60, 70), (70, 80), (80, 90), (90, 100), (100, 120)]
        print(f"\nTime bucket (% of window):")
        for lo, hi in buckets_pct:
            count = np.sum((elapsed_pct >= lo) & (elapsed_pct < hi))
            pct = count / len(elapsed_pct) * 100
            bar = "#" * int(pct / 2)
            print(f"  {lo:>3}-{hi:>3}%: {count:>5} ({pct:5.1f}%) {bar}")

    # 2. PRICE
    print(f"\n{'='*60}")
    print(f"2. PRICE DISTRIBUTION")
    print(f"{'='*60}")

    prices = np.array([float(t["price"]) for t in focus])
    sides = [t.get("side", "") for t in focus]

    buy_prices = np.array([float(t["price"]) for t in focus if t.get("side") == "BUY"])
    sell_prices = np.array([float(t["price"]) for t in focus if t.get("side") == "SELL"])

    print(f"Overall: mean={prices.mean():.3f}, median={np.median(prices):.3f}")
    if len(buy_prices) > 0:
        print(f"BUY:     mean={buy_prices.mean():.3f}, median={np.median(buy_prices):.3f}, n={len(buy_prices)}")
    if len(sell_prices) > 0:
        print(f"SELL:    mean={sell_prices.mean():.3f}, median={np.median(sell_prices):.3f}, n={len(sell_prices)}")

    price_buckets = [(0, 0.1), (0.1, 0.2), (0.2, 0.3), (0.3, 0.4), (0.4, 0.5),
                     (0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.0)]
    print(f"\nPrice distribution:")
    for lo, hi in price_buckets:
        count = np.sum((prices >= lo) & (prices < hi))
        pct = count / len(prices) * 100
        bar = "#" * int(pct / 2)
        print(f"  {lo:.1f}-{hi:.1f}: {count:>5} ({pct:5.1f}%) {bar}")

    # 3. SIZE
    print(f"\n{'='*60}")
    print(f"3. POSITION SIZING")
    print(f"{'='*60}")

    sizes = np.array([float(t["size"]) for t in focus])
    print(f"Mean: ${sizes.mean():.0f}, Median: ${np.median(sizes):.0f}, Total: ${sizes.sum():,.0f}")

    size_buckets = [(0, 10), (10, 25), (25, 50), (50, 100), (100, 200),
                    (200, 500), (500, 1000), (1000, 50000)]
    print(f"\nSize distribution:")
    for lo, hi in size_buckets:
        count = np.sum((sizes >= lo) & (sizes < hi))
        pct = count / len(sizes) * 100
        bar = "#" * int(pct / 2)
        label = f"${lo}-${hi}" if hi < 50000 else f"${lo}+"
        print(f"  {label:>14}: {count:>5} ({pct:5.1f}%) {bar}")

    # 4. SIDE
    print(f"\n{'='*60}")
    print(f"4. BUY vs SELL (Maker vs Taker)")
    print(f"{'='*60}")

    side_counts = Counter(t.get("side", "") for t in focus)
    for side, count in side_counts.most_common():
        print(f"  {side}: {count} ({count/len(focus)*100:.1f}%)")

    # 5. DIRECTION
    print(f"\n{'='*60}")
    print(f"5. DIRECTIONAL BIAS")
    print(f"{'='*60}")

    outcomes = Counter(t.get("outcome", "") for t in focus)
    for outcome, count in outcomes.most_common():
        print(f"  {outcome}: {count} ({count/len(focus)*100:.1f}%)")

    # 6. TRADES PER WINDOW
    print(f"\n{'='*60}")
    print(f"6. TRADES PER WINDOW")
    print(f"{'='*60}")

    window_trades = defaultdict(list)
    for t in focus:
        slug = t.get("slug", "")
        window_trades[slug].append(t)

    tpw = np.array([len(v) for v in window_trades.values()])
    print(f"Unique windows: {len(window_trades)}")
    print(f"Mean trades/window: {tpw.mean():.1f}, Max: {tpw.max()}")

    tpw_counts = Counter(tpw)
    for n, count in sorted(tpw_counts.items())[:10]:
        pct = count / len(window_trades) * 100
        bar = "#" * int(pct / 2)
        print(f"  {n} trades: {count:>5} ({pct:5.1f}%) {bar}")

    # 7. BOTH SIDES
    print(f"\n{'='*60}")
    print(f"7. BOTH-SIDES TRADING")
    print(f"{'='*60}")

    both = up_only = down_only = other_only = 0
    for slug, wt in window_trades.items():
        outcomes_set = set(t.get("outcome", "") for t in wt)
        if "Up" in outcomes_set and "Down" in outcomes_set:
            both += 1
        elif "Up" in outcomes_set:
            up_only += 1
        elif "Down" in outcomes_set:
            down_only += 1
        else:
            other_only += 1

    tw = len(window_trades)
    print(f"Both sides: {both} ({both/tw*100:.1f}%)")
    print(f"Up only:    {up_only} ({up_only/tw*100:.1f}%)")
    print(f"Down only:  {down_only} ({down_only/tw*100:.1f}%)")
    if other_only:
        print(f"Other:      {other_only} ({other_only/tw*100:.1f}%)")

    # 8. PRICE vs TIMING
    print(f"\n{'='*60}")
    print(f"8. PRICE vs TIMING")
    print(f"{'='*60}")

    if elapsed_list:
        timed = []
        for t in focus:
            elapsed = compute_elapsed_seconds(int(t["timestamp"]), t.get("title", ""))
            dur = get_window_duration(t.get("slug", ""))
            if elapsed is not None and 0 <= elapsed <= dur:
                pct_elapsed = elapsed / dur * 100
                timed.append((pct_elapsed, float(t["price"]), float(t["size"])))

        if timed:
            arr = np.array(timed)
            pct_bins = [(0, 10), (10, 20), (20, 30), (30, 40), (40, 50),
                        (50, 60), (60, 70), (70, 80), (80, 90), (90, 100)]
            print(f"{'Pct':>8} {'Trades':>8} {'Avg Price':>10} {'Avg Size':>10} {'Total $':>12}")
            for lo, hi in pct_bins:
                mask = (arr[:, 0] >= lo) & (arr[:, 0] < hi)
                if mask.sum() > 0:
                    avg_p = arr[mask, 1].mean()
                    avg_s = arr[mask, 2].mean()
                    total = arr[mask, 2].sum()
                    print(f"  {lo:>2}-{hi:>3}%: {mask.sum():>6} {avg_p:>10.3f} {avg_s:>10.0f} ${total:>11,.0f}")

    # 9. CONVICTION
    print(f"\n{'='*60}")
    print(f"9. CONVICTION SIZING")
    print(f"{'='*60}")

    for lo, hi in price_buckets:
        mask = (prices >= lo) & (prices < hi)
        if mask.sum() > 0:
            avg_size = sizes[mask].mean()
            total = sizes[mask].sum()
            print(f"  Price {lo:.1f}-{hi:.1f}: avg=${avg_size:.0f}, n={mask.sum()}, total=${total:,.0f}")

    # 10. HOURLY
    print(f"\n{'='*60}")
    print(f"10. HOURLY ACTIVITY (ET)")
    print(f"{'='*60}")

    hour_counts = Counter()
    for t in focus:
        ts = int(t["timestamp"])
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        et_hour = (dt.hour - 4) % 24
        hour_counts[et_hour] += 1

    for h in range(24):
        count = hour_counts.get(h, 0)
        pct = count / len(focus) * 100
        bar = "#" * int(pct)
        print(f"  {h:02d}:00 ET: {count:>5} ({pct:5.1f}%) {bar}")

    # 11. BUY vs SELL at different prices
    print(f"\n{'='*60}")
    print(f"11. BUY vs SELL BY PRICE RANGE")
    print(f"{'='*60}")

    for lo, hi in price_buckets:
        buy_mask = np.array([(float(t["price"]) >= lo and float(t["price"]) < hi and t.get("side") == "BUY") for t in focus])
        sell_mask = np.array([(float(t["price"]) >= lo and float(t["price"]) < hi and t.get("side") == "SELL") for t in focus])
        b, s = buy_mask.sum(), sell_mask.sum()
        if b + s > 0:
            print(f"  Price {lo:.1f}-{hi:.1f}: BUY={b}, SELL={s}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze_trader_strategy.py <name>")
        print("  Reads data/analysis/<name>/<name>_trades_raw.json")
        sys.exit(1)

    name = sys.argv[1]
    data_file = Path(f"data/analysis/{name}/{name}_trades_raw.json")

    with open(data_file) as f:
        trades = json.load(f)

    analyze(name, trades)


if __name__ == "__main__":
    main()
