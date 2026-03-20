# Reconciliation Report — 2026-03-20

## Trust Level: UNRELIABLE

## Divergence Summary

| Metric | Value | Threshold | Status |
|--------|-------|-----------|--------|
| Market odds MAE | 0.0093 | < 0.03 | PASS |
| Edge sign flip % | 5.4% | < 5% | FAIL |
| PnL sign match | Paper=-$25.98 vs Replay=+$0.02 | Same | FAIL |
| Trade count ratio | 1.00 | 0.8-1.2 | PASS |

## PnL Comparison

| Source | Total PnL | Trades | Sharpe |
|--------|-----------|--------|--------|
| Paper trading | -$25.98 | 29 | -- |
| Replay (real odds) | $0.02 | 29 | 46.50 |
| Replay (synthetic) | $0.01 | 24 | 35.59 |

## Root Cause Analysis

The critical divergence is the **PnL sign mismatch**: paper trading shows -$25.98 while replay shows +$0.02. Key observations:

1. **Trade count is identical (29)** -- the same trades are being taken in both paths
2. **Market odds MAE is excellent (0.009)** -- odds alignment is not the issue
3. **Edge sign flip is marginal (5.4% vs 5% threshold)** -- not the primary driver
4. **PnL units differ dramatically** -- paper reports in real USD, replay in fractional units

This points to **FIX_SIZING**: bet sizing logic differs between the paper executor (using real dollar amounts) and the replay backtest (using fractional/unit sizing). The same directional bets produce opposite PnL outcomes due to different position sizing and cost accounting.

## Action Taken

Triggered **FIX_SIZING** (build_plan.tsv row 23): Unify bet sizing between paper executor and replay backtest. Phase set to `building` with sub_phase `reconciliation_fix_sizing`.

## Previous Fixes Applied

None -- this is the first reconciliation run.
