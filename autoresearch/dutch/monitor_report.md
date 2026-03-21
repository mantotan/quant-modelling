# Dutch Monitor Report
Updated: 2026-03-21T22:56:53Z

## Mode
sub_phase=replay_available — PM2 health check skipped per spec; bar summaries read from dutch_backtest/ and dutch_paper/. PM2 queried for informational status only.

## Process Health
| Process | Status | Restarts | Notes |
|---------|--------|----------|-------|
| dutch-5m | online | 9 | (replay mode — informational only) |
| dutch-15m | online | 10 | (replay mode — informational only) |
| dutch-1h | online | 9 | (replay mode — informational only) |

All 3 dutch processes online per PM2 jlist.

## Anomaly Checklist
| # | Check | Status | Evidence |
|---|-------|--------|----------|
| 1 | Process health | SKIP/INFO | replay_available mode; PM2 shows 3/3 online |
| 2 | Sell race | PASS | 0 sell_losing events in last 100 events for 5m and 15m |
| 3 | Negative net shares | PASS | No negative up_shares or dn_shares in any TF |
| 4 | One-sided accumulation | PASS | 5m: 2 consec below 0.20 (need 3+); 15m paper: 0 consec; backtest: 0 consec |
| 5 | Budget exhaustion | PASS | No early budget exhaustion gate events detected |
| 6 | Pair cost stuck | WARNING | 5m paper: 9/10 active bars >0.98 (avg=1.036, 4 consec); 15m paper: 8/10 >0.98 (avg=1.025, 1 consec). NOT YET RESOLVED. |
| 7 | Zero fills | PASS | 0 consecutive zero-fill bars (bars with orders_placed>0 and orders_filled=0) |
| 8 | Kill switch spam | PASS | 0 kill switch events in last 100 events |

## Per-Timeframe Metrics (last 10 active bars)
| TF | Source | Total Bars | Active Bars | Avg Pair Cost | Total PnL | Fill Rate | Notes |
|----|--------|-----------|-------------|---------------|-----------|-----------|-------|
| 5m | paper | 117 | 99 | 1.036 (recent 10) | -$2148.71 | ~85% | pair_cost_stuck |
| 15m | paper | 44 | 41 | 1.025 (recent 10) | -$977.28 | ~86% | pair_cost_stuck |
| 15m | backtest | 53 | 53 | 0.951 (recent 10) | -$296.82 | ~90% | improving |
| 1h | paper | — | — | — | — | — | no bars file (no fills yet) |

### Recent Pair Costs (last 10 active bars)
- **BTC_5m paper**: [1.00, 1.22, 1.00, 1.005, 1.03, 0.975, 1.09, 1.04, 1.00, 1.00]
- **BTC_15m paper**: [0.997, 1.00, 1.232, 0.789, 1.201, 1.023, 0.994, 1.049, 0.947, 1.020]
- **BTC_15m backtest**: [0.784, 0.997, 1.065, 0.939, 1.017, 0.990, 0.850, 0.955, 0.888, 1.022]

### Key Observations
1. **pair_cost_stuck WARNING persists**: 5m paper avg=1.036 (9/10 active bars >0.98), 4 consecutive stuck. Not yet resolved.
2. **Backtest outperforming paper**: 15m backtest avg_pair_cost=0.951 vs 15m paper=1.025. V7 engine (conviction sell, adaptive pair cost) produces better pair cost in backtest environment than paper.
3. **No CRITICAL anomalies**: sell race fix is holding, no negative inventory.
4. **BTC_1h paper**: No bars file exists — 1h process has not yet executed any fills.
5. **Cumulative PnL losses are large on paper**: 5m -$2148.71, 15m -$977.28 (includes pre-fix period losses). Backtest -$296.82 on 53 bars.
6. **One-sided accumulation not triggered**: 5m shows 2 consecutive single-sided bars (below threshold of 3).

## Alerts

### Historical CRITICAL Alerts (all resolved)
- **process_down** (detected 2026-03-21T15:29, resolved 16:03): All processes online.
- **sell_race** (detected 2026-03-21T15:29, resolved 16:03): 0 sell_losing events confirmed.
- **negative_shares** (detected 2026-03-21T15:29, resolved 16:03): Inventory clean.

### Active WARNING
- **pair_cost_stuck** (detected 2026-03-21T16:03:44Z, UNRESOLVED): BTC_5m paper 9/10 >0.98 (avg=1.036, 4 consec). BTC_15m paper 8/10 >0.98 (avg=1.025). Resolution requires 5 consecutive active bars all <0.98 — not yet met on any paper TF. Backtest improving (avg=0.951, 5/10 stuck).
