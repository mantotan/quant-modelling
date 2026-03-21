# Dutch Monitor Report
Updated: 2026-03-22T06:15:00Z

## Process Health
| Process | Status | Restarts | Uptime |
|---------|--------|----------|--------|
| dutch-5m | N/A (replay_available mode) | — | — |
| dutch-15m | N/A (replay_available mode) | — | — |
| dutch-1h | N/A (replay_available mode) | — | — |

Note: sub_phase=replay_available — PM2 process checks skipped per spec. BTC_15m backtest data
in `data/dutch_backtest/BTC_15m/`. Live paper data from `data/dutch_paper/`.

## Anomaly Checklist
| # | Check | Status | Evidence |
|---|-------|--------|----------|
| 1 | Process health | SKIP | replay_available mode — no live processes to check |
| 2 | Sell race | PASS | 0 sell_race pairs across all TFs in last 100 events. BTC_5m_paper=0, BTC_15m_paper=0, BTC_15m_backtest=0 |
| 3 | Negative net shares | PASS | All bars: neg_up=0, neg_dn=0 across all TFs |
| 4 | One-sided accumulation | PASS | BTC_5m last-10: 3 resolved only (matched_ratio=27.8%). BTC_15m paper: 36.4%. No 3 consecutive resolved bars below 0.20 |
| 5 | Budget exhaustion | PASS | No kill switch events. Gate events (risk_cap) are normal. No early budget exhaustion. |
| 6 | Pair cost stuck | WARNING | BTC_5m paper: 3/5 recent resolved >0.98 (recent avg=1.043). BTC_15m paper: 4/5 recent resolved >0.98 (avg=1.026). BTC_15m backtest: 2/5 (avg=0.951, improving). Existing WARNING carries forward. |
| 7 | Zero fills | INFO | BTC_5m: 7/10 bars had 0 orders placed — gate-blocked or no signal, not a fill failure. Fill rate on bars with orders=83.3% (PASS). |
| 8 | Kill switch spam | PASS | 0 kill switch events across all TFs |

## Per-Timeframe Metrics (last 10 resolved bars)
| TF | Source | Bars | Resolved | Avg Pair Cost | Avg Profit | Fill Rate | Matched Ratio | Sell Count |
|----|--------|------|----------|---------------|------------|-----------|---------------|------------|
| 5m | paper | 10 | 3 | 1.043 | $-3.67 | 83.3% | 27.8% | 0 |
| 15m | paper | 10 | 9 | 1.026 | $-7.66 | 82.8% | 36.4% | 7 |
| 15m | backtest | 10 | 10 | 0.951 | $-2.57 | 91.0% | 39.8% | 7 |
| 1h | paper | N/A | N/A | N/A | N/A | N/A | N/A | N/A (no bars file) |

## Full-Session Stats
| TF | Source | Total Bars | Resolved | Total Profit | Overall Avg Cost | Stuck Episodes |
|----|--------|-----------|----------|-------------|-----------------|----------------|
| 5m | paper | 115 | 98 | $-2,149.11 | 0.631 | 19 |
| 15m | paper | 43 | 40 | $-975.12 | 0.857 | 3 |
| 15m | backtest | 53 | 53 | $-296.82 | 0.969 | 1 |

Note: BTC_5m overall avg_cost=0.631 reflects large proportion of pre-fix (V6/V7 transition) bars with
healthy costs. Recent last-3 resolved bars avg=1.043 shows deterioration. Session losses include early
sell_race and negative_shares period that has since been resolved.

BTC_15m backtest avg_cost=0.969 vs prior WARNING of 1.005 — modest improvement under new params.

## Alerts

### Historical CRITICAL Alerts (all resolved)
- **process_down** (detected 2026-03-21T15:29, resolved 16:03): Resolved.
- **sell_race** (detected 2026-03-21T15:29, resolved 16:03): 0 sell_losing events confirmed.
- **negative_shares** (detected 2026-03-21T15:29, resolved 16:03): Inventory clean.

### Active WARNING
- **pair_cost_stuck** (detected 2026-03-21T16:03:44Z, unresolved): BTC_5m recent 3/5 >0.98
  (avg=1.043). BTC_15m paper 4/5 >0.98 (avg=1.026). BTC_15m backtest improving at 2/5 (avg=0.951).
  Criteria for resolution: 5 consecutive resolved bars all below 0.98 — not yet met on paper TFs.
