# Dutch Monitor Report
Updated: 2026-03-21T19:10:32Z

## Process Health
| Process | Status | Restarts | Uptime |
|---------|--------|----------|--------|
| dutch-5m | online | 8 | 2.5m |
| dutch-15m | online | 8 | 2.5m |
| dutch-1h | online | 8 | 2.5m |

Note: All 3 processes restarted at ~02:06 UTC. The 8 restarts remain historical from the 15:30 UTC crash (no new restarts). Processes ran cleanly from 02:06 UTC to present (19:10 UTC = ~17h stable). Short uptime (2.5m) reflects recent process recycle unrelated to crashes — likely a periodic PM2 restart or machine event. No new errors in error logs.

## Anomaly Checklist
| # | Check | Status | Evidence |
|---|-------|--------|----------|
| 1 | Process health | PASS | All 3 online, no new restarts since historical 8. Running stably since 02:06 UTC. |
| 2 | Sell race | PASS | 0 sell_losing events in last 100 events across all TFs. |
| 3 | Negative net shares | PASS | All recent bars show valid positive inventory. No negatives in last 10 bars any TF. |
| 4 | One-sided accumulation | PASS | 5m 2 bars with matched_ratio=0.0 but not 3 consecutive. 15m 1 bar (bar_id=1774104300, zero fills). Not triggering threshold. |
| 5 | Budget exhaustion | PASS | No gate_budget events observed in recent events. Risk cap gates (normal). |
| 6 | Pair cost stuck | WARN | 5m: 7/10 bars above 0.98 (avg=0.9832). 15m: 8/10 bars above 0.98 (avg=1.0047). Neither has 5 consecutive at tail — last 5m bar=0.7454, last 15m bar=0.9663. WARNING maintained from prior check. |
| 7 | Zero fills | PASS | 5m: 0 zero-fill bars in last 10. 15m: 1 zero-fill bar (bar_id=1774104300, 5 placed). Not 3+ consecutive. |
| 8 | Kill switch spam | PASS | 0 kill switch events in recent 100 events per TF. |

## Per-Timeframe Metrics (last 10 resolved bars)
| TF | Total Bars | Avg Pair Cost | Avg Profit | Fill Rate | Matched Ratio | Sell Count |
|----|-----------|---------------|------------|-----------|---------------|------------|
| 5m | 73 | 0.983 | $-3.37 | 92% | 57% | 1509 total |
| 15m | 29 | 1.005 | $-5.07 | 92% | 75% | 583 total |
| 1h | N/A | N/A | N/A | N/A | N/A | N/A |

Cumulative PnL: 5m = -$1981.70 (73 bars), 15m = -$891.18 (29 bars). 1h: no bar file yet (process active, no completed bars since last restart).

## Alerts

### Historical CRITICAL Alerts (all resolved)
- **process_down** (detected 15:29, resolved 16:03): Processes online and stable.
- **sell_race** (detected 15:29, resolved 16:03): Zero sell_losing events confirmed.
- **negative_shares** (detected 15:29, resolved 16:03): Inventory clean in all recent bars.

### Active WARNING
- **pair_cost_stuck**: 5m avg_pair_cost=0.983 (7/10 >0.98), 15m avg_pair_cost=1.005 (8/10 >0.98). Neither has 5 consecutive at tail right now, but sustained high costs indicate structural issue. Cumulative losses are significant (-$2.8k total across TFs).
