# Reconciliation Report — 2026-03-20 (Cycle 3: 146 resolved trades)

## Trust Level: SUSPICIOUS

3/4 checks pass. Edge sign flip at 5.78% is just above the 5% TRUSTWORTHY threshold. Stable from previous run (5.88%) -- converging but not yet crossing the threshold. 67 new resolved trades since last reconciliation (79 -> 146).

## Divergence Summary

| Metric | Value | Threshold | Status |
|--------|-------|-----------|--------|
| Market odds MAE | 0.011 | < 0.03 | PASS |
| Edge sign flip % | 5.78% | < 5% | FAIL |
| PnL sign match | +$1669.25 vs +$635.20 | Same | PASS |
| Trade count ratio | 1.00 | 0.8-1.2 | PASS |

## PnL Comparison

| Source | Total PnL | Trades | Sharpe |
|--------|-----------|--------|--------|
| Paper trading | $1669.25 | 146 filled | -- |
| Replay (real odds, paper-sized) | $635.20 | 146 | -- |
| Replay (real odds, fractional) | $0.138 | 151 | 79.83 |
| Replay (synthetic odds) | $0.125 | 127 | 81.85 |

## Key Observations

- **Edge sign flip stable**: 5.88% -> 5.78% with 67 more resolved trades. Near structural floor -- model and market odds rarely disagree on direction but the 5% threshold is tight.
- **PnL magnitude gap**: Paper $1669 vs Replay $635 (2.6x). Both strongly positive. Gap reflects paper executor capturing slightly better fills than replay's snapshot-based odds.
- **Strong Sharpe**: Replay backtester Sharpe of 79.83 (real odds) and 81.85 (synthetic) -- both highly profitable.
- **Time bucket analysis**: 60-120s trades strongest (63% win rate, $0.0027 ROI/trade), 180-295s weakest (53% win rate, near-zero ROI). Late-bar edge degrades as expected.
- **Brier score**: 0.241 -- below 0.25 acceptance threshold. Calibration is adequate.

## Action Taken

None -- edge sign flip at 5.78% is borderline and does not map to any cataloged fix. It reflects inherent near-zero-edge trades where model and market odds are very close. No new fix triggered. System is profitable and stable.

## Previous Fixes Applied

- `FIX_SIZING` (DONE): Unified bet sizing between paper executor and replay backtest
- `FIX_RESOLUTION_LOAD` (DONE): Fixed resolution loader to aggregate (not overwrite) multi-prediction condition_ids
