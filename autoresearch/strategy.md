# Strategy Directive
Updated: 2026-03-21T10:30:00Z
After iteration: 73

## Program Status: 15m OPTIMIZATION + CPCV VALIDATION PIPELINE

All 12 baselines complete (4 assets x 3 timeframes). 15m confirmed as universally optimal timeframe.
1h baselines complete (iters 69-71): all 4 assets confirm 1h worse than 15m — 1h deprioritized.
15m train_bars optimization: BTC 10K (iter 66 KEEP), ETH 14K (iter 72 DISCARD at 10K), SOL 10K (iter 73 KEEP).
XRP 15m train_bars untested. Purge_period optimization pending for SOL/XRP 15m.

**Critical gap (auditor iter 71):** No 15m CPCV validation exists. All CPCV (iters 47-50, 57) was 5m only.
15m CPCV must be completed before multi-timeframe deployment.

---

## Priority Queue

The following experiments are ordered by expected value. The researcher should execute in order,
one per iteration.

1. **[15m-opt-3] XRP 15m train_bars optimization — test 14000 vs 10000.**

   Current XRP 15m baseline used train_bars=14000 (Brier 0.193523, iter 65).
   BTC 15m KEEP at 10K (iter 66), SOL 15m KEEP at 10K (iter 73), ETH 15m DISCARD at 10K (iter 72).
   XRP is ETH/SOL-class at 15m (tick-dominant, no regime in SHAP) but BTC-class at 5m (reg_alpha=4.13).
   At 15m, XRP retains reg_alpha=2.854 (unique). Test train_bars=10000 to determine XRP's preference.
   Set knobs: train_bars=10000, purge_period=24, asset=XRP, timeframe=15m.

   Rationale: Complete train_bars sweep for all 4 assets at 15m. 2/3 assets tested prefer 10K.

2. **[15m-opt-4] SOL 15m purge_period optimization — test 24 vs 12.**

   SOL 15m current best: Brier 0.186851 (iter 73, train_bars=10000, purge_period=24).
   SOL 5m preferred purge_period=12 (iter 39 KEEP). BTC 15m preferred 24 (iter 67 DISCARD at 12).
   SOL is tick-dominant — may behave differently from BTC at 15m.
   Set knobs: train_bars=10000, purge_period=12, asset=SOL, timeframe=15m.

   Rationale: purge_period is the second-highest-value walk-forward lever (4/9 KEEP overall, asset-specific).

3. **[15m-opt-5] XRP 15m purge_period optimization — test alternate direction.**

   After XRP train_bars is settled (priority 1), test purge_period opposite to XRP 5m preference.
   XRP 5m preferred purge_period=24 (iter 53 KEEP). If XRP 15m train_bars=10K is adopted,
   test purge_period=12. If XRP 15m stays at 14K, test purge_period=12 (same).
   XRP has unique regularization (reg_alpha=2.854 at 15m) — purge_period may interact.

   Rationale: Complete the walk-forward sweep for XRP 15m.

4. **[15m-cpcv-1] BTC 15m CPCV validation — first 15m CPCV.**

   After optimization completes for all 4 assets at 15m, begin CPCV validation.
   BTC 15m best: Brier 0.094003 (iter 66, train_bars=10000, purge_period=24).
   Use saved model.lgb params (NOT HPO midpoints — learned from iter 47 vs 50 that midpoints corrupt PBO).
   C(8,2)=28 paths, n_groups=8, k_test=2.
   BTC is regime-sensitive — expect PBO > 0.40 with negative IS-OOS correlation (same as 5m).
   Apply auditor Ruling 1: if IS-OOS corr < -0.50, PBO gate suspended; use composite gate
   (100% positive paths + IS-OOS gap < 20% + Deflated Sharpe > 0 + OOS Brier std < 0.01).

   Rationale: Auditor flagged 15m CPCV as critical gap. BTC first because BTC-class requires special handling.

5. **[15m-cpcv-2] ETH 15m CPCV validation.**

   ETH 15m best: Brier 0.17455 (iter 63, train_bars=14000, purge_period=12).
   ETH 5m PBO=0.1786 (PASS EXCELLENT). Expect ETH 15m PBO to also pass cleanly.
   Use saved model.lgb params.

   Rationale: ETH is the cleanest validation candidate (5m PBO was 0.18).

6. **[15m-cpcv-3] SOL 15m CPCV validation.**

   SOL 15m best: Brier 0.186851 (iter 73, train_bars=10000, purge_period=24).
   SOL 5m PBO=0.6429 CONDITIONAL-PASS. SOL may be borderline at 15m.

7. **[15m-cpcv-4] XRP 15m CPCV validation.**

   XRP 15m best from optimization. XRP 5m PBO=1.0000 CONDITIONAL-STRICT.
   XRP is BTC-class at 5m — may show same regime IS-OOS seesaw at 15m.

---

## Observations

**KEEP rates by category (iters 69-73, since last review):**
- 1h baselines: 3/3 (100%) — iters 69 (ETH), 70 (SOL), 71 (XRP)
- train_bars tuning (15m): 1/2 (50%) — iter 72 (ETH DISCARD), 73 (SOL KEEP)
- Total since last review: 4/5 (80%)

**KEEP rates overall (73 iterations):**
- Asset baselines (all timeframes): 12/12 (100%) — strongest category
- train_bars tuning: 7/10 (70%) — consistently high-value lever
- purge_period tuning: 4/10 (40%) — asset-specific, no universal direction
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
- brier_threshold tightening: 0/2 (0%) — permanent blacklist
- min_target_corr changes: 0/1 (0%) — permanent blacklist
- drawdown_penalty_weight: 1/4 (25%) — now below 33% threshold, BLACKLISTED

**train_bars split by asset class at 15m:**

| Asset | 15m Baseline (14K) | 15m at 10K | Preferred | Class |
|-------|-------------------|------------|-----------|-------|
| BTC   | 0.094907 (iter 62) | **0.094003** (iter 66 KEEP) | 10K | BTC-class |
| ETH   | **0.17455** (iter 63) | 0.174799 (iter 72 DISCARD) | 14K | ETH-class |
| SOL   | 0.187327 (iter 64) | **0.186851** (iter 73 KEEP) | 10K | SOL-class* |
| XRP   | 0.193523 (iter 65) | untested | ? | ? |

*SOL train_bars preference differs from ETH despite identical feature profiles (both tick-dominant).
This is the first divergence between SOL and ETH behavior. SOL may be closer to BTC-class for
walk-forward parameters despite having tick-dominant features.

**Brier trajectory — current best (all timeframes):**
- BTC: 5m 0.1018 (frozen) | 15m **0.0940** (best overall) | 1h 0.0985
- ETH: 5m 0.1778 (frozen) | 15m **0.1746** (baseline, optimal) | 1h 0.1775
- SOL: 5m 0.1894 (frozen) | 15m **0.1869** (optimized) | 1h 0.1950
- XRP: 5m 0.1953 (frozen) | 15m **0.1935** (baseline only) | 1h 0.1946

**1h vs 15m gap (all 4 assets now confirmed):**

| Asset | 15m Best | 1h Brier | Delta | 1h Verdict |
|-------|----------|----------|-------|------------|
| BTC   | 0.0940   | 0.0985   | -4.8% | WORSE |
| ETH   | 0.1746   | 0.1775   | -1.7% | WORSE |
| SOL   | 0.1869   | 0.1950   | -4.3% | WORSE |
| XRP   | 0.1935   | 0.1946   | -0.6% | WORSE |

**Conclusion:** 1h is universally worse than 15m. Deprioritize 1h optimization entirely.
1h models may still be useful for deployment as confirmation signals at reduced Kelly sizing
but do not warrant independent optimization iterations.

**Researcher compliance (iters 69-73):**
All 5 experiments followed previous strategy directive exactly:
- [1h-2] ETH 1h baseline: DONE (iter 69 KEEP)
- [1h-3] SOL 1h baseline: DONE (iter 70 KEEP)
- [1h-4] XRP 1h baseline: DONE (iter 71 KEEP)
- [15m-opt-1] ETH 15m train_bars: DONE (iter 72 DISCARD)
- [15m-opt-2] SOL 15m train_bars: DONE (iter 73 KEEP)
Full compliance. All 5 priorities executed in exact order.

## Risk Profile

- Max drawdown trend: stable across 15m (BTC 8.2%, ETH 1.5%, SOL 2.1%, XRP 1.5%), improving at 1h (BTC 4.3%, ETH 1.5%, SOL 1.8%, XRP 1.3%)
- Trade count range across 15m KEEPs: 14,234-14,849 (stable, sufficient for statistical reliability)
- Trade count at 1h: 3,675-3,870 (thin but adequate; 4x fewer than 15m as expected)
- Win rate range: BTC 82.9-87.5% (sniper), ETH/SOL/XRP 49.1-59.4% (calibrated probability models)
- HPO-OOS gap at 15m:
  - BTC: 3.5% (healthy)
  - ETH: 3.4% (healthy)
  - SOL: 2.2% (healthy)
  - XRP: penalty-inflated (0.2897 hpo_objective vs 0.1935 oos_brier — trade penalty component)
- HPO-OOS gap at 1h:
  - BTC: 1.5% (excellent)
  - ETH: 6.1% (higher than 15m, monitor)
  - SOL: 2.4% (healthy)
  - XRP: penalty-inflated (same pattern as XRP 5m/15m)

## Timeframe Coverage

- 5m: 57 iterations, 20 KEEPs (35.1%), best Brier=0.101759 (BTC) — COMPLETE, all assets at structural floor
- 15m: 8 iterations, 7 KEEPs (87.5%), best Brier=0.094003 (BTC) — optimization in progress (XRP train_bars + purge_period pending)
- 1h: 4 iterations, 4 KEEPs (100%), best Brier=0.098481 (BTC) — baselines complete, DEPRIORITIZED
- DEPLOY: 4 iterations (iters 58-61) — infrastructure complete
- Recommendation: **Focus on 15m optimization (2-3 iters) then 15m CPCV validation (4 iters)**

## Blacklist

**Permanent blacklist (apply to all assets and timeframes):**
- Interaction features: 0/1 KEEP (iter 6). Permanent.
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
- **drawdown_penalty_weight changes: 1/4 KEEP (25%) — NOW BLACKLISTED** (iter 32 ETH marginal, iters 40 SOL, 54 XRP, and 1h baselines confirm non-binding for all assets)

**15m confirmed patterns:**
- BTC 15m train_bars=10K: KEEP (iter 66)
- BTC 15m purge_period=24: confirmed (iter 67 DISCARD at 12)
- ETH 15m train_bars=14K: confirmed (iter 72 DISCARD at 10K)
- SOL 15m train_bars=10K: KEEP (iter 73)

## HPO Range Recommendations

All ranges remain at current wide defaults. No narrowing recommended (0/5 KEEP on narrowing attempts).

**15m parameter convergence (track only, do NOT narrow):**
- learning_rate: BTC 0.0148, ETH unknown, SOL 0.017, XRP 0.0127 — clustering in [0.01, 0.02]
- max_depth: BTC 4, ETH unknown, SOL 6, XRP 4 — BTC/XRP shallower
- reg_alpha: BTC ~0, ETH ~0, SOL ~0, XRP 2.854 — XRP unique
- reg_lambda: BTC 3.67, ETH unknown, SOL 8.25, XRP ~0 — asset-specific L2
