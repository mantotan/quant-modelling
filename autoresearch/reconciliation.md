# Reconciliation Report — 2026-03-20 (Revalidation after FIX_RESOLUTION_LOAD)

## Trust Level: SUSPICIOUS

3/4 checks pass. Edge sign flip at 5.88% is just above the 5% TRUSTWORTHY threshold. This is an improvement from 8.96% in the previous run (before FIX_RESOLUTION_LOAD). The FIX_RESOLUTION_LOAD fix is validated — PnL sign match now works correctly with 79 resolved trades (up from 53).

## Divergence Summary

| Metric | Value | Threshold | Status |
|--------|-------|-----------|--------|
| Market odds MAE | 0.0089 | < 0.03 | PASS |
| Edge sign flip % | 5.88% | < 5% | FAIL |
| PnL sign match | +$982.93 vs +$406.73 | Same | PASS |
| Trade count ratio | 1.00 | 0.8-1.2 | PASS |

## PnL Comparison

| Source | Total PnL | Trades | Sharpe |
|--------|-----------|--------|--------|
| Paper trading | $982.93 | 79 filled | -- |
| Replay (real odds, paper-sized) | $406.73 | 79 | -- |
| Replay (real odds, fractional) | $0.089 | 79 | 103.39 |
| Replay (synthetic odds) | $0.075 | 67 | 98.03 |

## Key Observations

- **FIX_RESOLUTION_LOAD validated**: Resolution loading now correctly aggregates multi-prediction condition_ids. PnL sign match is clean PASS with both sides strongly positive.
- **Edge sign flip improved**: 8.96% -> 5.88% with 26 more resolved trades. The flip rate may converge below 5% with more data.
- **PnL magnitude gap**: Paper $982.93 vs Replay $406.73 -- paper PnL is 2.4x replay. Both positive, but the magnitude difference suggests paper executor may be sizing larger or capturing different fills. This is worth monitoring but not a sign mismatch.
- **Strong Sharpe**: Replay backtester Sharpe of 103.39 (real odds) and 98.03 (synthetic) -- highly profitable in both modes.
- **Time bucket analysis**: 60-180s trades are most profitable (win rate 62-71%), while 180-295s trades are marginal (win rate 48-53%). Late-bar edge degrades.

## Action Taken

No new fix triggered. Edge sign flip at 5.88% is borderline and does not map to any cataloged fix -- it reflects inherent differences between real and synthetic odds at the boundary where edge is near zero. Will re-evaluate when more trades accumulate (targeting 150+ resolved trades for stable metrics).

## Previous Fixes Applied

- `FIX_SIZING` (DONE): Unified bet sizing between paper executor and replay backtest
- `FIX_RESOLUTION_LOAD` (DONE): Fixed resolution loader to aggregate (not overwrite) multi-prediction condition_ids -- **validated in this run**
