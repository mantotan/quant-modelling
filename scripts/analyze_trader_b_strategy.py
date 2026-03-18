"""Deep analysis of trader_b's Polymarket trading strategy."""
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

DATA = Path("data/analysis/trader_b/trader_b_trades_raw.json")


def parse_window_start(title: str) -> int | None:
    """Extract window start time from title like 'Bitcoin Up or Down - March 18, 5:25AM-5:30AM ET'."""
    m = re.search(r"(\w+ \d+), (\d+:\d+)(AM|PM)-(\d+:\d+)(AM|PM) ET", title)
    if not m:
        return None
    # We just need to compute how far into the window the trade happened
    # Parse the start time
    month_day = m.group(1)
    start_time = m.group(2)
    start_ampm = m.group(3)
    return None  # We'll use a different approach


def parse_window_times(title: str):
    """Parse window start/end from title. Returns (start_minute_of_day, end_minute_of_day, duration_minutes)."""
    # "Bitcoin Up or Down - March 18, 5:25AM-5:30AM ET"
    m = re.search(r"(\d+):(\d+)(AM|PM)-(\d+):(\d+)(AM|PM)", title)
    if not m:
        return None, None, None

    sh, sm, sampm = int(m.group(1)), int(m.group(2)), m.group(3)
    eh, em, eampm = int(m.group(4)), int(m.group(5)), m.group(6)

    if sampm == "PM" and sh != 12:
        sh += 12
    if sampm == "AM" and sh == 12:
        sh = 0
    if eampm == "PM" and eh != 12:
        eh += 12
    if eampm == "AM" and eh == 12:
        eh = 0

    start_min = sh * 60 + sm
    end_min = eh * 60 + em
    duration = end_min - start_min
    if duration <= 0:
        duration += 24 * 60
    return start_min, end_min, duration


def compute_elapsed_seconds(trade_ts: int, title: str) -> float | None:
    """Compute how many seconds into the 5m window this trade was placed."""
    # Extract date from title
    m = re.search(r"(\w+) (\d+),", title)
    if not m:
        return None

    month_name = m.group(1)
    day = int(m.group(2))

    # Parse window start time
    tm = re.search(r"(\d+):(\d+)(AM|PM)-", title)
    if not tm:
        return None

    sh, sm, sampm = int(tm.group(1)), int(tm.group(2)), tm.group(3)
    if sampm == "PM" and sh != 12:
        sh += 12
    if sampm == "AM" and sh == 12:
        sh = 0

    # Guess year from timestamp
    dt = datetime.fromtimestamp(trade_ts, tz=timezone.utc)
    year = dt.year

    months = {"January": 1, "February": 2, "March": 3, "April": 4,
              "May": 5, "June": 6, "July": 7, "August": 8,
              "September": 9, "October": 10, "November": 11, "December": 12}
    month_num = months.get(month_name)
    if not month_num:
        return None

    # ET is UTC-4 (EDT) or UTC-5 (EST) — assume EDT for simplicity
    # Window start in UTC = ET + 4h
    from datetime import timedelta
    window_start_et = datetime(year, month_num, day, sh, sm, 0, tzinfo=timezone.utc)
    window_start_utc = window_start_et + timedelta(hours=4)  # EDT offset

    elapsed = trade_ts - int(window_start_utc.timestamp())
    return elapsed


def main():
    with open(DATA) as f:
        trades = json.load(f)

    btc_5m = [t for t in trades if "btc-updown-5m" in t.get("slug", "")]
    print(f"=== RWO STRATEGY ANALYSIS ===")
    print(f"Total trades: {len(trades)}")
    print(f"BTC 5m trades: {len(btc_5m)}")
    print()

    # 1. TIMING ANALYSIS — when in the 5m window does trader_b trade?
    print("=" * 60)
    print("1. TIMING WITHIN 5-MINUTE WINDOW")
    print("=" * 60)

    elapsed_list = []
    for t in btc_5m:
        elapsed = compute_elapsed_seconds(int(t["timestamp"]), t.get("title", ""))
        if elapsed is not None and -30 <= elapsed <= 360:
            elapsed_list.append(elapsed)

    elapsed_arr = np.array(elapsed_list)
    print(f"Trades with valid timing: {len(elapsed_arr)}")
    print(f"Mean elapsed: {elapsed_arr.mean():.1f}s")
    print(f"Median elapsed: {np.median(elapsed_arr):.1f}s")
    print(f"Std: {elapsed_arr.std():.1f}s")
    print()

    # Histogram by 30s buckets
    buckets = [(-30, 0), (0, 30), (30, 60), (60, 120), (120, 180), (180, 240), (240, 300), (300, 360)]
    print("Time bucket distribution:")
    for lo, hi in buckets:
        count = np.sum((elapsed_arr >= lo) & (elapsed_arr < hi))
        pct = count / len(elapsed_arr) * 100
        bar = "#" * int(pct / 2)
        print(f"  {lo:>4}-{hi:>3}s: {count:>5} ({pct:5.1f}%) {bar}")

    # 2. PRICE ANALYSIS — what prices does trader_b buy at?
    print()
    print("=" * 60)
    print("2. PRICE DISTRIBUTION (what odds does trader_b buy at?)")
    print("=" * 60)

    prices = np.array([float(t["price"]) for t in btc_5m])
    print(f"Mean price: {prices.mean():.3f}")
    print(f"Median price: {np.median(prices):.3f}")
    print(f"Std: {prices.std():.3f}")
    print()

    # Price bucket distribution
    price_buckets = [(0, 0.1), (0.1, 0.2), (0.2, 0.3), (0.3, 0.4), (0.4, 0.5),
                     (0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.0)]
    print("Price bucket distribution:")
    for lo, hi in price_buckets:
        count = np.sum((prices >= lo) & (prices < hi))
        pct = count / len(prices) * 100
        bar = "#" * int(pct / 2)
        print(f"  {lo:.1f}-{hi:.1f}: {count:>5} ({pct:5.1f}%) {bar}")

    # 3. SIZE ANALYSIS
    print()
    print("=" * 60)
    print("3. POSITION SIZING")
    print("=" * 60)

    sizes = np.array([float(t["size"]) for t in btc_5m])
    print(f"Mean size: ${sizes.mean():.0f}")
    print(f"Median size: ${np.median(sizes):.0f}")
    print(f"Std: ${sizes.std():.0f}")
    print(f"Total volume: ${sizes.sum():,.0f}")
    print()

    size_buckets = [(0, 50), (50, 100), (100, 200), (200, 500), (500, 1000),
                    (1000, 2000), (2000, 5000), (5000, 15001)]
    print("Size bucket distribution:")
    for lo, hi in size_buckets:
        count = np.sum((sizes >= lo) & (sizes < hi))
        pct = count / len(sizes) * 100
        bar = "#" * int(pct / 2)
        label = f"${lo}-${hi}" if hi < 15001 else f"${lo}+"
        print(f"  {label:>14}: {count:>5} ({pct:5.1f}%) {bar}")

    # 4. SIDE ANALYSIS — Up vs Down
    print()
    print("=" * 60)
    print("4. DIRECTIONAL BIAS")
    print("=" * 60)

    outcomes = Counter(t.get("outcome", "") for t in btc_5m)
    for outcome, count in outcomes.most_common():
        print(f"  {outcome}: {count} ({count/len(btc_5m)*100:.1f}%)")

    # 5. MAKER vs TAKER
    print()
    print("=" * 60)
    print("5. MAKER vs TAKER (BUY vs SELL)")
    print("=" * 60)

    sides = Counter(t.get("side", "") for t in btc_5m)
    for side, count in sides.most_common():
        print(f"  {side}: {count} ({count/len(btc_5m)*100:.1f}%)")

    # 6. MULTIPLE TRADES PER WINDOW
    print()
    print("=" * 60)
    print("6. TRADES PER WINDOW (does trader_b trade multiple times per 5m?)")
    print("=" * 60)

    window_trades = defaultdict(list)
    for t in btc_5m:
        slug = t.get("slug", "")
        window_trades[slug].append(t)

    trades_per_window = [len(v) for v in window_trades.values()]
    tpw = np.array(trades_per_window)
    print(f"Unique windows traded: {len(window_trades)}")
    print(f"Mean trades/window: {tpw.mean():.1f}")
    print(f"Max trades/window: {tpw.max()}")
    print()

    tpw_counts = Counter(trades_per_window)
    print("Distribution:")
    for n, count in sorted(tpw_counts.items()):
        pct = count / len(window_trades) * 100
        bar = "#" * int(pct / 2)
        print(f"  {n} trades: {count:>5} windows ({pct:5.1f}%) {bar}")

    # 7. BOTH-SIDES ANALYSIS — does trader_b bet Up AND Down in same window?
    print()
    print("=" * 60)
    print("7. BOTH-SIDES TRADING (Up + Down in same window)")
    print("=" * 60)

    both_sides = 0
    up_only = 0
    down_only = 0
    for slug, wt in window_trades.items():
        outcomes_in_window = set(t.get("outcome", "") for t in wt)
        if "Up" in outcomes_in_window and "Down" in outcomes_in_window:
            both_sides += 1
        elif "Up" in outcomes_in_window:
            up_only += 1
        else:
            down_only += 1

    total_windows = len(window_trades)
    print(f"Both sides: {both_sides} ({both_sides/total_windows*100:.1f}%)")
    print(f"Up only:    {up_only} ({up_only/total_windows*100:.1f}%)")
    print(f"Down only:  {down_only} ({down_only/total_windows*100:.1f}%)")

    # 8. PRICE vs TIMING — does trader_b buy cheaper early and more expensive late?
    print()
    print("=" * 60)
    print("8. PRICE vs TIMING (does price increase with elapsed time?)")
    print("=" * 60)

    timed_trades = []
    for t in btc_5m:
        elapsed = compute_elapsed_seconds(int(t["timestamp"]), t.get("title", ""))
        if elapsed is not None and 0 <= elapsed <= 300:
            timed_trades.append((elapsed, float(t["price"]), float(t["size"]), t.get("outcome", "")))

    if timed_trades:
        timed_arr = np.array([(e, p, s) for e, p, s, _ in timed_trades])
        time_bins = [(0, 30), (30, 60), (60, 120), (120, 180), (180, 240), (240, 300)]
        print(f"{'Bucket':>12} {'Trades':>8} {'Avg Price':>10} {'Avg Size':>10} {'Total $':>12}")
        for lo, hi in time_bins:
            mask = (timed_arr[:, 0] >= lo) & (timed_arr[:, 0] < hi)
            if mask.sum() > 0:
                avg_p = timed_arr[mask, 1].mean()
                avg_s = timed_arr[mask, 2].mean()
                total_s = timed_arr[mask, 2].sum()
                print(f"  {lo:>3}-{hi:>3}s: {mask.sum():>6} {avg_p:>10.3f} {avg_s:>10.0f} ${total_s:>11,.0f}")

    # 9. CONVICTION SIZING — does trader_b size up when price is extreme (high confidence)?
    print()
    print("=" * 60)
    print("9. CONVICTION SIZING (larger bets at extreme prices?)")
    print("=" * 60)

    for lo, hi in price_buckets:
        mask = (prices >= lo) & (prices < hi)
        if mask.sum() > 0:
            avg_size = sizes[mask].mean()
            total = sizes[mask].sum()
            print(f"  Price {lo:.1f}-{hi:.1f}: avg=${avg_size:.0f}, n={mask.sum()}, total=${total:,.0f}")

    # 10. HOURLY PATTERN — is trader_b active 24/7 or specific hours?
    print()
    print("=" * 60)
    print("10. HOURLY ACTIVITY PATTERN (ET)")
    print("=" * 60)

    hour_counts = Counter()
    for t in btc_5m:
        ts = int(t["timestamp"])
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        et_hour = (dt.hour - 4) % 24  # crude EDT conversion
        hour_counts[et_hour] += 1

    for h in range(24):
        count = hour_counts.get(h, 0)
        pct = count / len(btc_5m) * 100
        bar = "#" * int(pct)
        print(f"  {h:02d}:00 ET: {count:>5} ({pct:5.1f}%) {bar}")


if __name__ == "__main__":
    main()
