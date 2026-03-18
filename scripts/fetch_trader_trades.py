"""Fetch trade history for any Polymarket trader via data-api."""
import json
import sys
import time
from pathlib import Path

import httpx

BASE_URL = "https://data-api.polymarket.com/trades"
OUT_DIR = Path("data/analysis")


def fetch_all_trades(wallet: str):
    all_trades = []
    before_ts = None
    limit = 500
    max_offset = 3000
    seen_hashes = set()

    while True:
        offset = 0
        batch = []

        while True:
            params = f"user={wallet}&limit={limit}&offset={offset}"
            if before_ts:
                params += f"&before={before_ts}"
            url = f"{BASE_URL}?{params}"

            try:
                resp = httpx.get(url, timeout=30)
                resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 400 and offset > 0:
                    print(f"  Hit offset limit at {offset}, switching cursor")
                    break
                raise

            trades = resp.json()
            if not trades:
                break

            # Dedup by transaction hash
            new_trades = []
            for t in trades:
                h = t.get("transactionHash", "")
                key = f"{h}_{t.get('asset','')}"
                if key not in seen_hashes:
                    seen_hashes.add(key)
                    new_trades.append(t)

            batch.extend(new_trades)
            print(f"  offset={offset}: got {len(trades)} ({len(new_trades)} new, total: {len(all_trades) + len(batch)})")

            if len(trades) < limit:
                break

            offset += limit
            if offset >= max_offset:
                print(f"  Hit max_offset={max_offset}, switching cursor")
                break

            time.sleep(0.3)

        if not batch:
            break

        all_trades.extend(batch)

        oldest_ts = min(int(t["timestamp"]) for t in batch)
        if before_ts and oldest_ts >= before_ts:
            break
        before_ts = oldest_ts - 1
        print(f"  Cursor: before={before_ts} (total: {len(all_trades)})")
        time.sleep(0.5)

    return all_trades


def main():
    if len(sys.argv) < 3:
        print("Usage: python fetch_trader_trades.py <name> <wallet>")
        sys.exit(1)

    name = sys.argv[1]
    wallet = sys.argv[2]

    out_dir = OUT_DIR / name
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Fetching trades for {name} ({wallet})")
    trades = fetch_all_trades(wallet)
    print(f"\nTotal trades: {len(trades)}")

    out_file = out_dir / f"{name}_trades_raw.json"
    with open(out_file, "w") as f:
        json.dump(trades, f, indent=2)
    print(f"Saved to {out_file}")

    # Quick breakdown
    from collections import Counter
    slugs = Counter()
    for t in trades:
        slug = t.get("slug", "unknown")
        if "btc-updown-5m" in slug:
            slugs["btc_5m"] += 1
        elif "btc-updown-15m" in slug:
            slugs["btc_15m"] += 1
        elif "btc-updown-1h" in slug:
            slugs["btc_1h"] += 1
        elif "eth" in slug:
            slugs["eth"] += 1
        elif "sol" in slug:
            slugs["sol"] += 1
        else:
            slugs["other"] += 1

    print(f"\nBreakdown:")
    for k, v in slugs.most_common():
        print(f"  {k}: {v}")

    sides = Counter(t.get("side", "") for t in trades)
    print(f"\nSides: {dict(sides)}")

    prices = [float(t["price"]) for t in trades if "price" in t]
    sizes = [float(t["size"]) for t in trades if "size" in t]
    if prices:
        print(f"\nPrices: min={min(prices):.3f}, max={max(prices):.3f}, avg={sum(prices)/len(prices):.3f}")
    if sizes:
        print(f"Sizes:  min={min(sizes):.1f}, max={max(sizes):.1f}, avg={sum(sizes)/len(sizes):.1f}, total=${sum(sizes):,.0f}")


if __name__ == "__main__":
    main()
