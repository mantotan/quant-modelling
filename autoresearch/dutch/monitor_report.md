# Dutch Monitor Report
Updated: 2026-03-21T11:24:07Z

## Process Health
| Process | Status | Restarts | Uptime |
|---------|--------|----------|--------|
| dutch-5m | online | 2 | 13m |
| dutch-15m | online | 2 | 13m |
| dutch-1h | online | 2 | 13m |

## Anomaly Checklist
| # | Check | Status | Evidence |
|---|-------|--------|----------|
| 1 | Process health | PASS | All 3 processes online |
| 2 | Sell race | CRITICAL | 19 bars in 5m, 8 bars in 15m have sell_losing events with time_pct gap < 0.005 |
| 3 | Negative net shares | CRITICAL | 5m: 8 bars with negative shares (e.g. bar 1774089000 up=-20.88 dn=-46.87); 15m: 2 bars (e.g. bar 1774084500 dn=-7.10) |
| 4 | One-sided accumulation | WARNING | 5m: 3 consecutive bars with matched/max < 0.20; 15m: 4 consecutive bars |
| 5 | Budget exhaustion | PASS | No early budget exhaustion detected |
| 6 | Pair cost stuck | WARNING | 5m: 5 consecutive bars with avg_pair_cost >= 1.0 |
| 7 | Zero fills | PASS | All bars have fills |
| 8 | Kill switch spam | PASS | 0% kill switch rate across both TFs |

## Per-Timeframe Metrics (last 10 resolved bars)
| TF | Bars | Avg Pair Cost | Avg Profit | Fill Rate | Matched Ratio | Sell Count |
|----|------|---------------|------------|-----------|---------------|------------|
| 5m | 10 | 0.692 | $-49.30 | 99.3% | 25.4% | 19 bars w/sell |
| 15m | 10 | 0.943 | $-44.01 | 98.8% | 18.7% | 8 bars w/sell |
| 1h | 0 | - | - | - | - | - |

## Alerts
- **CRITICAL: Sell race condition** — Multiple sell_losing events fire within < 0.005 time_pct on the same bar across nearly every bar. This suggests the sell logic fires redundantly on adjacent ticks without debounce. 19/37 bars affected in 5m, 8/20 in 15m. Some gaps as small as 0.000001.
- **CRITICAL: Negative net shares** — 8 bars in 5m and 2 bars in 15m end with negative up_shares or dn_shares, meaning more shares were sold than ever bought on that side. This indicates sell orders are executing beyond available inventory.
- **WARNING: One-sided accumulation** — Both TFs show 3-4 consecutive bars with matched ratio < 20%, indicating the engine is heavily accumulating one side without balancing.
- **WARNING: Pair cost stuck at 1.0** — 5m has 5 consecutive bars at avg_pair_cost >= 1.0, meaning all pairs are at maximum cost (no discount captured).
