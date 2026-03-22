# Dutch Monitor Report
Updated: 2026-03-22T07:26:47Z

## Mode
Backtest replay (`sub_phase=replay_available`). PM2 health check skipped per spec. Bar summaries read from `data/dutch_backtest/BTC_15m/`.

## Process Health
| Process | Status | Notes |
|---------|--------|-------|
| dutch-5m | N/A (replay) | Backtest only TF available: BTC_15m |
| dutch-15m | N/A (replay) | 53 bars logged in dutch_backtest/ |
| dutch-1h | N/A (replay) | No backtest data for 5m or 1h |

## Anomaly Checklist
| # | Check | Status | Evidence |
|---|-------|--------|----------|
| 1 | Process health | SKIP | replay_available mode — no live processes |
| 2 | Sell race | PASS | 0 sell_losing events in 5577 total events; 0 sell-type events across all 53 bars |
| 3 | Negative net shares | PASS | 0 bars with negative up_shares, dn_shares, or total_cost in all 53 bars |
| 4 | One-sided accumulation | PASS | Max consecutive matched_ratio <0.20 = 2 (threshold: 3+); last 3 matched ratios = [0.441, 0.989, 0.879] |
| 5 | Budget exhaustion | PASS | 0 budget-exhaustion gate events detected in 5577-event log |
| 6 | Pair cost stuck | WARNING (active) | 28/53 bars >0.98 avg_pair_cost; max consecutive in full history = 5 (trigger threshold = 5). Last 10: 5/10 >0.98, only 1 consecutive at end. Avg last 10 = 0.9505 — improving vs prior sessions. |
| 7 | Zero fills | PASS | 0 bars with orders_placed>0 and orders_filled=0 across 53 bars |
| 8 | Kill switch spam | PASS | 0 kill switch events in full event log |

## Per-Timeframe Metrics (last 10 resolved bars)
| TF | Bars | Avg Pair Cost | Avg Profit | Fill Rate | Matched Ratio | Sell Count |
|----|------|---------------|------------|-----------|---------------|------------|
| 15m (backtest) | 10 | 0.9505 | $-2.57 | 91.0% | 70.7% | 0 |
| 5m | N/A | — | — | — | — | — |
| 1h | N/A | — | — | — | — | — |

## Full Backtest Summary (BTC_15m, 53 bars)
- Total bars: 53
- Avg pair cost (all): 0.9688
- Total profit: $-296.82
- Bars >0.98 pair cost: 28/53 (52.8%)
- Max consecutive >0.98: 5
- Zero fill bars: 0
- Negative share bars: 0
- sell_losing events: 0
- Kill switch events: 0

## Last 10 Bars Detail (BTC_15m backtest)
| bar_id | outcome | avg_pair_cost | profit | fill_rate | matched_ratio |
|--------|---------|---------------|--------|-----------|---------------|
| 1774121400 | DN | 0.7839 | $-9.96 | 100.0% | 15.8% |
| 1774122300 | UP | 0.9970 | $-3.10 | 74.5% | 89.4% |
| 1774123200 | DN | 1.0648 | $+10.01 | 97.8% | 55.4% |
| 1774124100 | UP | 0.9388 | $-8.56 | 94.7% | 56.5% |
| 1774125000 | DN | 1.0165 | $+1.91 | 89.9% | 94.8% |
| 1774125900 | DN | 0.9896 | $-10.18 | 93.3% | 84.0% |
| 1774126800 | DN | 0.8497 | $+1.41 | 94.1% | 80.1% |
| 1774127700 | DN | 0.9547 | $-21.33 | 87.0% | 44.1% |
| 1774128600 | DN | 0.8879 | $+16.40 | 90.7% | 98.9% |
| 1774129500 | DN | 1.0221 | $-2.35 | 87.5% | 87.9% |

## Alerts

### Active WARNING
- **pair_cost_stuck** (detected 2026-03-21T16:03:44Z, UNRESOLVED): In full 53-bar history, max consecutive
  avg_pair_cost >0.98 = 5 (threshold = 5). Last 10 bars show improvement: avg=0.9505, only 1 consecutive
  at end. Resolution requires 5 consecutive bars all <0.98 — not yet met.

### Resolved CRITICAL Alerts
- **process_down** (resolved 2026-03-21T16:03:44Z): N/A in replay mode, confirmed no crashes.
- **sell_race** (resolved 2026-03-21T16:03:44Z): 0 sell_losing events in full backtest log — confirmed.
- **negative_shares** (resolved 2026-03-21T16:03:44Z): 0 negative-share bars in backtest — confirmed.

## Key Observations

1. **pair_cost_stuck improving but not resolved**: Last 10-bar avg_pair_cost dropped to 0.9505 (vs 0.951
   last check). Three bars below 0.90 in last 10 (0.784, 0.850, 0.888). Only 1 consecutive >0.98 at end.
   Trending toward resolution but 5-consecutive <0.98 streak not achieved yet.

2. **Large profit swings**: Last 10 bars span $-21.33 to $+16.40. High variance in per-bar P&L is
   expected at current matched share levels. Net -$25.26 over last 10 bars, cumulative -$296.82 (53 bars).

3. **Fill rate healthy**: 91.0% fill rate in last 10 bars. No zero-fill bars across all 53.

4. **Matched ratio volatile**: Ranges 0.158 to 0.989 in last 10. Single bar at 15.8% (below 20% threshold)
   but not 3+ consecutive — PASS.

5. **No sells firing**: 0 sell events across 5577 event entries. This is consistent with prior monitor
   observations — sell thresholds not being reached in backtest conditions.
