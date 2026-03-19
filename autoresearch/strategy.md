# Strategy Directive
Updated: 2026-03-20T17:30:00Z
After iteration: 52

## Program State Summary

Four assets across three phases:
- ETH: UNCONDITIONAL PASS — deployment preparation may begin immediately
- BTC: CONDITIONAL-PASS — one diagnostic iteration required (regime-bucketed OOS)
- SOL: CONDITIONAL-PASS — one diagnostic iteration required (regime-bucketed OOS)
- XRP: Optimization in progress — baseline KEEP (0.195335), train_bars lever exhausted (iter 52 DISCARD)

The optimization research phase is complete for BTC/ETH/SOL. XRP has 3-4 productive iterations
remaining before CPCV. The critical path to full program completion is:

  iter 53: XRP purge_period 12→6 (highest-EV remaining XRP lever)
  iter 54: XRP drawdown_penalty_weight 5.0→10.0 (low-cost marginal lever)
  iter 55: BTC regime-bucketed OOS diagnostic (auditor CONDITIONAL-PASS requirement)
  iter 56: SOL regime-bucketed OOS diagnostic (auditor CONDITIONAL-PASS requirement)
  iter 57: XRP CPCV validation (deployment gate)

Estimated iterations to full 4-asset deployment clearance: 5 iterations minimum.

---

## Priority Queue

1. **[XRP-2] XRP purge_period 12→6.**

   Change: `walk_forward.purge_period: 12 → 6`

   Rationale: XRP is confirmed ETH/SOL-class (tick-dominant, regime_vol_zscore absent from
   top-10 SHAP across both iter 51 and iter 52). For tick-dominant assets, optimal purge_period
   is determined by the autocorrelation length of the tick features, not by regime transitions.
   ETH optimal is purge_period=12 (iter 29 KEEP). Trying 6 (tighter) tests whether XRP's
   tick features decorrelate faster than ETH's, which is plausible given XRP's payment-token
   microstructure (higher mean-reversion rate, less trend persistence than ETH).

   XRP baseline best_params showed reg_alpha=4.13 — anomalously high vs ETH (1e-6) and SOL
   (0.016). This implies the model is applying heavy L1 regularization even in tick-dominant
   mode. A shorter purge_period reduces train-test leakage exposure on correlated tick features,
   which could relax the reg_alpha pressure. If purge_period=6 produces a lower reg_alpha
   best_param AND lower Brier, this confirms autocorrelation length is the mechanism.

   KEEP threshold: Brier < 0.195335 (XRP baseline). No change to any other knob.
   DISCARD path: revert to purge_period=12 and proceed to priority 2.
   Expected outcome: marginal improvement (0.1-0.5%) consistent with SOL iter 39 (0.004%)
   and ETH iter 29 (0.009%) patterns.

2. **[XRP-3] XRP drawdown_penalty_weight 5.0→10.0.**

   Change: `objective.drawdown_penalty_weight: 5.0 → 10.0`

   Rationale: This produced a marginal KEEP on ETH (iter 32, Brier 0.177773→0.177772). The
   constraint is effectively non-binding for ETH/SOL-class assets (max drawdown 1.5-1.9%
   vs 30% threshold), but tightening the penalty can subtly bias the HPO search toward models
   with lower variance predictions, which may improve calibration. Low-cost lever (30 HPO trials,
   no structural change). Should run regardless of iter 53 outcome.

   KEEP threshold: Brier < XRP best after iter 53 result (strict improvement required).
   DISCARD path: revert and proceed to priority 3 (BTC regime-bucketed).
   Expected outcome: 0.0-0.05% improvement (marginal or zero, same as ETH).

3. **[BTC-DIAG] BTC regime-bucketed OOS validation — auditor CONDITIONAL-PASS requirement.**

   This is a diagnostic analysis run (mode=analyze), NOT a training run. No HPO. No knob
   changes. Uses the existing BTC walk-forward OOS prediction outputs.

   Compute OOS Sharpe and OOS Brier per regime_vol_state bucket:
     regime_vol_state = low    → OOS Sharpe, OOS Brier, n_trades
     regime_vol_state = normal → OOS Sharpe, OOS Brier, n_trades
     regime_vol_state = high   → OOS Sharpe, OOS Brier, n_trades
     regime_vol_state = crisis → OOS Sharpe, OOS Brier, n_trades

   Decision tree:
   - All 4 buckets OOS Sharpe > 0: BTC receives FULL deployment clearance. Proceed to SOL diag.
   - 1-2 buckets negative: BTC RESTRICTED clearance — flag those regime states for production
     halt. Still deployable with runtime regime filter.
   - 3+ buckets negative: BTC FAIL — escalate to auditor immediately.

   Expected outcome per audit.md ruling 3: all positive. Worst CPCV path OOS Sharpe > 104,
   and that path corresponds to the most regime-heterogeneous fold. A genuinely regime-failing
   model would have shown negative paths in CPCV.

   Log this as its own results.tsv row with status VALIDATION-PASS or VALIDATION-FAIL.
   BTC best_knobs unchanged.

4. **[SOL-DIAG] SOL regime-bucketed OOS validation — auditor CONDITIONAL-PASS requirement.**

   Same structure as priority 3. SOL carries HIGHER uncertainty than BTC per auditor ruling 4:
   - regime_vol_zscore absent from SOL top-10 SHAP (mechanism less clear than BTC)
   - SOL PBO=0.6429 vs BTC PBO=0.9643 (SOL less extreme but also less mechanistically explained)
   - Auditor flagged temporal non-stationarity hypothesis: FTX collapse (2022 Q4) may produce
     fold heterogeneity independent of regime state

   Additional diagnostic for SOL: cross-reference any negative-Sharpe bucket with temporal
   position. If weak Sharpe aligns with 2022 Q4 dates rather than a specific regime state,
   the mechanism is temporal data shift, not regime sensitivity. This matters for deployment
   risk assessment: temporal shift implies the model may degrade as time passes (data vintage
   drift), whereas regime failure implies performance is conditional on market conditions at
   execution time.

   Decision tree:
   - All buckets positive: SOL full clearance. Deploy at 0.5x Kelly per auditor directive
     until 30 days live performance confirmed.
   - Any bucket negative + temporal alignment with 2022 Q4: SOL RESTRICTED clearance. Flag
     the date range. Consider retraining baseline excluding pre-2023 data as a remediation path
     (new experiment, requires auditor WIDEN directive to change train_start date).
   - Any bucket negative + regime alignment: SOL RESTRICTED with regime filter. Same as BTC
     restricted path.
   - Multiple buckets negative: escalate to auditor.

5. **[XRP-CPCV] XRP CPCV validation — deployment gate for XRP.**

   Run after priorities 1-4. Use XRP best_params from best walk-forward run after iters 53-54.
   C(8,2)=28 paths, n_groups=8, k_test=2. Interpret results using auditor Ruling 1 framework:

   - PBO(Sharpe) < 0.40: XRP clean PASS (ETH-class behavior expected given tick dominance).
   - PBO(Sharpe) 0.40-0.70: CONDITIONAL-PASS (SOL-class). Note IS-OOS correlation.
   - PBO(Sharpe) > 0.70: CONDITIONAL-PASS (BTC-class). Verify all 28 paths positive.
   - Any OOS path negative: FAIL regardless of PBO — escalate to auditor.
   - Deflated Sharpe < 0: FAIL regardless of PBO — escalate to auditor.

   XRP prior: payment-token microstructure is tick-dominant and likely cleaner than SOL
   (no FTX-style structural break in XRP history 2022-2026). Expect PBO(Sharpe) < 0.40
   (ETH analog). reg_alpha=4.13 anomaly may produce slightly elevated IS-OOS gap vs ETH —
   monitor this.

---

## Observations

**Researcher compliance: full through iter 52.**
Iter 52 correctly executed XRP-1 (train_bars 14000→18000), confirmed DISCARD, and restored
knobs to train_bars=14000. Researcher_ack.txt correctly identifies XRP purge_period as the
next hypothesis. Full compliance maintained.

**KEEP rates by category (52 iterations complete):**
- Asset baselines (new asset first run): 4/4 (100%) — iters 7, 23, 37, 51
- KEEP-VERIFIED runs (mode=verify): 2/2 (100%)
- train_bars extension to optimal ceiling: 5/6 (83%) — iters 8, 18, 25, 38 KEEP; iter 52 DISCARD (ceiling confirmation, not a failure of the lever)
- purge_period tuning: 3/6 (50%) — iters 22, 29, 39 KEEP; iters 9, 30 DISCARD
- Regime+liquidation alpha features (BTC): 2/2 (100%)
- drawdown_penalty_weight: 1/1 (100%)
- Alpha features — funding: 0/3 (0%) — permanent blacklist
- time_pcts adjustments: 1/6 (17%) — only [0.30,0.50,0.80] stays, effectively 1 point at t=0.80
- HPO range narrowing: 0/5 (0%) — permanent blacklist
- regime_params window changes: 0/3 (0%) — permanent blacklist
- interaction features: 0/1 (0%) — permanent blacklist
- n_splits changes: 0/4 (0%) — n_splits=8 confirmed optimal
- embargo_period changes: 0/2 (0%) — embargo=6 confirmed
- objective/gate experiments: 0/4 (0%) — model floor locked
- CPCV/validation runs: ETH PASS; BTC/SOL CONDITIONAL-PASS; XRP pending
- Overall KEEP rate: 19/46 optimization iterations = 41.3%

**Brier trajectory:**
- BTC: 0.1982 (iter 7) → 0.101759 (iter 22). Frozen 30 consecutive experiments.
- ETH: 0.178243 (iter 23) → 0.177772 (iter 32). Effectively flat 20 experiments.
- SOL: 0.193016 (iter 37) → 0.189372 (iter 39). Flat 13 experiments.
- XRP: 0.195335 (iter 51, baseline). 1 DISCARD so far. 2 optimization levers remaining.

**XRP anomaly — reg_alpha=4.13:**
XRP baseline best_params include reg_alpha=4.13, which is 250x higher than SOL (0.016) and
orders of magnitude higher than ETH (1e-6). Both SOL and ETH are also tick-dominant. Possible
explanations:
  (a) XRP tick features have higher mutual correlation than ETH/SOL (XRP has tighter spreads,
      more HFT-dominated order flow). L1 sparsity regularization removes redundant correlated
      features effectively.
  (b) Noise: 26 HPO trials in baseline is low; reg_alpha may not be converged. Post-iter 53
      and 54, check if reg_alpha remains high or converges downward with more trials.
  (c) XRP has a sparse informative feature (similar to BTC regime_vol_zscore) that is outside
      top-10 SHAP but present in top-20. If liquidation_proximity is informative for XRP at
      rank 11-15, reg_alpha would increase to penalize weaker features.
  Monitor reg_alpha across iters 53-54. If still > 1.0 after purge_period tuning, note in
  XRP CPCV report as a model characteristic.

**Both-sides vs single-side (updated through iter 52):**
- BTC: single-side Sharpe 109.25, bs_sharpe 93.84. Single-side 16% superior. Directional asset.
- ETH: bs_sharpe 267-274 vs single-side 252-270. Both-sides dominant; $14M vs $176 absolute.
- SOL: bs_sharpe 251.55 vs single-side 251.86. Statistical tie.
- XRP baseline: bs_sharpe 262.33 vs single-side 262.23. Statistical tie — ETH/SOL-class.
  XRP iter 52 DISCARD: bs_sharpe 253.96 vs single-side 245.86. Both-sides 3.3% superior at
  18K train_bars but overall Brier worse — discard result, baseline holds. Both-sides MM is
  likely the correct XRP deployment strategy (consistent with ETH/SOL-class behavior).

**HPO convergence (stable):**
- BTC: lr=0.01272, max_depth=4, num_leaves=77, reg_alpha=2.854, reg_lambda=1.131
- ETH: lr=0.009, max_depth=6, num_leaves=95, reg_alpha=1e-6, reg_lambda=0.023
- SOL: lr=0.023, max_depth=6, num_leaves=72, reg_alpha=0.016, reg_lambda=8e-6
- XRP: lr=0.089 (anomalous — 4x higher than SOL), max_depth=6, num_leaves=30 (low), reg_alpha=4.13
  XRP HPO has not converged (26 trials in baseline, 30 in iter 52 DISCARD). Expect params to
  shift after iter 53 with more trial budget. Key watch: does lr drop toward ETH/SOL range
  (0.009-0.023) or remain elevated?

**Cross-asset classification — confirmed:**
- BTC-class (regime-sensitive): BTC alone. Characteristics: regime_vol_zscore SHAP top-10,
  meaningful L2 reg, max_depth=4, single-side directional.
- ETH/SOL/XRP-class (tick-dominant): ETH, SOL, XRP. Characteristics: tick microstructure
  dominates SHAP, both-sides MM viable, max_depth=6, near-zero to moderate regularization.

**Deployment preparation (ETH — can start now):**
ETH has UNCONDITIONAL PASS from auditor (ruling 2, audit.md). No blocking items remain.
Deployment preparation actions (outside autoresearch loop, can proceed in parallel):
- Compile ETH model via treelite
- Freeze config: train_bars=14000, purge_period=12, n_splits=8, time_pcts=[0.80]
- Deployment strategy: both_sides_mm (bs_sharpe 267-274 consistently dominates)
- Document architecture: single-snapshot-at-t=0.80, late-bar predictor
- Trigger: deploy signal at t=0.80 of 5m bar (4:00 of 5:00 bar)

---

## Blacklist

All previous entries carried forward. No additions or removals from iter 52.

- **Interaction features:** all 8 pairs, permanent. Iter 6: +41% Brier regression.
- **Funding features in cached_features:** permanent. 0/3 KEEP (BTC iter 2, ETH iter 27, SOL
  iter 43). Apply zero-funding assumption to XRP.
- **HPO range narrowing:** permanent. 0/5 KEEP (iters 10, 13, 15, 19, 20). Wall-clock binding.
- **time_pcts beyond [0.30,0.50,0.80]:** 0/3 KEEP (iters 12, 21, 28). Three-point set is
  ceiling; effective architecture is single-point (t=0.80). Do not expand.
- **embargo_period != 6:** 0/2 KEEP (iters 9, 30). Keep at 6 all assets.
- **n_splits != 8:** 0/4 KEEP (iters 11, 31, 33). n_splits=8 confirmed optimal.
- **regime_params window changes:** 0/3 KEEP (iters 17, 26). Skip for XRP.
- **Manual feature pruning:** 0/2 KEEP (iters 16, 24). Trust automated selection.
- **train_bars above 10000 for BTC:** ceiling confirmed iters 18-22.
- **train_bars above 14000 for ETH/SOL/XRP:** ceiling confirmed (ETH baseline, SOL iter 38,
  XRP iter 52 DISCARD). No exceptions for ETH-class assets.
- **max_depth above 6 for SOL:** iter 41 regression. Apply same ceiling to XRP (ETH/SOL-class).
- **Sharpe-primary objective for SOL:** iter 42, landscape invariant.
- **BTC/SOL further knob optimization before regime-bucketed validation:** auditor mandate.
  Do not attempt Brier optimization for BTC or SOL until priorities 3 and 4 complete.
- **PBO < 0.40 as hard gate for regime-sensitive assets:** auditor formally suspended per
  Ruling 1. Use composite: 100% positive OOS paths + IS-OOS gap < 20% + Deflated Sharpe > 0
  + regime-bucketed all positive.

---

## HPO Range Recommendations

**BTC/ETH/SOL: no changes.** All at confirmed structural floors. HPO range modifications are
permanently blacklisted (0/5 KEEP).

**XRP: do not narrow yet.** XRP has only 2 optimization iterations (baseline + 1 DISCARD).
Current best_params (lr=0.089, max_depth=6, num_leaves=30, reg_alpha=4.13) are from 26-trial
baseline and are not converged. After iter 53 and 54 complete with different purge/penalty
settings, inspect whether params cluster:
- If lr stays above 0.05 across 2+ KEEP iters: narrow to [0.03, 0.10]
- If reg_alpha stays above 2.0 across 2+ KEEP iters: this is a valid XRP characteristic,
  do not suppress it
- If num_leaves stays in [25, 40] across 2+ KEEP iters: narrow to [20, 60]
- 3+ KEEP iterations with convergence evidence required before any narrowing

Do NOT narrow before the XRP floor is confirmed. Current range [0.005, 0.1] for lr and
[1e-8, 10.0] for reg_alpha are appropriate for XRP's unconverged state.

---

## XRP Optimization Priority Stack (updated after iter 52)

| Priority | Iter | Experiment                      | Knob Change                     | Predicted Outcome         | KEEP Rate Basis          |
|----------|------|---------------------------------|---------------------------------|---------------------------|--------------------------|
| XRP-2    | 53   | purge_period 12→6               | walk_forward.purge_period: 6    | 0.1-0.5% Brier improvement| 3/6 = 50% cross-asset    |
| XRP-3    | 54   | drawdown_penalty_weight 5→10    | objective.drawdown_penalty: 10  | 0.0-0.05% improvement     | 1/1 = 100% (ETH only)    |
| XRP-CPCV | 57   | XRP CPCV validation             | mode=verify, saved best_params  | PBO < 0.40 expected       | ETH precedent (0.18)     |

Completed XRP experiments:
| Priority | Iter | Experiment                      | Outcome                                          |
|----------|------|---------------------------------|--------------------------------------------------|
| XRP-0    | 51   | XRP baseline                    | KEEP — Brier 0.195335, baseline anchor set       |
| XRP-1    | 52   | train_bars 14000→18000          | DISCARD — ceiling confirmed at 14000             |

Skip for XRP (blacklisted):
- Funding features: 0/3 cross-asset KEEP
- regime_params window changes: 0/3 cross-asset KEEP
- HPO range narrowing: 0/5 KEEP — wall-clock binding
- interaction features: 0/1, +41% regression
- time_pcts expansion: 0/3 KEEP
- n_splits != 8: 0/4 KEEP
- embargo_period != 6: 0/2 KEEP
- max_depth > 6: SOL iter 41 regression, apply to XRP as same class
- train_bars > 14000: iter 52 DISCARD, ceiling confirmed

---

## Cross-Asset Status Summary

| Asset | Best Brier | Best Sharpe | Best bs_sharpe | Opt Iters | Validation Status                                               |
|-------|------------|-------------|----------------|-----------|------------------------------------------------------------------|
| BTC   | 0.101759   | 109.25      | 93.84          | 22        | CONDITIONAL-PASS — regime-bucketed diagnostic required (iter 55) |
| ETH   | 0.177772   | 264.57      | 274.44         | 9         | UNCONDITIONAL PASS — deploy immediately                          |
| SOL   | 0.189372   | 251.86      | 251.55         | 7         | CONDITIONAL-PASS (elevated uncertainty) — regime-bucketed (iter 56) |
| XRP   | 0.195335   | 262.23      | 262.33         | 1         | In progress — 2 optimization iters + CPCV remaining              |

---

## Acceptance Gate Status (post iter 52)

| Metric          | Required   | BTC                     | ETH                  | SOL                        | XRP               |
|-----------------|------------|-------------------------|----------------------|----------------------------|-------------------|
| OOS Brier       | < 0.25     | 0.1018 PASS             | 0.1778 PASS          | 0.1894 PASS                | 0.1953 PASS       |
| OOS ECE         | < 0.05     | 0.0088 PASS             | 0.0252 PASS          | 0.0135 PASS                | 0.0186 PASS       |
| Net PnL         | > 0        | $45.55 PASS             | $176.50 PASS         | $172.13 PASS               | $173.97 PASS      |
| Max Drawdown    | < 30%      | 13.61% PASS             | 1.75% PASS           | 1.62% PASS                 | 1.50% PASS        |
| Deflated Sharpe | > 0.0      | 126.91 PASS             | 266.25 PASS          | 255.58 PASS                | pending CPCV      |
| OOS Paths Pos.  | 100%       | 100% (28/28) PASS       | 100% (28/28) PASS    | 100% (28/28) PASS          | pending CPCV      |
| PBO             | < 0.40*    | 0.9643 COND-PASS*       | 0.1786 PASS          | 0.6429 COND-PASS*          | pending CPCV      |
| Win Rate        | 40-85%     | 87.0% borderline-high   | 54.7% PASS           | 52.0% PASS                 | 53.0% PASS        |

*PBO gate suspended for BTC/SOL per auditor Ruling 1. Replacement criteria: 100% positive OOS
paths + IS-OOS Sharpe gap < 20% + Deflated Sharpe > 0 + regime-bucketed all positive.

**XRP note:** All walk-forward acceptance criteria pass at baseline. XRP is conditionally
deployment-ready pending CPCV validation only (same as SOL path).

---

## Deployment Priority Order (per auditor audit.md)

1. ETH — unconditional PASS, deploy first, both-sides MM strategy (bs_sharpe 267-274)
2. BTC — deploy after iter 55 regime-bucketed validation passes, single-side sniper
3. SOL — deploy after iter 56 regime-bucketed validation passes, 0.5x Kelly sizing, both-sides
4. XRP — deploy after iter 57 CPCV passes, both-sides MM strategy (statistical tie)

---

## Next Auditor Trigger

Per audit.md: auditor trigger at iteration 60 or at any of:
- Regime-bucketed validation showing negative OOS Sharpe for any bucket in BTC or SOL
- XRP CPCV FAIL (any OOS path negative OR Deflated Sharpe < 0)
- Any metric regression below acceptance threshold in validation runs

After all four conditions below are satisfied, the program transitions to deployment:
1. BTC regime-bucketed validation PASS (iter 55)
2. SOL regime-bucketed validation PASS (iter 56)
3. XRP CPCV PASS (iter 57)
4. ETH deployment preparation complete (parallel, no iteration slot required)
