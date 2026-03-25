"""Cross-reference trader_a trades with our Pulse BTC_5m model P(up).

For each trade by trader_a on a specific Polymarket 5m BTC market,
computes what our model's P(up) was at the exact trade timestamp.

Usage:
    uv run python scripts/analyze_trader_a_trades.py
"""

from __future__ import annotations

import json
import pickle
from datetime import datetime, timedelta, timezone
from pathlib import Path

import lightgbm as lgb
import numpy as np
import polars as pl

from qm.core.types import Asset, PartialBar, Timeframe
from qm.features.intrabar import (
    CACHED_DEFAULTS,
    CACHED_FEATURE_NAMES,
    IntraBarFeatureCalculator,
)
from qm.features.live_cache import _build_reorder_indices, _load_model_feature_order
from qm.features.pipeline import FeaturePipeline

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SLUG = "btc-updown-5m-1774218300"
TRADES_FILE = Path("data/analysis/trader_a/trader_a_trades_mar22_5m.json")
TICK_DIR = Path("data/raw/polymarket_ticks/asset=BTC/timeframe=5m")
OHLCV_DIR = Path("data/raw/ohlcv/asset=BTC/timeframe=5m")
MODEL_DIR = Path("data/models/pulse/BTC_5m")
OUTPUT_CSV = Path("data/analysis/trader_a/trader_a_trades_vs_model.csv")

# Market window: March 22, 6:25-6:30 PM ET = 22:25-22:30 UTC
WINDOW_START = datetime(2026, 3, 22, 22, 25, 0, tzinfo=timezone.utc)
WINDOW_END = datetime(2026, 3, 22, 22, 30, 0, tzinfo=timezone.utc)
BAR_SECONDS = 300.0  # 5 minutes


def load_trades() -> list[dict]:
    """Load trader_a trades for the target slug."""
    with open(TRADES_FILE) as f:
        trades = json.load(f)
    return sorted(trades, key=lambda t: t["timestamp"])


def load_tick_data() -> pl.DataFrame:
    """Load all tick data for March 22 BTC 5m."""
    df = pl.scan_parquet(str(TICK_DIR / "date=2026-03-22" / "*.parquet"))
    return df.collect()


def build_ohlcv_from_ticks(ticks: pl.DataFrame) -> pl.DataFrame:
    """Build 5-minute OHLCV bars from tick data using spot_price.

    Returns DataFrame with columns: time, open, high, low, close, volume,
    trade_count, vwap (matching what FeaturePipeline expects).
    """
    # Each tick has window_start; group by it to get per-bar OHLCV
    bars = (
        ticks.filter(~pl.col("is_heartbeat"))
        .group_by("window_start")
        .agg(
            pl.col("spot_price").first().alias("open"),
            pl.col("spot_price").max().alias("high"),
            pl.col("spot_price").min().alias("low"),
            pl.col("spot_price").last().alias("close"),
            # Use tick count as proxy for volume/trade_count (no actual volume in ticks)
            pl.len().alias("trade_count"),
        )
        .sort("window_start")
        .with_columns(
            pl.col("window_start").alias("time"),
            # Approximate volume from trade count (dummy for feature computation)
            pl.col("trade_count").cast(pl.Float64).alias("volume"),
            # VWAP approximation: mean of spot prices
            pl.lit(0.0).alias("vwap"),  # placeholder
        )
        .select("time", "open", "high", "low", "close", "volume", "trade_count", "vwap")
    )
    return bars


def load_historical_ohlcv() -> pl.DataFrame:
    """Load recent OHLCV bars from Binance data (up to March 21)."""
    frames = []
    for date_str in ["2026-03-19", "2026-03-20", "2026-03-21"]:
        path = OHLCV_DIR / f"date={date_str}" / "data.parquet"
        if path.exists():
            df = pl.read_parquet(str(path))
            # Normalize column names: timestamp -> time, add missing cols
            if "timestamp" in df.columns:
                df = df.rename({"timestamp": "time"})
            elif "open_time" in df.columns and "time" not in df.columns:
                df = df.with_columns(
                    pl.from_epoch(pl.col("open_time"), time_unit="ms").alias("time")
                )
            # Ensure required columns exist
            if "trade_count" not in df.columns:
                df = df.with_columns(pl.lit(0).alias("trade_count"))
            if "vwap" not in df.columns:
                df = df.with_columns(pl.lit(0.0).alias("vwap"))
            # Drop extra columns, keep only what pipeline needs
            df = df.select("time", "open", "high", "low", "close", "volume", "trade_count", "vwap")
            frames.append(df)
    if not frames:
        raise FileNotFoundError("No OHLCV data found for preceding days")
    return pl.concat(frames).sort("time")


def compute_sentinel_features(
    historical_bars: pl.DataFrame, tick_bars: pl.DataFrame
) -> dict[str, float]:
    """Run Sentinel pipeline on combined bars, return features for the bar
    immediately preceding the target window.
    """
    # Combine historical OHLCV with tick-derived bars
    # Ensure schema compatibility - strip timezone from tick bars to match historical
    tick_bars_compat = tick_bars.select(historical_bars.columns).with_columns(
        pl.col("time").dt.replace_time_zone(None),
        pl.col("trade_count").cast(pl.Int32),
    )
    # Also ensure historical bars are timezone-naive
    historical_bars = historical_bars.with_columns(
        pl.col("time").dt.replace_time_zone(None)
    )
    combined = pl.concat([historical_bars, tick_bars_compat]).sort("time")

    # Only keep bars before the target window (compare naive datetimes)
    window_start_naive = WINDOW_START.replace(tzinfo=None)
    preceding = combined.filter(pl.col("time") < window_start_naive)

    # Take last 50 bars for pipeline (enough for RSI-14, etc.)
    preceding = preceding.tail(50)

    pipeline = FeaturePipeline()
    featured = pipeline.compute(preceding)

    # Extract features from the LAST completed bar
    last_row = featured.tail(1)
    features: dict[str, float] = {}
    for name in CACHED_FEATURE_NAMES:
        if name in last_row.columns:
            val = last_row[name][0]
            if val is not None:
                features[name] = float(val)
            else:
                features[name] = CACHED_DEFAULTS[name]
        else:
            features[name] = CACHED_DEFAULTS[name]

    return features


def build_partial_bar_at_timestamp(
    ticks: pl.DataFrame,
    trade_ts: datetime,
) -> PartialBar:
    """Build a PartialBar snapshot at the given timestamp from tick data."""
    # Get ticks for the target window up to the trade timestamp
    window_ticks = ticks.filter(
        (pl.col("window_start") == WINDOW_START)
        & (pl.col("ts") <= trade_ts)
        & (~pl.col("is_heartbeat"))
    ).sort("ts")

    if len(window_ticks) == 0:
        # If no ticks yet, use first available
        window_ticks = ticks.filter(
            pl.col("window_start") == WINDOW_START
        ).sort("ts").head(1)

    open_price = float(window_ticks["spot_price"][0])
    current_price = float(window_ticks["spot_price"][-1])
    high = float(window_ticks["spot_price"].max())
    low = float(window_ticks["spot_price"].min())
    trade_count = len(window_ticks)

    elapsed = (trade_ts - WINDOW_START).total_seconds()
    elapsed = max(0.0, min(elapsed, BAR_SECONDS))

    return PartialBar(
        window_start=WINDOW_START,
        window_end=WINDOW_END,
        asset=Asset.BTC,
        timeframe=Timeframe.M5,
        open=open_price,
        high_so_far=high,
        low_so_far=low,
        current_price=current_price,
        volume_so_far=float(trade_count),  # proxy
        trade_count=trade_count,
        elapsed_seconds=elapsed,
        remaining_seconds=BAR_SECONDS - elapsed,
    )


def get_market_odds_at_timestamp(
    ticks: pl.DataFrame,
    trade_ts: datetime,
) -> dict[str, float]:
    """Get the market odds (mid_up, bid_up, ask_up, etc.) at the trade timestamp."""
    # Find the closest tick to the trade timestamp
    window_ticks = ticks.filter(
        (pl.col("window_start") == WINDOW_START)
        & (pl.col("ts") <= trade_ts)
    ).sort("ts")

    if len(window_ticks) == 0:
        return {"mid_up": 0.5, "bid_up": 0.5, "ask_up": 0.5}

    last_tick = window_ticks.tail(1)
    return {
        "mid_up": float(last_tick["mid_up"][0]) if last_tick["mid_up"][0] is not None else 0.5,
        "bid_up": float(last_tick["bid_up"][0]) if last_tick["bid_up"][0] is not None else 0.5,
        "ask_up": float(last_tick["ask_up"][0]) if last_tick["ask_up"][0] is not None else 0.5,
        "bid_dn": float(last_tick["bid_dn"][0]) if last_tick["bid_dn"][0] is not None else 0.5,
        "ask_dn": float(last_tick["ask_dn"][0]) if last_tick["ask_dn"][0] is not None else 0.5,
        "spread_up": float(last_tick["spread_up"][0]) if last_tick["spread_up"][0] is not None else 0.0,
    }


def main() -> None:
    print("=" * 80)
    print("trader_a Trade Analysis vs Pulse BTC_5m Model")
    print(f"Market: {SLUG}")
    print(f"Window: {WINDOW_START} -> {WINDOW_END}")
    print("=" * 80)

    # 1. Load trades
    trades = load_trades()
    print(f"\n[1] Loaded {len(trades)} trades from {TRADES_FILE}")

    # 2. Load tick data
    ticks = load_tick_data()
    print(f"[2] Loaded {len(ticks)} ticks for March 22")

    # 3. Build OHLCV bars from ticks
    tick_bars = build_ohlcv_from_ticks(ticks)
    print(f"[3] Built {len(tick_bars)} OHLCV bars from tick data")

    # 4. Load historical OHLCV
    hist_bars = load_historical_ohlcv()
    print(f"[4] Loaded {len(hist_bars)} historical OHLCV bars")

    # 5. Compute Sentinel features for the bar preceding the target window
    sentinel_features = compute_sentinel_features(hist_bars, tick_bars)
    print(f"[5] Computed Sentinel features (rsi_14={sentinel_features.get('rsi_14', '?'):.1f})")

    # 6. Load Pulse model + calibrator
    model = lgb.Booster(model_file=str(MODEL_DIR / "model.lgb"))
    model_feature_order = model.feature_name()

    from qm.model.calibration.calibrator import TimeAwareCalibrator
    calibrator = TimeAwareCalibrator()
    calibrator.load(MODEL_DIR / "calibrator.pkl")
    print(f"[6] Loaded Pulse model ({len(model_feature_order)} features) + calibrator")

    # 7. Set up feature calculator with Sentinel cache
    calc = IntraBarFeatureCalculator()
    calc.update_cache(Asset.BTC, sentinel_features)

    # Build reorder indices
    source_names = calc.feature_names
    reorder_idx = _build_reorder_indices(source_names, model_feature_order)

    # 8. Process each trade
    print(f"\n[7] Processing {len(trades)} trades...\n")
    results = []

    for i, trade in enumerate(trades):
        ts_epoch = trade["timestamp"]
        trade_dt = datetime.fromtimestamp(ts_epoch, tz=timezone.utc)

        # Build PartialBar at trade timestamp
        partial = build_partial_bar_at_timestamp(ticks, trade_dt)

        # Compute features
        raw_features = calc.compute(partial)
        features_reordered = raw_features[reorder_idx]

        # Model prediction
        raw_prob = float(model.predict(features_reordered.reshape(1, -1))[0])

        # Calibrate
        elapsed_pct = partial.elapsed_seconds / BAR_SECONDS
        cal_prob = float(
            calibrator.transform(
                np.array([raw_prob]),
                np.array([elapsed_pct]),
            )[0]
        )

        # Market odds at trade time
        market = get_market_odds_at_timestamp(ticks, trade_dt)

        # Trade details
        side = trade["side"]
        outcome = trade["outcome"]
        price = trade["price"]
        size = trade["size"]
        usdc = trade.get("usdcSize", price * size)

        # Edge calculation
        if outcome == "Up":
            model_fair = cal_prob
            edge_vs_model = model_fair - price  # positive = model agrees
        else:
            model_fair = 1.0 - cal_prob
            edge_vs_model = model_fair - price

        results.append({
            "trade_num": i + 1,
            "timestamp_utc": trade_dt.strftime("%Y-%m-%d %H:%M:%S.000"),
            "timestamp_et": (trade_dt - timedelta(hours=4)).strftime("%H:%M:%S"),
            "elapsed_pct": round(elapsed_pct * 100, 1),
            "side": side,
            "outcome": outcome,
            "shares": round(size, 2),
            "price": price,
            "usdc_cost": round(usdc, 2),
            "spot_price": round(partial.current_price, 2),
            "model_raw_pup": round(raw_prob, 4),
            "model_cal_pup": round(cal_prob, 4),
            "market_mid_pup": round(market["mid_up"], 4),
            "market_bid_up": round(market["bid_up"], 4),
            "market_ask_up": round(market["ask_up"], 4),
            "model_fair_for_outcome": round(model_fair, 4),
            "edge_vs_model": round(edge_vs_model, 4),
            "tx_hash": trade.get("transactionHash", ""),
        })

    # 9. Output results
    df = pl.DataFrame(results)
    df.write_csv(str(OUTPUT_CSV))
    print(f"\nSaved to {OUTPUT_CSV}\n")

    # Print summary table
    print(f"{'#':>3} {'Time ET':>8} {'Elap%':>5} {'Side':>4} {'Out':>4} "
          f"{'Shares':>8} {'Price':>6} {'USDC':>8} {'BTC':>10} "
          f"{'RawPup':>7} {'CalPup':>7} {'MktPup':>7} {'Fair':>6} {'Edge':>7}")
    print("-" * 120)

    total_usdc = 0.0
    for r in results:
        total_usdc += r["usdc_cost"]
        edge_str = f"{r['edge_vs_model']:+.4f}"
        print(
            f"{r['trade_num']:>3} {r['timestamp_et']:>8} {r['elapsed_pct']:>5.1f} "
            f"{r['side']:>4} {r['outcome']:>4} "
            f"{r['shares']:>8.2f} {r['price']:>6.2f} {r['usdc_cost']:>8.2f} "
            f"{r['spot_price']:>10.2f} "
            f"{r['model_raw_pup']:>7.4f} {r['model_cal_pup']:>7.4f} "
            f"{r['market_mid_pup']:>7.4f} {r['model_fair_for_outcome']:>6.4f} {edge_str:>7}"
        )

    # Summary stats
    buys_up = [r for r in results if r["side"] == "BUY" and r["outcome"] == "Up"]
    buys_dn = [r for r in results if r["side"] == "BUY" and r["outcome"] == "Down"]
    sells_dn = [r for r in results if r["side"] == "SELL" and r["outcome"] == "Down"]
    sells_up = [r for r in results if r["side"] == "SELL" and r["outcome"] == "Up"]

    print(f"\n{'=' * 80}")
    print(f"SUMMARY")
    print(f"  Total trades: {len(results)}")
    print(f"  Total USDC deployed: ${total_usdc:.2f}")
    print(f"  BUY Up:  {len(buys_up)} trades, ${sum(r['usdc_cost'] for r in buys_up):.2f}")
    print(f"  BUY Down: {len(buys_dn)} trades, ${sum(r['usdc_cost'] for r in buys_dn):.2f}")
    print(f"  SELL Down: {len(sells_dn)} trades, ${sum(r['usdc_cost'] for r in sells_dn):.2f}")
    print(f"  SELL Up:  {len(sells_up)} trades, ${sum(r['usdc_cost'] for r in sells_up):.2f}")

    # Model agreement
    agree = [r for r in results if r["edge_vs_model"] > 0]
    disagree = [r for r in results if r["edge_vs_model"] <= 0]
    print(f"\n  Model agrees (edge > 0): {len(agree)}/{len(results)} trades")
    print(f"  Avg model P(up): {np.mean([r['model_cal_pup'] for r in results]):.4f}")
    print(f"  Avg market P(up): {np.mean([r['market_mid_pup'] for r in results]):.4f}")
    if buys_dn:
        avg_dn_price = np.mean([r["price"] for r in buys_dn])
        avg_model_pdn = np.mean([r["model_fair_for_outcome"] for r in buys_dn])
        print(f"  Avg BUY Down price: {avg_dn_price:.4f} vs model fair P(dn): {avg_model_pdn:.4f}")


if __name__ == "__main__":
    main()
