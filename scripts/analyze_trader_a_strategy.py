"""Analyze trader_a's trading strategy on the 5m BTC market."""
from __future__ import annotations

import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import polars as pl
import numpy as np

df = pl.read_csv("data/analysis/trader_a/trader_a_trades_vs_model.csv")

print("=" * 90)
print("trader_a STRATEGY ANALYSIS - btc-updown-5m-1774218300 (resolved UP)")
print("=" * 90)

# ── 1. Timeline phases ──────────────────────────────────────────────
print("\n### PHASE ANALYSIS (by elapsed %)")
phases = [
    (0, 10, "Phase 1: 0-10% (first 30s)"),
    (10, 25, "Phase 2: 10-25% (30s-75s)"),
    (25, 45, "Phase 3: 25-45% (75s-135s)"),
    (45, 60, "Phase 4: 45-60% (135s-180s)"),
    (60, 75, "Phase 5: 60-75% (180s-225s)"),
]
for lo, hi, label in phases:
    phase = df.filter((pl.col("elapsed_pct") >= lo) & (pl.col("elapsed_pct") < hi))
    if len(phase) == 0:
        continue
    print(f"\n  {label} ({len(phase)} trades, ${phase['usdc_cost'].sum():.0f} deployed)")
    for side_val, out_val, tag in [
        ("BUY", "Up", "BUY Up  "),
        ("BUY", "Down", "BUY Down"),
        ("SELL", "Up", "SELL Up "),
        ("SELL", "Down", "SELL Dn "),
    ]:
        sub = phase.filter((pl.col("side") == side_val) & (pl.col("outcome") == out_val))
        if len(sub) == 0:
            continue
        mid_col = "mid_up" if out_val == "Up" else "mid_dn"
        print(
            f"    {tag}: {len(sub):>3} trades "
            f"${sub['usdc_cost'].sum():>7.0f}  "
            f"avg_price={sub['price'].mean():.2f}  "
            f"avg_{mid_col}={sub[mid_col].mean():.2f}  "
            f"PnL=${sub['pnl_usdc'].sum():>+8.0f}"
        )

# ── 2. Maker spread capture ────────────────────────────────────────
print("\n\n### MAKER SPREAD ANALYSIS")
buy_dn = df.filter((pl.col("side") == "BUY") & (pl.col("outcome") == "Down"))
buy_up = df.filter((pl.col("side") == "BUY") & (pl.col("outcome") == "Up"))
dn_saved = buy_dn["ask_dn"].mean() - buy_dn["price"].mean()
up_saved = buy_up["ask_up"].mean() - buy_up["price"].mean()
print(f"  BUY Down: avg fill={buy_dn['price'].mean():.3f}  avg ask_dn={buy_dn['ask_dn'].mean():.3f}  saved {dn_saved:.3f}/share by being maker")
print(f"  BUY Up:   avg fill={buy_up['price'].mean():.3f}  avg ask_up={buy_up['ask_up'].mean():.3f}  saved {up_saved:.3f}/share by being maker")
print(f"  Total saved vs taker: ~${dn_saved * buy_dn['shares'].sum() + up_saved * buy_up['shares'].sum():.0f}")

# ── 3. Net position (both-sides) ───────────────────────────────────
print("\n\n### NET POSITION (BOTH-SIDES HEDGING)")
bought_up_shares = df.filter((pl.col("side") == "BUY") & (pl.col("outcome") == "Up"))["shares"].sum()
bought_dn_shares = df.filter((pl.col("side") == "BUY") & (pl.col("outcome") == "Down"))["shares"].sum()
sold_up_shares = df.filter((pl.col("side") == "SELL") & (pl.col("outcome") == "Up"))["shares"].sum()
sold_dn_shares = df.filter((pl.col("side") == "SELL") & (pl.col("outcome") == "Down"))["shares"].sum()
net_up = bought_up_shares - sold_up_shares
net_dn = bought_dn_shares - sold_dn_shares

cost_up = df.filter((pl.col("side") == "BUY") & (pl.col("outcome") == "Up"))["usdc_cost"].sum()
cost_dn = df.filter((pl.col("side") == "BUY") & (pl.col("outcome") == "Down"))["usdc_cost"].sum()
proceeds_up = df.filter((pl.col("side") == "SELL") & (pl.col("outcome") == "Up"))["usdc_cost"].sum()
proceeds_dn = df.filter((pl.col("side") == "SELL") & (pl.col("outcome") == "Down"))["usdc_cost"].sum()
net_cost_up = cost_up - proceeds_up
net_cost_dn = cost_dn - proceeds_dn
total_net_cost = net_cost_up + net_cost_dn

print(f"  Net Up:   {net_up:>7.0f} shares  (bought {bought_up_shares:.0f}, sold {sold_up_shares:.0f})  net cost ${net_cost_up:.0f}")
print(f"  Net Down: {net_dn:>7.0f} shares  (bought {bought_dn_shares:.0f}, sold {sold_dn_shares:.0f})  net cost ${net_cost_dn:.0f}")
print(f"  Total net invested: ${total_net_cost:.0f}")
print(f"  Avg cost/Up share:   ${net_cost_up / net_up:.3f}" if net_up > 0 else "")
print(f"  Avg cost/Down share: ${net_cost_dn / net_dn:.3f}" if net_dn > 0 else "")
print()
pnl_if_up = net_up - total_net_cost
pnl_if_dn = net_dn - total_net_cost
print(f"  If UP resolves:   payout ${net_up:.0f}  - cost ${total_net_cost:.0f}  = PnL ${pnl_if_up:+.0f}  ({pnl_if_up/total_net_cost*100:+.1f}%)")
print(f"  If DOWN resolves: payout ${net_dn:.0f}  - cost ${total_net_cost:.0f}  = PnL ${pnl_if_dn:+.0f}  ({pnl_if_dn/total_net_cost*100:+.1f}%)")

# Is it a guaranteed profit (both sides positive)?
if pnl_if_up > 0 and pnl_if_dn > 0:
    print(f"  >>> GUARANTEED PROFIT: min ${min(pnl_if_up, pnl_if_dn):.0f}, max ${max(pnl_if_up, pnl_if_dn):.0f} <<<")
elif pnl_if_up > 0 or pnl_if_dn > 0:
    print(f"  >>> DIRECTIONAL BET with hedge: wins if {'UP' if pnl_if_up > 0 else 'DOWN'}, loses if {'DOWN' if pnl_if_up > 0 else 'UP'} <<<")

# ── 4. Spot price vs side selection ─────────────────────────────────
print("\n\n### SPOT PRICE vs SIDE SELECTION")
open_price = df["spot_price"][0]
print(f"  Bar open price: ~${open_price:.0f}")
for tag, out_val in [("BUY Up", "Up"), ("BUY Down", "Down")]:
    sub = df.filter((pl.col("side") == "BUY") & (pl.col("outcome") == out_val))
    if len(sub) == 0:
        continue
    spots = sub["spot_price"].to_list()
    dist = [(s - open_price) for s in spots]
    print(f"  {tag}:")
    print(f"    spot range: ${min(spots):.0f} - ${max(spots):.0f}  (move from open: ${min(dist):.0f} to ${max(dist):.0f})")
    print(f"    avg mid_up when buying: {sub['mid_up'].mean():.3f}")
    print(f"    PATTERN: buys {out_val} when spot {'BELOW' if np.mean(dist) < 0 else 'ABOVE'} open (avg move ${np.mean(dist):+.0f})")

# ── 5. Timing: when does he place orders? ───────────────────────────
print("\n\n### ORDER TIMING PATTERN")
# Group by unique fill timestamps
timestamps = df["fill_timestamp_utc"].unique().sort()
print(f"  Unique fill timestamps: {len(timestamps)}")
print(f"  Trades span: {df['elapsed_pct'].min():.0f}% to {df['elapsed_pct'].max():.0f}% of bar")
print(f"  First trade at {df['elapsed_pct'].min():.1f}% (~{df['elapsed_pct'].min()*3:.0f}s into bar)")
print(f"  Last trade at {df['elapsed_pct'].max():.1f}% (~{df['elapsed_pct'].max()*3:.0f}s into bar)")
print(f"  He does NOT trade in the last 28% of the bar (no trades after 72%)")

# ── 6. Share sizing pattern ─────────────────────────────────────────
print("\n\n### SIZING PATTERN")
print(f"  Max single trade: {df['shares'].max():.0f} shares (${df['usdc_cost'].max():.0f})")
print(f"  Avg trade size: {df['shares'].mean():.0f} shares (${df['usdc_cost'].mean():.0f})")
print(f"  Median trade size: {df['shares'].median():.0f} shares")
big = df.filter(pl.col("shares") > 100)
small = df.filter(pl.col("shares") <= 100)
print(f"  Large trades (>100 shares): {len(big)} ({len(big)/len(df)*100:.0f}%)")
print(f"  Small trades (<=100 shares): {len(small)} ({len(small)/len(df)*100:.0f}%)")

# ── 7. Key strategy insights ───────────────────────────────────────
print("\n\n### STRATEGY REVERSE-ENGINEERING")
print("""
  WHAT HE DOES:
  1. MAKER-ONLY: Posts limit orders on both sides of both books (Up + Down)
     Never crosses the spread - saves ~$0.03-0.06/share vs taker

  2. CONTRARIAN / MEAN-REVERSION within the bar:
     - When spot DROPS below open -> buys Up cheap (market panics, Up odds crash)
     - When spot RALLIES above open -> buys Down cheap (market euphoria, Down odds crash)
     - He's betting on REVERSION or just capturing mispriced odds

  3. BOTH-SIDES ACCUMULATION:
     - Buys BOTH Up and Down throughout the bar
     - Goal: accumulate shares on both sides at prices that sum to < $1.00
     - Combined cost basis < $1.00 = guaranteed profit regardless of outcome

  4. SELLS TO REBALANCE:
     - Occasionally sells one side when it gets too heavy
     - Captures P&L when odds swing in his favor mid-bar

  5. EXITS BY 72% elapsed:
     - No trades in the final ~85 seconds
     - Likely: odds become too efficient late in bar (less mispricing to exploit)
     - Or: his edge is in the volatile early/mid period

  WHY IT WORKS:
  - Polymarket 5m binary markets are ILLIQUID with WIDE spreads
  - Retail traders panic-buy/sell on each spot price tick
  - He sits passively as maker, gets filled when others panic
  - His combined cost basis < $1.00 = structural edge
""")

# ── 8. What we need to replicate ────────────────────────────────────
print("### WHAT WE NEED TO REPLICATE THIS")
print("""
  1. MAKER INFRASTRUCTURE:
     - Polymarket CLOB API for limit order placement (not just REST)
     - Sub-second order management (post, cancel, reprice)
     - Must be on Polygon L2 with low-latency RPC

  2. DUAL-BOOK QUOTING:
     - Quote BOTH Up and Down books simultaneously
     - Dynamic pricing: adjust quotes based on spot price movement
     - Inventory management: track net position, avoid getting too one-sided

  3. OUR MODEL AS EDGE:
     - Use Pulse P(up) to set fair value -> derive limit order prices
     - When model says P(up)=0.70: bid Up at 0.68, bid Down at 0.28
     - Combined bid < $1.00 = positive expected value even before spread
     - Our model IS the pricing oracle - much better than spot-price-following

  4. PACING / RISK:
     - Max position per side (he caps at ~151 shares/trade, ~$150 max per fill)
     - Stop quoting after 70% elapsed (edge disappears)
     - Circuit breaker if net position gets too one-sided

  5. THIS IS BASICALLY OUR DUTCH ENGINE but as a market maker:
     - Dutch V7.3 already does conviction-based accumulation on both sides
     - We just need to switch from TAKER (crossing spread) to MAKER (posting bids)
     - And add the dual-book quoting logic
""")

# ── 9. Quantify the opportunity ─────────────────────────────────────
print("### OPPORTUNITY SIZE")
spread_up_avg = df["spread_up"].mean()
spread_dn_avg = df["spread_dn"].mean()
print(f"  Avg spread Up:   {spread_up_avg:.3f} ({spread_up_avg*100:.1f} cents)")
print(f"  Avg spread Down: {spread_dn_avg:.3f} ({spread_dn_avg*100:.1f} cents)")
print(f"  His PnL this bar: ${df['pnl_usdc'].sum():.0f} on ${total_net_cost:.0f} deployed ({df['pnl_usdc'].sum()/total_net_cost*100:.1f}%)")
print(f"  If replicated every 5m bar for 24h: {288} bars x ${df['pnl_usdc'].sum():.0f} = ~${288 * df['pnl_usdc'].sum():.0f}/day")
print(f"  (Assuming similar fill rates and spreads - likely lower in practice)")
