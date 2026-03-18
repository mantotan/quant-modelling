"""Fetch trade history for Polymarket trader 'trader_b' via data-api."""
import json
import time
from pathlib import Path

import httpx

WALLET = "0x0000000000000000000000000000000000000000"
BASE_URL = "https://data-api.polymarket.com/trades"
OUT_DIR = Path("data/analysis/trader_b")
OUT_DIR.mkdir(parents=True, exist_ok=True)

def fetch_all_trades():
    all_trades = []
    before_ts = None  # cursor for timestamp-based pagination
    limit = 500
    max_offset = 3000  # API caps around 3500

    while True:
        # Use timestamp-based pagination to get around offset limits
        offset = 0
        batch = []

        while True:
            params = f"user={WALLET}&limit={limit}&offset={offset}"
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

            batch.extend(trades)
            print(f"  offset={offset}: got {len(trades)} (batch: {len(batch)}, total: {len(all_trades) + len(batch)})")

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

        # Use oldest trade timestamp as cursor for next batch
        oldest_ts = min(int(t["timestamp"]) for t in batch)
        if before_ts and oldest_ts >= before_ts:
            break  # no progress
        before_ts = oldest_ts - 1  # -1 to avoid re-fetching boundary
        print(f"  Cursor: before={before_ts} (total: {len(all_trades)})")
        time.sleep(0.5)

    return all_trades

def main():
    print(f"Fetching trades for trader_b ({WALLET})")
    trades = fetch_all_trades()
    print(f"\nTotal trades: {len(trades)}")

    # Save raw
    out_file = OUT_DIR / "trader_b_trades_raw.json"
    with open(out_file, "w") as f:
        json.dump(trades, f, indent=2)
    print(f"Saved to {out_file}")

    # Quick stats
    btc_5m = [t for t in trades if "btc-updown-5m" in t.get("slug", "")]
    btc_15m = [t for t in trades if "btc-updown-15m" in t.get("slug", "")]
    other = [t for t in trades if "btc-updown" not in t.get("slug", "")]

    print(f"\nBreakdown:")
    print(f"  BTC 5m:  {len(btc_5m)} trades")
    print(f"  BTC 15m: {len(btc_15m)} trades")
    print(f"  Other:   {len(other)} trades")

    # Side distribution
    buys = sum(1 for t in trades if t.get("side") == "BUY")
    sells = sum(1 for t in trades if t.get("side") == "SELL")
    print(f"\nSides: BUY={buys}, SELL={sells}")

    # Outcome distribution for BTC 5m
    if btc_5m:
        ups = sum(1 for t in btc_5m if t.get("outcome") == "Up")
        downs = sum(1 for t in btc_5m if t.get("outcome") == "Down")
        print(f"\nBTC 5m outcomes: Up={ups}, Down={downs}")

        # Price distribution
        prices = [float(t["price"]) for t in btc_5m if "price" in t]
        if prices:
            print(f"BTC 5m prices: min={min(prices):.3f}, max={max(prices):.3f}, avg={sum(prices)/len(prices):.3f}")

        # Size distribution
        sizes = [float(t["size"]) for t in btc_5m if "size" in t]
        if sizes:
            print(f"BTC 5m sizes:  min={min(sizes):.1f}, max={max(sizes):.1f}, avg={sum(sizes)/len(sizes):.1f}, total=${sum(sizes):,.0f}")

        # Time analysis - when in the 5m window does trader_b trade?
        print(f"\nSample BTC 5m trades (first 20):")
        for t in btc_5m[:20]:
            ts = t.get("timestamp", 0)
            title = t.get("title", "")
            side = t.get("side", "")
            outcome = t.get("outcome", "")
            price = float(t.get("price", 0))
            size = float(t.get("size", 0))
            print(f"  ts={ts} | {side} {outcome} @ {price:.3f} | ${size:.0f} | {title}")

if __name__ == "__main__":
    main()
