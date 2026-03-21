# Dutch Monitor Report
Updated: 2026-03-21T16:03:44Z

## Process Health
| Process | Status | Restarts | Uptime |
|---------|--------|----------|--------|
| dutch-5m | online | 8 | 34m |
| dutch-15m | online | 8 | 34m |
| dutch-1h | online | 8 | 34m |

Note: 8 restarts are historical from the ~15:30 UTC crash (exit_code=1). All processes have been stable for 34m with no new crashes. The sell race fix from commit 4ac2d2c is confirmed active.

## Anomaly Checklist
| # | Check | Status | Evidence |
|---|-------|--------|----------|
| 1 | Process health | PASS | All 3 online, 34m uptime, no active crash activity. |
| 2 | Sell race | PASS | 0 sell_losing events in last 100 events across all TFs. Prior CRITICAL alert predated sell-race fix. |
| 3 | Negative net shares | PASS (recent) | Historical negatives: 5m 8 bars (bar_id<=1774085700), 15m 2 bars (bar_id<=1774088100). All recent bars clean. Root cause was sell race, fixed. |
| 4 | One-sided accumulation | PASS | 5m matched_ratio=57.4%, 15m matched_ratio=75.4%. Both well above 20% threshold. |
| 5 | Budget exhaustion | PASS | No gate_budget events in recent events; active gates are gate_risk_cap (normal). |
| 6 | Pair cost stuck | WARN | 15m avg_pair_cost=1.005, 8/10 consecutive bars >0.98. Consistently above breakeven. |
| 7 | Zero fills | PASS | 5m: 0 zero-fill bars in last 10. 15m: 1 zero-fill bar (bar_id=1774104300, 5 expired). Not 3+ consecutive. |
| 8 | Kill switch spam | PASS | 0 kill switch events in recent 100 events per TF. |

## Per-Timeframe Metrics (last 10 resolved bars)
| TF | Total Bars | Avg Pair Cost | Avg Profit | Fill Rate | Matched Ratio | Sell Count |
|----|-----------|---------------|------------|-----------|---------------|------------|
| 5m | 73 | 0.983 | $-3.37 | 84.7% | 57.4% | 6/10 |
| 15m | 29 | 1.005 | $-5.07 | 85.5% | 75.4% | 8/10 |
| 1h | N/A | N/A | N/A | N/A | N/A | N/A |

Note: 1h has no resolved bars yet (process started mid-bar 1774108800).

## Alerts

### Previous CRITICAL Alerts (all resolved)
- **process_down** (detected 15:29): RESOLVED. All 3 processes online, stable 34m uptime.
- **sell_race** (detected 15:29): RESOLVED. Zero sell_losing events in recent 100 events per TF. Sell race fix confirmed active.
- **negative_shares** (detected 15:29): RESOLVED in recent bars. Historical negatives from pre-fix session only (bar_ids before ~1774086000). Current inventory accounting clean.

### Active WARNING
- **pair_cost_stuck (15m)**: avg_pair_cost=1.005 across last 10 bars, 8/10 consecutive bars above 0.98 threshold. Consistently above breakeven — pair cost above 1.00 guarantees net losses. Consider tightening max_side_fraction on 15m.
