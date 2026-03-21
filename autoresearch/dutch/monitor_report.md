# Dutch Monitor Report
Updated: 2026-03-22T00:30:00Z

## Mode
sub_phase=replay_available — PM2 health check skipped per spec; bar summaries read from dutch_backtest/ and dutch_paper/.

## Process Health
| Process | Status | Notes |
|---------|--------|-------|
| dutch-5m | N/A (replay) | Paper log active: 118 bars total |
| dutch-15m | N/A (replay) | Paper log: 44 bars, Backtest: 53 bars |
| dutch-1h | N/A (replay) | Events only, 0 bars filled yet |

## Anomaly Checklist
| # | Check | Status | Evidence |
|---|-------|--------|----------|
| 1 | Process health | SKIP | replay_available mode |
| 2 | Sell race | PASS | 0 sell_losing events in last 100 events across all TFs |
| 3 | Negative net shares | PASS | 0 bars with negative up_shares or dn_shares across all TFs |
| 4 | One-sided accumulation | PASS | Max consec one-sided = 2 (threshold = 3) |
| 5 | Budget exhaustion | PASS | No early budget exhaustion gate events |
| 6 | Pair cost stuck | WARNING | 5m paper: 4/5 active bars >0.98 (avg=1.034); 15m paper: 8/10 >0.98 (consec=4, avg=1.028). UNRESOLVED. |
| 7 | Zero fills | PASS | 0 consecutive zero-fill bars |
| 8 | Kill switch spam | PASS | 0 kill switch events in last 100 events |

## Per-Timeframe Metrics (last 10 bars)
| TF | Source | Total Bars | Active/10 | Avg Pair Cost | Avg Profit | Fill Rate | Matched Ratio | Total PnL |
|----|--------|-----------|-----------|---------------|------------|-----------|---------------|-----------|
| 5m | paper | 118 | 5/10 | 1.034 | -$0.92 | 90.0% | 0.21 | -$2147.27 |
| 15m | paper | 44 | 9/10 | 1.028 | -$6.17 | 86.1% | 0.58 | -$977.28 |
| 15m | backtest | 53 | 10/10 | 0.951 | -$2.57 | 90.0% | 0.71 | -$296.82 |
| 1h | paper | 0 | 0/0 | N/A | N/A | N/A | N/A | N/A |

### Recent Bar-Level Pair Costs

**BTC_5m paper (last 10 bars, active only):**
bar=1774130700 cost=1.090, bar=1774131000 cost=1.040, bar=1774131300 cost=1.000 (unmatched),
bar=1774132800 cost=1.000 (unmatched), bar=1774133400 cost=1.040

**BTC_15m paper (last 10 bars):**
bar=1774124100 cost=1.000 (skip), bar=1774125000 cost=1.000, bar=1774125900 cost=1.232,
bar=1774126800 cost=0.789, bar=1774127700 cost=1.201, bar=1774128600 cost=1.023,
bar=1774129500 cost=0.994, bar=1774130400 cost=1.049, bar=1774131300 cost=0.947, bar=1774132200 cost=1.020

**BTC_15m backtest (last 10 bars):**
0.784, 0.997, 1.065, 0.939, 1.016, 0.990, 0.850, 0.955, 0.888, 1.022

### Key Observations
1. **pair_cost_stuck WARNING persists**: 5m paper avg=1.034 (4/5 active bars >0.98). 15m paper avg=1.028 (8/10 >0.98, consec=4). Resolution requires 5 consecutive active bars all <0.98 — not yet met.
2. **Backtest outperforming paper**: 15m backtest avg=0.951 vs 15m paper=1.028. V7 engine (conviction sell, adaptive pair cost) producing better pair cost in backtest than live paper.
3. **No CRITICAL anomalies**: sell race fix holding, inventory clean, no kill switches.
4. **BTC_1h**: No bars yet — 1h windows are long, may not have completed any trades.
5. **Cumulative PnL**: 5m -$2147.27 (118 bars), 15m paper -$977.28 (44 bars), 15m backtest -$296.82 (53 bars). Paper losses driven by high pair cost; backtest losses smaller and improving.
6. **Low matched ratio on 5m (0.21)**: Many recent 5m bars are unmatched single-side positions, contributing to losses. Dutch engine struggling to get both sides matched in 5m bar windows.

## Alerts

### Historical CRITICAL Alerts (all resolved)
- **process_down** (detected 2026-03-21T15:29, resolved 16:03): All processes were online.
- **sell_race** (detected 2026-03-21T15:29, resolved 16:03): 0 sell_losing events confirmed.
- **negative_shares** (detected 2026-03-21T15:29, resolved 16:03): Inventory clean.

### Active WARNING
- **pair_cost_stuck** (detected 2026-03-21T16:03:44Z, UNRESOLVED): BTC_5m paper avg=1.034 (4/5 active >0.98). BTC_15m paper avg=1.028 (8/10 >0.98, 4 consec). Backtest improving (avg=0.951). Resolution requires 5 consecutive active bars all <0.98.
