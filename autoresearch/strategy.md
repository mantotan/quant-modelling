# Strategy Directive
Updated: 2026-03-21T15:30:00Z
After iteration: 78

## Program Status: 15m CPCV VALIDATION PIPELINE — ETH 15m ESCALATED

15m optimization COMPLETE for all 4 assets. CPCV pipeline in progress:
- [15m-cpcv-1] BTC 15m: VALIDATION-PASS (iter 77, conditional — regime seesaw, composite gate PASS)
- [15m-cpcv-2] ETH 15m: VALIDATION-FAIL (iter 78, PBO=0.6429 FAIL, ESCALATED to auditor)
- [15m-cpcv-3] SOL 15m: PENDING
- [15m-cpcv-4] XRP 15m: PENDING

**ETH 15m ESCALATION:** PBO=0.6429 with near-zero IS-OOS correlation (0.0009) is a NEW failure mode.
Unlike BTC regime seesaw (IS-OOS corr=-0.90), ETH 15m shows RANDOM fold ranking.
Auditor Ruling 1 (PBO gate suspended if IS-OOS corr < -0.50) does NOT apply — corr is +0.0009.
However: 100% positive OOS paths, 2% IS-OOS gap, Deflated Sharpe=155.59, OOS Brier std=0.0039.
All 4 composite gate criteria PASS. Auditor must establish whether a new ruling covers near-zero IS-OOS correlation.

---

## Priority Queue

The following experiments are ordered by expected value. The researcher should execute in order,
one per iteration.

1. **[15m-cpcv-3] SOL 15m CPCV validation.**

   SOL 15m best: Brier 0.186836 (iter 75, train_bars=10000, purge_period=12).
   Use saved model.lgb params. C(8,2)=28 paths, n_groups=8, k_test=2.
   SOL 5m PBO=0.6429 CONDITIONAL-PASS. SOL may show similar borderline PBO at 15m.
   SOL is tick-dominant at 15m (regime_vol_zscore absent) — expect non-regime IS-OOS pattern.
   If IS-OOS corr is near zero (like ETH 15m iter 78), note this as a systematic tick-dominant pattern.

   Rationale: SOL 15m CPCV is independent of ETH 15m escalation. Proceeding builds data for auditor.

2. **[15m-cpcv-4] XRP 15m CPCV validation.**

   XRP 15m best: Brier 0.192624 (iter 74, train_bars=10000, purge_period=24).
   Use saved model.lgb params. C(8,2)=28 paths, n_groups=8, k_test=2.
   XRP 5m PBO=1.0000 CONDITIONAL-STRICT (BTC-class, regime seesaw IS-OOS corr=-0.90).
   At 15m, XRP is tick-dominant (regime_vol_zscore absent) — may shift from BTC-class to ETH-class behavior.
   If IS-OOS corr flips from negative (5m) to near-zero (15m), this confirms tick-dominance drives PBO failure mode.

   Rationale: XRP 15m CPCV completes the 15m validation pipeline and provides auditor with 4-asset comparative data.

3. **[HOLD] ETH 15m remediation — PENDING AUDITOR RULING.**

   Do NOT attempt ETH 15m remediation (e.g., re-training, knob changes) until auditor reviews.
   The auditor needs to establish whether near-zero IS-OOS correlation with 100% positive paths
   constitutes a new PASS condition (analogous to Ruling 1 for negative correlation).

   Possible auditor outcomes:
   - New Ruling 2: PBO gate suspended for near-zero IS-OOS corr (e.g., |corr| < 0.20) when composite gate PASSES
   - CONDITIONAL-PASS: Deploy ETH 15m at reduced Kelly sizing
   - REMEDIATION: Re-train ETH 15m with different walk-forward params
   - HALT: Investigate why ETH 15m PBO degraded from 5m (0.18 -> 0.64)

4. **[DEFERRED] 1h CPCV validation — after all 15m resolved.**

   1h models deprioritized per auditor (iter 71). Do not begin 1h CPCV until 15m pipeline complete.

---

## Observations

**KEEP rates by category (iters 74-78, since last review):**
- train_bars tuning (15m): 1/1 (100%) — iter 74 XRP KEEP at 10K
- purge_period tuning (15m): 1/1 (100%) — iter 75 SOL KEEP at 12; iter 76 XRP DISCARD at 12
- CPCV validation: 1 PASS / 1 FAIL of 2 attempted (iters 77-78)
- Total since last review: 2/3 non-validation iters KEEP (67%)

**KEEP rates overall (78 iterations):**
- Asset baselines (all timeframes): 12/12 (100%)
- train_bars tuning: 8/11 (73%) — consistently highest-value lever
- purge_period tuning: 5/12 (42%) — asset-specific
- KEEP-VERIFIED: 2/2 (100%)
- Regime+liquidation alpha: 2/2 (100%)
- Deployment engineering: 4/4 (100%)
- Validation/CPCV: 6 PASS / 3 FAIL / 4 CONDITIONAL of 13 total
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
- drawdown_penalty_weight: 1/4 (25%) — permanent blacklist

**15m optimization COMPLETE — final parameter matrix:**

| Asset | train_bars | purge_period | Best Brier | Source Iter |
|-------|-----------|-------------|------------|-------------|
| BTC   | 10000     | 24          | 0.094003   | iter 66     |
| ETH   | 14000     | 12          | 0.17455    | iter 63     |
| SOL   | 10000     | 12          | 0.186836   | iter 75     |
| XRP   | 10000     | 24          | 0.192624   | iter 74     |

**Pattern: purge_period splits by asset class:**
- purge_period=24: BTC, XRP (both show higher L1 regularization)
- purge_period=12: ETH, SOL (both tick-dominant with near-zero reg_alpha)

**15m CPCV results so far:**

| Asset | PBO(Sharpe) | IS-OOS Corr | IS-OOS Gap | 100% Positive | Composite | Verdict |
|-------|------------|------------|------------|---------------|-----------|---------|
| BTC   | 0.9643     | -0.6954    | 10.5%      | YES           | PASS      | PASS (Ruling 1) |
| ETH   | 0.6429     | +0.0009    | 2.0%       | YES           | PASS      | FAIL (no ruling) |
| SOL   | pending    | -          | -          | -             | -         | pending |
| XRP   | pending    | -          | -          | -             | -         | pending |

**NEW PATTERN — PBO failure modes by IS-OOS correlation:**
1. **Regime seesaw** (BTC 5m/15m, XRP 5m): IS-OOS corr strongly negative (-0.70 to -0.90). PBO fails mechanically because rank correlation inverts. Auditor Ruling 1 covers this.
2. **Random fold ranking** (ETH 15m): IS-OOS corr near zero (0.0009). PBO fails because rank correlation is flat — no consistent IS-to-OOS performance mapping. NO ruling covers this yet.
3. **Genuine signal** (ETH 5m): IS-OOS corr weakly negative (-0.33) but PBO=0.18 PASS. The sweet spot — mild IS-OOS decorrelation produces valid PBO.

Hypothesis: tick-dominant models (ETH/SOL/XRP at 15m) may systematically produce near-zero IS-OOS correlation because tick features have low fold-to-fold variance. If SOL/XRP 15m CPCV shows similar near-zero correlation, this confirms a systematic pattern requiring a new auditor ruling.

**Brier trajectory — current best (all timeframes):**
- BTC: 5m 0.1018 (frozen) | 15m **0.0940** (best overall) | 1h 0.0985
- ETH: 5m 0.1778 (frozen) | 15m **0.1746** (baseline, optimal) | 1h 0.1775
- SOL: 5m 0.1894 (frozen) | 15m **0.1869** (optimized) | 1h 0.1950
- XRP: 5m 0.1953 (frozen) | 15m **0.1926** (optimized) | 1h 0.1946

**Researcher compliance (iters 74-78):**
All 5 experiments followed previous strategy directive exactly:
- [15m-opt-3] XRP train_bars 14K->10K: DONE (iter 74 KEEP)
- [15m-opt-4] SOL purge_period 24->12: DONE (iter 75 KEEP)
- [15m-opt-5] XRP purge_period 24->12: DONE (iter 76 DISCARD, reverted)
- [15m-cpcv-1] BTC 15m CPCV: DONE (iter 77 VALIDATION-PASS)
- [15m-cpcv-2] ETH 15m CPCV: DONE (iter 78 VALIDATION-FAIL, ESCALATED)
Full compliance. All 5 priorities executed in exact order. Researcher correctly escalated ETH 15m failure.

## Risk Profile

- Max drawdown trend: STABLE across 15m (BTC 8.2%, ETH 1.5%, SOL 2.1%, XRP 1.5%)
- Trade count range across 15m KEEPs: 14,130-15,130 (stable, sufficient for statistical reliability)
- Win rate range across 15m KEEPs: BTC 87.2% (sniper), ETH 53.9%, SOL 58.5%, XRP 51.8%
- HPO-OOS gap at 15m: BTC 3.5%, ETH 3.4%, SOL 2.2%, XRP penalty-inflated (stable, no widening)
- CPCV risk: ETH 15m PBO=0.6429 is the only deployment blocker remaining

## Timeframe Coverage

- 5m: 57 iterations, 20 KEEPs (35.1%), best Brier=0.101759 (BTC) — COMPLETE, all assets at structural floor
- 15m: 12 iterations, 9 KEEPs (75.0%), best Brier=0.094003 (BTC) — optimization COMPLETE, CPCV in progress
- 1h: 4 iterations, 4 KEEPs (100%), best Brier=0.098481 (BTC) — baselines complete, DEPRIORITIZED
- DEPLOY: 4 iterations (iters 58-61) — infrastructure complete
- Recommendation: **Complete 15m CPCV pipeline (SOL + XRP), then await auditor ruling on ETH 15m**

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
- drawdown_penalty_weight changes: 1/4 KEEP (25%) — permanent blacklist (iter 32 ETH marginal noise)

**15m confirmed patterns:**
- BTC 15m: train_bars=10K KEEP (iter 66), purge_period=24 confirmed (iter 67 DISCARD at 12)
- ETH 15m: train_bars=14K confirmed (iter 72 DISCARD at 10K), purge_period=12 (baseline)
- SOL 15m: train_bars=10K KEEP (iter 73), purge_period=12 KEEP (iter 75)
- XRP 15m: train_bars=10K KEEP (iter 74), purge_period=24 confirmed (iter 76 DISCARD at 12)

## HPO Range Recommendations

All ranges remain at current wide defaults. No narrowing recommended (0/5 KEEP on narrowing attempts).

**15m parameter convergence (track only, do NOT narrow):**
- learning_rate: BTC 0.0053*, ETH 0.0120, SOL 0.017, XRP 0.039 — wider spread than 5m
- max_depth: BTC 6*, ETH 5, SOL 6, XRP 6 — converging to 5-6 (BTC model.lgb differs from iter 66)
- reg_alpha: BTC 0.015, ETH ~0, SOL ~0, XRP ~0 (collapsed from 2.854 after train_bars=10K)
- reg_lambda: BTC 3.67, ETH unknown, SOL 8.25, XRP ~0 — asset-specific L2

*Note: BTC 15m saved model.lgb params (lr=0.0053, depth=6) differ from iter 66 reported params (lr=0.0148, depth=4) — model was overwritten by subsequent training. CPCV used model.lgb params which are the true deployed params.
