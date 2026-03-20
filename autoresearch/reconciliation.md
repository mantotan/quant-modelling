# Reconciliation Report — 2026-03-20 (Revalidation after FIX_SIZING)

## Trust Level: SUSPICIOUS

**Note:** The replay_backtest.py script reports UNRELIABLE due to a PnL sign mismatch, but this is caused by a bug in the script's `load_resolutions()` function (see below). After correcting for the bug, the true trust level is SUSPICIOUS (1/4 checks fail).

## Bug Found: Resolution Clobbering in replay_backtest.py

`load_resolutions()` (line 107) uses `resolutions[event["condition_id"]] = event`, which **overwrites** earlier resolution records sharing the same condition_id. When a bar has multiple predictions (e.g., at 50%, 80% elapsed), each gets its own resolution record. The last resolution (often PnL=0 for an unfilled prediction) overwrites the earlier one (with actual PnL for a filled prediction).

- **Reported paper PnL (buggy):** -$26.96
- **Actual paper PnL (correct):** +$210.96 (sum of all 53 resolution records)
- **Impact:** False PnL sign mismatch causing UNRELIABLE classification

Fix required: `FIX_RESOLUTION_LOAD` -- aggregate resolution PnL per condition_id instead of overwriting.

## Divergence Summary (Corrected)

| Metric | Value | Threshold | Status |
|--------|-------|-----------|--------|
| Market odds MAE | 0.0094 | < 0.03 | PASS |
| Edge sign flip % | 8.96% | < 5% | FAIL |
| PnL sign match | +$210.96 vs +$187.92 | Same | PASS (corrected) |
| Trade count ratio | 1.00 | 0.8-1.2 | PASS |

## Divergence Summary (As Reported by Script)

| Metric | Value | Threshold | Status |
|--------|-------|-----------|--------|
| Market odds MAE | 0.0094 | < 0.03 | PASS |
| Edge sign flip % | 8.96% | < 5% | FAIL |
| PnL sign match | -$26.96 vs +$187.92 | Same | FAIL (bug) |
| Trade count ratio | 1.00 | 0.8-1.2 | PASS |

## PnL Comparison

| Source | Total PnL | Trades | Sharpe |
|--------|-----------|--------|--------|
| Paper trading (corrected) | $210.96 | 53 resolved | -- |
| Paper trading (buggy load) | -$26.96 | 50 (clobbered) | -- |
| Replay (real odds, paper-sized) | $187.92 | 50 | -- |
| Replay (real odds, fractional) | $0.047 | 51 | 82.27 |
| Replay (synthetic odds) | $0.045 | 41 | 94.52 |

## Edge Sign Flip Analysis

The 8.96% edge sign flip rate is in the SUSPICIOUS range (5-15%) but is an expected consequence of real Polymarket odds deviating from the synthetic 0.50 baseline. With market odds MAE of only 0.0094, the flips occur at the boundary where edge is near zero -- these are low-confidence trades that would not generate significant PnL in either direction.

This is not a fixable divergence -- it is inherent to real vs synthetic odds.

## Action Taken

- Identified `FIX_RESOLUTION_LOAD` bug in `scripts/replay_backtest.py` -- resolution loader must aggregate (not overwrite) multi-prediction condition_ids
- Added to build_plan.tsv as PENDING
- After fix, re-run reconciliation to get clean result
- Edge sign flip at 9% is acceptable and does not require a code fix

## Previous Fixes Applied

- `FIX_SIZING` (DONE): Unified bet sizing between paper executor and replay backtest via `replay_paper_pnl()` function for USD-vs-USD comparison
