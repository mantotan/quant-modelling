# Dutch Monitor Report
Updated: 2026-03-21T19:02:00Z

## Process Health
| Process | Status | Restarts | Uptime |
|---------|--------|----------|--------|
| dutch-5m | online | 3 | ~4m |
| dutch-15m | online | 3 | ~4m |
| dutch-1h | online | 3 | ~4m |

Note: All 3 processes restarted at ~18:58 UTC for V3 fill simulator upgrade. Restart count=3 is from upgrade cycles, not crashes.

## Anomaly Checklist
| # | Check | Status | Evidence |
|---|-------|--------|----------|
| 1 | Process health | PASS | All 3 online |
| 2 | Sell race | CRITICAL | 15m: 6/10 recent bars, 5m: 1/10 recent bars have sell_losing with time_pct gap < 0.005 |
| 3 | Negative net shares | CRITICAL | 15m: 2 bars (bar 1774084500 dn=-7.10, bar 1774088100 dn=-23.35). 5m: PASS now |
| 4 | One-sided accumulation | WARNING | 5m: 9 consecutive bars matched_ratio < 20%, 15m: 5 consecutive |
| 5 | Budget exhaustion | PASS | Not observed |
| 6 | Pair cost stuck | PASS | No 5+ consecutive bars > 0.98 |
| 7 | Zero fills | PASS | Fill rates ~99% across TFs |
| 8 | Kill switch spam | PASS | 0% of bars |

## Per-Timeframe Metrics (last 10 resolved bars)
| TF | Bars | Avg Pair Cost | Avg Profit | Fill Rate | Matched Ratio | Sell Count |
|----|------|---------------|------------|-----------|---------------|------------|
| 5m | 10 | -0.593 | $-66.48 | 99.5% | 6.5% | 257 |
| 15m | 10 | 0.803 | $-26.63 | 98.6% | 15.3% | 264 |
| 1h | 0 | N/A | N/A | N/A | N/A | 0 |

## Critical Findings

### 1. Negative pair costs on 5m (avg = -0.59)
The system spends far more on sells than it recovers. Sell_losing logic dumps shares at massive losses. Combined with 6.5% matched ratio, nearly all inventory is unmatched and sold at loss.

### 2. Sell race persists after V3 restart
V3 fill simulator did NOT fix sell race. 15m shows 6/10 bars with rapid-fire sell_losing events at near-identical time_pct. This causes negative shares (selling beyond held inventory).

### 3. One-sided accumulation dominant
Both 5m (9 consec) and 15m (5 consec) show persistent one-sided loading with minimal matching. Root cause of poor pair costs and losses.

## Alerts
- **CRITICAL: sell_race** (detected 2026-03-21T11:24:07Z) -- STILL ACTIVE, reduced but not fixed
- **CRITICAL: negative_shares** (detected 2026-03-21T11:24:07Z) -- STILL ACTIVE on 15m, fixed on 5m
- **WARNING: one_sided_accumulation** -- 5m: 9 consec bars, 15m: 5 consec bars
