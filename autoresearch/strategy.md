# Strategy Directive
Updated: 2026-03-21T06:00:00Z
After iteration: 68

## Program Status: MULTI-TIMEFRAME EXPANSION — 1h BASELINES + 15m OPTIMIZATION

15m baselines complete for all 4 assets (iters 62-65). BTC 15m optimized with 2 knob iterations (iters 66-67).
BTC 1h baseline established (iter 68). The 15m timeframe is confirmed as BTC's sweet spot
(Brier 0.0940 vs 5m 0.1018 vs 1h 0.0985). The next phase is: complete 1h baselines for ETH/SOL/XRP,
then optimize the best 15m performers (ETH/SOL/XRP have untouched 15m baselines with potential lift
from train_bars/purge_period tuning).

---

## Priority Queue

The following experiments are ordered by expected value. The researcher should execute in order,
one per iteration.

1. **[1h-2] ETH 1h baseline — establish ETH 1h anchor.**

   Reset knobs to BTC 1h config (train_bars=10000, purge_period=24, n_splits=8,
   time_pcts=[0.30,0.50,0.80], 22 cached+regime features). Train ETH 1h.
   Expected: ETH 1h Brier in range 0.165-0.180. ETH was tick-dominant at both 5m and 15m.
   The 1h timeframe aggregates even more microstructure signal per bar. Compare vs
   ETH 15m best 0.17455 to measure the 15m->1h lift for tick-dominant assets.

   Rationale: Complete the 1h asset sweep before optimizing. BTC 1h baseline revealed
   diminishing returns (1h worse than 15m). ETH may show different dynamics since
   its feature profile is tick-dominant (vs BTC's regime-sensitive profile).

2. **[1h-3] SOL 1h baseline — continue 1h asset rotation.**

   Same knobs as ETH 1h. SOL showed smallest 5m->15m lift (1.1%). If SOL 1h Brier is worse
   than SOL 15m (0.1873), SOL follows the BTC diminishing-returns pattern and 15m is confirmed
   as the universal sweet spot. If SOL 1h improves, SOL has a different bar-duration optimum.

3. **[1h-4] XRP 1h baseline — complete 1h asset sweep.**

   Same knobs. XRP had the smallest 5m->15m lift (0.9%). Watch for reg_alpha behavior —
   XRP had extreme L1 (4.13) at 5m, near-zero at 15m. 1h may reveal whether XRP's
   regularization need is timeframe-dependent.

4. **[15m-opt-1] ETH 15m train_bars optimization — test 10000 vs 14000.**

   After 1h baselines complete, return to 15m optimization. ETH 15m baseline used
   train_bars=14000 (Brier 0.17455). BTC 15m improved with train_bars=10000 (iter 66, 0.95% lift).
   Test whether ETH 15m also improves at 10000. NOTE: ETH on 5m was OPPOSITE — train_bars
   14000 beat 10000 (iter 25 KEEP). The 15m landscape may differ. If KEEP: adopt 10000 for ETH 15m.
   If DISCARD: ETH 15m optimal remains 14000.

5. **[15m-opt-2] SOL 15m train_bars optimization — test 10000 vs 14000.**

   Same rationale as ETH. SOL 5m also preferred train_bars=14000. Test if 15m differs.
   SOL and ETH have nearly identical feature profiles (tick-dominant, no regime), so
   expect the same direction as ETH.

6. **[15m-opt-3] Best 15m performer: purge_period optimization.**

   After train_bars is settled for ETH/SOL 15m, test purge_period=12 vs 24 on the best
   15m performer (excluding BTC, which already tested this in iter 67 — DISCARD).
   ETH 5m preferred purge_period=12 (iter 29 KEEP). SOL 5m also preferred 12 (iter 39 KEEP).
   XRP 5m preferred 24 (iter 53 KEEP). Apply the 5m preference as the first hypothesis.

---

## Observations

**KEEP rates by category (iters 63-68, since last review):**
- 15m baselines: 3/3 (100%) — iters 63 (ETH), 64 (SOL), 65 (XRP)
- 1h baselines: 1/1 (100%) — iter 68 (BTC)
- train_bars tuning (15m): 1/1 (100%) — iter 66 (BTC 15m 14K->10K)
- purge_period tuning (15m): 0/1 (0%) — iter 67 (BTC 15m 24->12 DISCARD)

**KEEP rates overall (all 67 iterations):**
- Asset baselines (all timeframes): 9/9 (100%)
- train_bars extension/reduction: 6/8 (75%) — strongest non-baseline lever
- purge_period tuning: 4/9 (44%) — asset-specific, no universal direction
- KEEP-VERIFIED: 2/2 (100%)
- Regime+liquidation alpha: 2/2 (100%)
- Deployment engineering: 4/4 (100%)
- Validation/CPCV: 11/11 complete
- Funding features: 0/3 (0%) — permanent blacklist
- HPO range narrowing: 0/5 (0%) — permanent blacklist
- Interaction features: 0/1 (0%) — permanent blacklist
- n_splits changes: 0/4 (0%) — permanent blacklist
- embargo_period changes: 0/2 (0%) — permanent blacklist
- Sharpe-primary objective: 0/1 (0%) — permanent blacklist
- regime_params window changes: 0/3 (0%) — permanent blacklist
- Manual feature pruning: 0/2 (0%) — permanent blacklist
- drawdown_penalty_weight: 1/3 (33%) — near blacklist threshold

**15m vs 5m lift by asset (from baselines):**

| Asset | 5m Best | 15m Best | Lift | Class |
|-------|---------|----------|------|-------|
| BTC | 0.1018 | 0.0940 | 7.6% | BTC-class (regime) |
| ETH | 0.1778 | 0.1746 | 1.8% | ETH-class (tick) |
| SOL | 0.1894 | 0.1873 | 1.1% | ETH-class (tick) |
| XRP | 0.1953 | 0.1935 | 0.9% | ETH-class (tick at 15m, BTC-class at 5m) |

BTC benefits most from longer bars (regime features gain signal with more data per bar).
Tick-dominant assets (ETH/SOL/XRP) show smaller but consistent improvement at 15m.

**1h vs 15m (BTC only so far):**

| Asset | 15m Best | 1h Brier | Delta |
|-------|----------|----------|-------|
| BTC | 0.0940 | 0.0985 | -4.8% (WORSE) |

BTC 1h is worse than BTC 15m but better than BTC 5m. Diminishing returns confirmed at 1h.
The 1h timeframe produces 12x fewer trades (3,675 vs 43,721 at 5m) and 4x fewer than 15m.
However, 1h shows the BEST max_dd (4.34% vs 7.31% at 15m vs 13.61% at 5m) — excellent
risk profile despite lower Sharpe.

**Brier trajectory — current state (all timeframes):**
- BTC: 5m 0.1018 (frozen) | 15m **0.0940** (best overall) | 1h 0.0985
- ETH: 5m 0.1778 (frozen) | 15m 0.1746 (baseline only) | 1h pending
- SOL: 5m 0.1894 (frozen) | 15m 0.1873 (baseline only) | 1h pending
- XRP: 5m 0.1953 (frozen) | 15m 0.1935 (baseline only) | 1h pending

**Feature profile patterns at 15m:**
- All 4 assets show reg_alpha near 0 at 15m (vs BTC 2.854 and XRP 4.13 at 5m)
- Exception: XRP 15m retains reg_alpha=2.854 — UNIQUE across all assets and timeframes
- regime_vol_zscore present in BTC 15m SHAP (rank 6-8), absent from ETH/SOL/XRP 15m
- Tick features dominate at 15m same as 5m for ETH/SOL/XRP
- Key new 15m features: distance_from_open and vol_norm_distance elevated at 15m

**Researcher compliance:**
The researcher followed the previous strategy directive completely:
- [15m-2] ETH 15m baseline: DONE (iter 63)
- [15m-3] SOL 15m baseline: DONE (iter 64)
- [15m-4] XRP 15m baseline: DONE (iter 65)
- [15m-5] BTC 15m train_bars: DONE (iter 66, KEEP)
- [15m-6] BTC 15m purge_period: DONE (iter 67, DISCARD)
- [1h-1] BTC 1h baseline: DONE (iter 68, KEEP)

All 6 strategy priorities executed in exact order. Full compliance.

## Risk Profile

- Max drawdown trend: improving with longer timeframes — BTC 5m 13.61% -> BTC 15m 8.2% -> BTC 1h 4.34%
- Trade count range across KEEPs:
  - 5m: 43,000-45,000 (stable)
  - 15m: 14,200-14,800 (stable, ~3x fewer than 5m as expected)
  - 1h: 3,675 (12x fewer than 5m, first data point)
- Win rate across timeframes: BTC 5m 87.0% | BTC 15m 87.5% | BTC 1h 82.9% (slight 1h decline)
- HPO-OOS gap:
  - BTC 15m: 0.0907 (HPO) vs 0.0940 (OOS) = 0.0033 gap (3.6%, healthy)
  - BTC 1h: 0.0970 (HPO) vs 0.0985 (OOS) = 0.0015 gap (1.5%, excellent)
  - ETH 15m: 0.1685 (HPO) vs 0.1746 (OOS) = 0.0061 gap (3.5%, healthy)
  - SOL 15m: 0.1832 (HPO) vs 0.1873 (OOS) = 0.0041 gap (2.2%, healthy)
  - All HPO-OOS gaps are narrower at 15m/1h than at 5m — longer bars produce less overfit-prone models
- DD/PnL ratio: BTC 1h = 4.34/3.55 = 1.22 (elevated but acceptable for first 1h data point; fewer trades
  produce lower absolute PnL despite better per-trade quality)

## Timeframe Coverage

- 5m: 57 iterations, 20 KEEPs (35.1%), best Brier=0.101759 (BTC) — COMPLETE, all 4 assets at structural floor
- 15m: 6 iterations, 5 KEEPs (83.3%), best Brier=0.094003 (BTC) — baselines complete, optimization pending for ETH/SOL/XRP
- 1h: 1 iteration, 1 KEEP (100%), best Brier=0.098481 (BTC) — baselines pending for ETH/SOL/XRP
- Recommendation: **Complete 1h baselines (3 iters), then return to 15m optimization (3 iters)**. 15m is the strongest timeframe and has untapped optimization potential for 3 assets.

## Blacklist

All 5m blacklist items remain in force across all timeframes:

**Permanent blacklist (apply to all assets and timeframes):**
- Interaction features: 0/1 KEEP (iter 6, +41% Brier regression). Permanent.
- Funding features in cached_features: 0/3 KEEP (iters 2, 27, 43). Permanent.
- HPO range narrowing: 0/5 KEEP (iters 10, 13, 15, 19, 20). Permanent.
- n_splits != 8: 0/4 KEEP. Permanent.
- embargo_period != 6: 0/2 KEEP. Permanent.
- max_depth > 6: 0/1 KEEP (SOL iter 41). Permanent.
- Sharpe-primary objective: 0/1 KEEP (SOL iter 42). Permanent.
- regime_params window changes: 0/3 KEEP. Permanent.
- Manual feature pruning: 0/2 KEEP. Permanent.
- brier_threshold tightening: 0/2 KEEP (iters 35, 36). Permanent.
- min_target_corr changes: 0/1 KEEP (iter 34). Permanent.

**Near-blacklist (1 more DISCARD triggers blacklist):**
- drawdown_penalty_weight changes: 1/3 KEEP (iters 32 ETH marginal KEEP, 40 SOL DISCARD, 54 XRP DISCARD).
  The single KEEP was noise-level (0.000001 Brier improvement). Effectively non-binding for all assets.

**15m confirmed patterns:**
- BTC 15m purge_period=24->12: DISCARD (iter 67). BTC prefers purge_period=24 at both 5m and 15m.
- BTC 15m train_bars=14K->10K: KEEP (iter 66). BTC prefers shallower training at both 5m and 15m.

## HPO Range Recommendations

All ranges remain at current wide defaults. No narrowing recommended.

**15m/1h observations (do NOT act on these yet, just track):**
- reg_alpha converges to ~0 for BTC/ETH/SOL at 15m. XRP is the exception (2.854). Leave range wide.
- learning_rate at 15m: BTC 0.0148, ETH unknown, SOL unknown. May cluster differently than 5m.
- max_depth at 15m/1h: BTC 15m=4, BTC 1h=4 (same as 5m). SOL 15m=6 (same as 5m). Stable.
- num_leaves: variable across assets and timeframes (51-115). No convergence — keep range wide.

## Knobs State Advisory

Current knobs.json has train_bars=10000, purge_period=24 (BTC-optimal). For ETH/SOL/XRP 1h baselines,
the researcher should note:
- ETH/SOL/XRP optimal at 5m was train_bars=14000. The 1h baselines should use 10000 (consistent with
  BTC 1h baseline) to establish a common anchor, then test 14000 as an optimization step if warranted.
- Alternatively, the researcher may use train_bars=14000 for ETH/SOL/XRP 1h baselines (their 5m-optimal)
  and test 10000 later. Either approach is valid — just be explicit in the description.

## 1h Expansion Protocol

For each 1h baseline, the researcher should:
1. Set asset in training script to target asset
2. Set timeframe to 1h
3. Use current knobs.json (train_bars=10000, purge_period=24, n_splits=8)
4. Run standard HPO (40 trial target, 600s timeout)
5. Log to results.tsv with timeframe=1h
6. Compare Brier vs same-asset 15m best AND 5m best
7. Note SHAP feature profile — does 1h change feature importance vs 15m/5m?
8. Report max_dd and trade count — 1h will have ~4x fewer trades than 15m

After all 4 baselines complete, assess the BTC pattern: if 1h is consistently worse than 15m
across all assets, 1h optimization is low-priority and 15m optimization should be the focus.
If any asset shows 1h > 15m, that asset gets 1h optimization priority.

## Deployment Integration

The multi-timeframe deployment architecture remains:
- 5m model: fires at t=0.80 of each 5m bar (every 4 minutes)
- 15m model: fires at t=0.80 of each 15m bar (every 12 minutes)
- 1h model: fires at t=0.80 of each 1h bar (every 48 minutes)
- Signal combination: deferred until 15m/1h validation. Prioritize 15m as it has the best Brier.

Multi-timeframe CPCV validation is required before adding 15m/1h models to the deployment stack.
This validation should follow the same protocol as 5m (iters 47-57): CPCV first, then
regime-bucketed diagnostic for BTC-class assets.
