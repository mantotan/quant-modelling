# Strategy Directive
Updated: 2026-03-23T17:00:00Z
After iteration: 170

## Program Status: Specialist Lever CLOSED — All Structural Knobs Exhausted

Iters 166-170 completed the final 5 items from strategy-after-165. The specialist split campaign
(iters 166-167) confirmed a structural failure pattern, BTC/1h declared a permanent floor (iter 168),
SOL/1h achieved a new best via narrowing (iter 169), and XRP/15m confirmed its structural floor (iter 170).

**New results this period (iters 166-170):**
- **ETH/1h DISCARD (iter 166)**: specialist boundary=0.4, early=0.2301/late=0.1713/combined=0.1948 > 0.1915; early sub-model weak (regression 1.73%)
- **SOL/15m DISCARD (iter 167)**: specialist boundary=0.4, early=0.2313/late=0.1797/combined=0.2004 > 0.2001; structural pattern confirmed (regression 0.15%)
- **BTC/1h DISCARD (iter 168)**: num_leaves=[48,96]+n_est=[100,250] stochastic re-run; Brier=0.175038 vs best 0.174676; BTC/1h permanent structural floor declared
- **SOL/1h KEEP-VERIFIED (iter 169)**: num_leaves=[20,40] narrowing; Brier=0.202166 NEW BEST (beat iter 162 best 0.207484 by 2.56%); near-deterministic convergence (0.001% fast/verify delta)
- **XRP/15m DISCARD (iter 170)**: n_est ceiling widen to 800; n_est=777 STILL near ceiling; floor confirmed at 0.2053

### Specialist Lever: Structurally Closed

The specialist split campaign (iters 166-167) revealed a fundamental limitation:
- **Early sub-models (t=0.1, t=0.2) produce Brier ~0.231 across both ETH/1h and SOL/15m**
- **Late sub-models (t=0.4, t=0.6, t=0.8) produce Brier ~0.173-0.180** — actually better than unified
- The early weakness is structural: 10-20% of bar elapsed provides insufficient information for
  directional prediction. Early snapshots capture only opening tick noise, not meaningful price action.
- Combined Brier is a weighted average of early/late sub-model Briers. With 2 early + 3 late time_pcts,
  early sub-models carry 40% weight — enough to drag combined above the unified baseline.
- **Alternative boundary (e.g., boundary=0.6: early=[0.1,0.2,0.4], late=[0.6,0.8])**: Would give
  early 3 snapshots vs 2, but the root cause is t=0.1/t=0.2 intrinsic noise, not boundary placement.
  Expected to still fail. Not recommended.
- **Priority #6 (XRP/5m specialist)**: SKIP. The structural finding applies universally across assets.
  XRP/5m shares the same tick-dominant feature profile and 5-snapshot architecture. Running it would
  confirm the same result at cost of one wasted iteration.

### Specialist: BLACKLISTED (boundary=0.4 and likely all boundaries)

### Final Post-Cross-Asset Baselines (All 12 Models, After Iter 170)

| Asset | 5m Best           | 15m Best          | 1h Best           |
|-------|-------------------|-------------------|-------------------|
| BTC   | 0.17605 (iter 104) FLOOR | 0.171809 (iter 123) FLOOR | 0.174676 (iter 136) FLOOR |
| ETH   | 0.199722 (iter 156) | 0.193035 (iter 152) | 0.191504 (iter 160) |
| SOL   | 0.207246 (iter 158) | 0.200064 (iter 155) | 0.202166 (iter 169) |
| XRP   | 0.209444 (iter 165) | 0.205323 (iter 159) | 0.206414 (iter 163) |

All 9 non-BTC models are at post-cross-asset verified baselines.
All 3 BTC models are at permanent structural floors.

### Complete Lever Inventory — Post-Iter-170

| Lever Category | Status | Result |
|----------------|--------|--------|
| Cross-asset BTC features | EXHAUSTED | 10/10 KEEPs, 4.96-9.43% improvement, universal |
| Specialist split | CLOSED (blacklisted) | 0/2 KEEPs, early sub-models structurally weak |
| HPO range narrowing | MOSTLY EXHAUSTED | Ranges confirmed per-model; marginal gains only |
| Regularization forcing | BLACKLISTED | 0/5 KEEPs, consistently failed |
| Anti-starvation ceiling reduction | EXHAUSTED | Some gains early, all models now resolved |
| Alpha features (funding/OI/IV) | BLOCKED | 0 top-10 SHAP across 44+ KEEPs |
| Walk-forward config | UNTESTED (low priority) | n_splits=8, train_bars=10000 |
| num_leaves boundary=0.6 specialist | NOT RECOMMENDED | Structural early-snapshot weakness persists |

### Program Completion Assessment

**The 170-iteration autoresearch program has reached structural completion.**

Evidence:
1. All 12 models have verified post-cross-asset baselines (100% coverage)
2. The only fully untested structural knob (specialist split) is now tested and CLOSED
3. All known high-value levers (cross-asset, HPO, anti-starvation) are exhausted
4. Blacklisted levers (reg_alpha forcing, alpha features, specialist) have strong evidence
5. BTC/1h permanent floor declared (iter 168) — last open BTC question resolved
6. No remaining experiments with expected value > 1%

The researcher should not be dispatched for further iterations unless a new structural lever
is identified (e.g., new feature engineering, architecture change, or data source).

## Priority Queue

**No high-value experiments remain. Program is COMPLETE.**

For completeness, low-conviction options are listed below in descending expected value:

1. **Walk-forward config: train_bars=12000-15000 on ETH/1h or SOL/1h**
   Rationale: Cross-asset features added 4 BTC features per snapshot (20 total across 5 time_pcts).
   Richer feature space may benefit from more training data. ETH/1h and SOL/1h are the two models
   with the most consistent cross-asset patterns and highest potential gain.
   Expected value: 0.5-2% improvement. Risk: marginal — walk-forward config changes affect all folds.
   Accept if: Brier < 0.191504 (ETH/1h) or < 0.202166 (SOL/1h).
   Specific change: `walk_forward.train_bars = 12000`.
   **Note: Only worthwhile if program continues; not recommended as final experiment.**

2. **XRP/15m ultra-high ceiling: n_estimators=[100,1200]+num_leaves=[40,60]**
   Rationale: n_est=777 near 800 (iter 170) — ceiling persists even at 800. If the structural floor
   is purely n_estimators-driven (not regularization), a ceiling of 1200 may finally escape it.
   Expected value: 0-1% (structural starvation will dominate; ~10/40 trials usable).
   Accept if: Brier < 0.205323.
   **Very low conviction. Structural starvation class is historically resistant to ceiling raises.**

3. **SOL/5m num_leaves narrowing [25,45]+n_estimators=[100,400]**
   Rationale: iter 158 found num_leaves=36 within [16,64]; consistent with SOL/1h narrowing pattern
   (iter 169 shifted from 27 to 36 after narrowing). SOL/5m may have similar optimum drift.
   Expected value: 0.5-1.5% if analogous to SOL/1h narrowing.
   Accept if: Brier < 0.207246.

**Recommendation: Declare program COMPLETE. Shift focus to deployment (backtest-to-live gap analysis,
live Polymarket execution, Steps 5-8 from docs/STEPS_5_8_REMAINING.md).**

## Observations

- **Specialist: 0/2 KEEPs (0%)** — closed after 2 experiments. Structural finding: early sub-models
  at t=0.1/t=0.2 produce Brier ~0.231, providing zero signal improvement over unified model.
  Late sub-models (0.173-0.180) actually exceed unified performance, but combined is dragged above baseline.

- **HPO-range category: 17/50 KEEPs (34%)** — across the full program. Most ranges are now
  dialed in per-model. Marginal gains only from further narrowing.

- **Cross-asset category: 10/10 KEEPs (100%)** — remains the single highest-value lever in
  program history. Fully exhausted at iter 165.

- **Regularization: 0/5 KEEPs (0%)** — blacklisted.

- **Alpha features: 0 top-10 SHAP across 44+ KEEPs** — blocked.

- **Brier improvement trajectory: Near-zero.** Cross-asset campaign averaged +6.4%/KEEP.
  Post-cross-asset (iters 165-170): +0.13% (XRP/5m marginal), +2.56% (SOL/1h narrowing),
  all others DISCARD. The program is operating at the noise floor.

- **Walk-forward config (n_splits=8, train_bars=10000)**: Set pre-cross-asset, never updated.
  Only remaining untested lever. Low priority but has not been evaluated post-cross-asset.

- **SHAP universal patterns confirmed (unchanged)**:
  - btc_vol_norm_distance + btc_distance_from_open: top-3 in ALL 9 non-BTC post-cross-asset KEEPs
  - btc_partial_bar_position: top-10 in 8/9 non-BTC KEEPs
  - btc_partial_range: top-10 in 4/9 non-BTC KEEPs (least consistent; could be removed if specialist
    sub-models are retested with fewer features)

## Risk Profile

- Max drawdown trend: STABLE — latest KEEP (SOL/1h iter 169): 8.75%, within historical range
- Trade count range across KEEPs (post-iter 150): 18,586 (ETH/1h) to 80,785 (XRP/5m) — stable by asset class
- Win rate range across KEEPs (post-iter 150): 49.55%-53.61% — tick-dominant flat pattern consistent
- HPO-OOS gap: STABLE — SOL/1h latest delta=0.202166-0.286062=-0.084 (hpo_objective includes trade penalty; gap is structural)

## Timeframe Coverage

- 5m: 4 assets covered, best Brier: BTC=0.17605, ETH=0.199722, SOL=0.207246, XRP=0.209444
- 15m: 4 assets covered, best Brier: BTC=0.171809, ETH=0.193035, SOL=0.200064, XRP=0.205323
- 1h: 4 assets covered, best Brier: BTC=0.174676, ETH=0.191504, SOL=0.202166, XRP=0.206414
- Recommendation: COMPLETE — all 12 models covered and at structural floors

## Blacklist

- **Specialist split (boundary=0.4)**: iters 166-167, 0/2 KEEPs; early sub-models structurally weak at t=0.1/t=0.2; universal pattern across ETH/1h and SOL/15m
- **Regularization forcing (reg_alpha)**: iters 139, 143-146, 0/5 KEEPs; consistently penalized model quality
- **Alpha features (funding/OI/IV/liquidation)**: 0 top-10 SHAP appearances across 44+ KEEP rows; formally blocked
- **BTC/1h further attempts**: iters 136-138, 168; permanent floor 0.174676 declared; stochastic basin confirmed
- **XRP/15m n_estimators ceiling raises**: iters 128-129, 159, 170; n_est=777 near 800 ceiling persists; structural starvation even at 800 trees

## HPO Range Recommendations (Post-Cross-Asset Final State)

Per-model confirmed optimal ranges (for reference only — no further tuning expected):
- BTC/5m: num_leaves=[16,32], n_estimators=[100,300] (FLOOR)
- BTC/15m: num_leaves=[64,128], n_estimators=[100,500] (FLOOR, iter 152 double-ceiling solution)
- BTC/1h: num_leaves=[48,96], n_estimators=[100,250] (FLOOR, iter 136 best at 350 but starvation-prone)
- ETH/5m: num_leaves=[16,32], n_estimators=[100,400]
- ETH/15m: num_leaves=[32,72], n_estimators=[100,400]
- ETH/1h: num_leaves=[16,32], n_estimators=[100,400]
- SOL/5m: num_leaves=[16,64], n_estimators=[100,400]
- SOL/15m: num_leaves=[32,72], n_estimators=[100,400]
- SOL/1h: num_leaves=[20,40], n_estimators=[100,400] (iter 169 confirmed optimal narrowed range)
- XRP/5m: num_leaves=[16,48], n_estimators=[100,400] (n_est=375 near ceiling, structural)
- XRP/15m: num_leaves=[32,80], n_estimators=[100,800] (n_est=777 near ceiling, structural starvation)
- XRP/1h: num_leaves=[16,64], n_estimators=[100,400]
