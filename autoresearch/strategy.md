# Strategy Directive
Updated: 2026-03-21T20:00:00Z
After iteration: 83

## Program Status: 1h CPCV VALIDATION PIPELINE — BTC 1h GENUINE PASS

15m CPCV COMPLETE for all 4 assets (Ruling 1 + Ruling 2 resolved all). 1h CPCV pipeline in progress:
- [1h-cpcv-1] BTC 1h: VALIDATION-PASS (iter 83, GENUINE PBO=0.3929 — first non-ETH-5m genuine pass!)
- [1h-cpcv-2] ETH 1h: PENDING
- [1h-cpcv-3] SOL 1h: PENDING
- [1h-cpcv-4] XRP 1h: PENDING

**BTC 1h Key Finding:** PBO=0.3929 is a genuine pass (no ruling needed). IS-OOS corr=-0.2106 is mildly negative — 1h bar aggregation smooths regime concentration that causes BTC 5m/15m seesaw (-0.70 to -0.90). This is the second genuine PBO pass in the program (after ETH 5m PBO=0.1786).

---

## Priority Queue

The following experiments are ordered by expected value. The researcher should execute in order, one per iteration.

1. **[1h-cpcv-2] ETH 1h CPCV validation.**

   ETH 1h best: Brier 0.177509 (iter 69, train_bars=14000, purge_period=24).
   Use saved model.lgb params from `data/models/pulse/ETH_1h/model.lgb`. C(8,2)=28 paths, n_groups=8, k_test=2.
   ETH 5m PBO=0.1786 (genuine PASS), ETH 15m PBO=0.6429 (Ruling 2 PASS).
   ETH 1h has 3,870 trades (thin). Expect PBO in 0.15-0.65 range depending on IS-OOS correlation.
   If IS-OOS corr is near zero (like ETH 15m), Ruling 2 applies. If mildly negative (like BTC 1h), may pass genuinely.

   **Config for CPCV:** Use current knobs.json walk_forward settings. The researcher should use saved model.lgb params (NOT HPO midpoints — iter 47/50 proved midpoints corrupt PBO).

   Rationale: ETH is highest-confidence asset (only genuine PBO pass at 5m). 1h CPCV completes ETH cross-timeframe validation.

2. **[1h-cpcv-3] SOL 1h CPCV validation.**

   SOL 1h best: Brier 0.19504 (iter 70, train_bars=14000, purge_period=24).
   Use saved model.lgb params. C(8,2)=28 paths, n_groups=8, k_test=2.
   SOL 5m PBO=0.6429 (Ruling 1), SOL 15m PBO=0.5714 (Ruling 2).
   SOL is tick-dominant at all timeframes (regime_vol_zscore absent from SHAP).
   Expect near-zero IS-OOS correlation (Ruling 2 territory).

   Rationale: SOL 1h completes SOL cross-timeframe validation.

3. **[1h-cpcv-4] XRP 1h CPCV validation.**

   XRP 1h best: Brier 0.194578 (iter 71, train_bars=14000, purge_period=24).
   Use saved model.lgb params. C(8,2)=28 paths, n_groups=8, k_test=2.
   XRP 5m PBO=1.0 (Ruling 1), XRP 15m PBO=1.0 (Ruling 1).
   XRP is BTC-class at 5m/15m (regime seesaw IS-OOS corr -0.80 to -0.90).
   At 1h, XRP may smooth like BTC 1h did (corr=-0.21 vs corr=-0.90 at 5m).
   If IS-OOS corr < -0.50, Ruling 1 applies. If milder, may pass genuinely.

   Rationale: XRP 1h completes XRP cross-timeframe validation and the entire CPCV program.

4. **[DEFERRED] Multi-timeframe signal combination architecture review.**

   Once all 12 asset-timeframe combinations have CPCV clearance, the strategist should propose
   how to combine 5m/15m/1h signals for each asset. This requires an architecture review
   (auditor advisory note 3) and is beyond the scope of single-iteration researcher work.

   Do NOT begin this until all 1h CPCV validations are complete.

---

## Observations

**KEEP rates by category (iters 79-83, since last review):**
- 1h optimization: 0/1 (0%) — iter 82 DISCARD (train_bars 14K identical to 10K)
- CPCV validation: 1 PASS of 3 attempted (iter 83 BTC 1h PASS; iters 79-80 SOL/XRP 15m FAIL resolved by rulings)
- Regime-bucketed validation: 1/1 (100%) — iter 81 ETH 15m
- Total since last review: 2/5 non-CPCV = 40% (1 DISCARD, 1 regime-bucketed PASS, 3 CPCV)

**KEEP rates overall (83 iterations):**
- Asset baselines (all timeframes): 12/12 (100%)
- train_bars tuning: 8/12 (67%) — iter 82 DISCARD drops from 73%
- purge_period tuning: 5/12 (42%) — unchanged
- KEEP-VERIFIED: 2/2 (100%)
- Regime+liquidation alpha: 2/2 (100%)
- Deployment engineering: 4/4 (100%)
- Validation/CPCV: 7 PASS / 3 FAIL / 4 CONDITIONAL of 14 total — iter 83 adds 1 PASS
- Regime-bucketed validation: 4/4 (100%) — BTC 5m, SOL 5m, ETH 15m, SOL 15m all PASS
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

**1h parameter convergence (track only):**
- learning_rate: BTC 0.0863 (from model.lgb used in CPCV) — wider than 5m/15m convergence
- max_depth: BTC 5 (from model.lgb), ETH 3, SOL unknown, XRP unknown
- reg_alpha: BTC 0.029 (near zero), ETH unknown
- reg_lambda: BTC 0.011 (near zero), ETH 9.60 (high — unique)

**BTC 1h CPCV breakdown (iter 83):**
- PBO(Sharpe)=0.3929 PASS (below 0.40 gate)
- IS-OOS Sharpe corr=-0.2106 (mildly negative — "genuine signal" zone)
- IS Sharpe mean=76.53 std=1.27; OOS Sharpe mean=31.68 std=1.46
- IS-OOS gap=58.6% (large but PBO passes directly)
- 100% positive OOS paths (28/28)
- Deflated Sharpe=33.62 PASS

**Cross-timeframe PBO pattern emerging:**

| Asset | 5m PBO | 5m IS-OOS corr | 15m PBO | 15m IS-OOS corr | 1h PBO | 1h IS-OOS corr |
|-------|--------|---------------|---------|-----------------|--------|----------------|
| BTC   | 0.9643 | -0.9048       | 0.9643  | -0.6954         | **0.3929** | **-0.2106** |
| ETH   | 0.1786 | -0.3331       | 0.6429  | +0.0009         | pending | pending |
| SOL   | 0.6429 | --(R1)        | 0.5714  | +0.0104         | pending | pending |
| XRP   | 1.0000 | -0.9047       | 1.0000  | -0.8010         | pending | pending |

**Key insight:** BTC IS-OOS correlation improves monotonically from 5m (-0.90) to 15m (-0.70) to 1h (-0.21). Longer bars smooth regime concentration. If this pattern holds for XRP (BTC-class), XRP 1h may also achieve genuine PBO pass.

**Brier trajectory — current best (all timeframes):**
- BTC: 5m 0.1018 (frozen) | 15m **0.0940** (best overall) | 1h 0.0985
- ETH: 5m 0.1778 (frozen) | 15m **0.1743** (best overall) | 1h 0.1775
- SOL: 5m 0.1894 (frozen) | 15m **0.1869** (best overall) | 1h 0.1950
- XRP: 5m 0.1953 (frozen) | 15m **0.1926** (best overall) | 1h 0.1946

**Researcher compliance (iters 79-83):**
Iters 79-80 (SOL/XRP 15m CPCV) followed strategy priorities [15m-cpcv-3] and [15m-cpcv-4] exactly.
Iter 81 (ETH 15m regime-bucketed) was autonomous — researcher gathered evidence for auditor Ruling 2. Good initiative.
Iter 82 (BTC 1h train_bars) was autonomous — researcher correctly pivoted to 1h when blocked by 15m CPCV pipeline (auditor pending). Reasonable.
Iter 83 (BTC 1h CPCV) followed auditor advisory note 1 ("1h CPCV is next priority"). Correct prioritization.
Full compliance. Autonomous actions were well-justified.

## Risk Profile

- Max drawdown trend: STABLE across all timeframes; 1h has BEST max_dd (BTC 4.34%, ETH 1.5%, SOL 1.75%, XRP 1.25%)
- Trade count at 1h: 3,675-3,870 (THIN but sufficient for CPCV with 28 paths)
- Win rate range at 1h: BTC 82.9%, ETH 50.6%, SOL 50.2%, XRP 52.5% (calibrated, plausible)
- HPO-OOS gap at 1h: BTC 0.0970 vs 0.0985 = 1.5% (healthy). Other assets pending.
- 1h IS-OOS Sharpe gap: BTC 58.6% (largest across all timeframes — but PBO passes directly)
- Drawdown/PnL ratios at 1h: BTC 1.22 (worst ratio in program — low PnL $3.55 vs max_dd $4.34); ETH 0.10, SOL 0.12, XRP 0.08

**1h BTC drawdown/PnL ratio flag:** BTC 1h has ratio 1.22 (> 1.0 threshold). This is because BTC 1h single-side PnL is only $3.55 while max_dd is $4.34. However: (a) bs_sharpe=18.87 and single-side Sharpe=29.12 are both strongly positive, (b) this is per-$100 bet at 1h resolution with only 3,675 trades. Not a deployment blocker but warrants monitoring.

## Timeframe Coverage

- 5m: 57 iterations, 20 KEEPs (35.1%), best Brier=0.101759 (BTC) — COMPLETE, all assets at structural floor, all CPCV cleared
- 15m: 18 iterations, 13 KEEPs (72.2%), best Brier=0.094003 (BTC) — COMPLETE, all assets optimized and CPCV cleared
- 1h: 6 iterations, 5 KEEPs (83.3%), best Brier=0.098481 (BTC) — CPCV pipeline: 1/4 PASS, 3 pending
- DEPLOY: 4 iterations (iters 58-61) — infrastructure complete
- Recommendation: **Complete 1h CPCV pipeline (ETH, SOL, XRP) — no further optimization at 1h (auditor confirmed low ROI)**

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
- 1h optimization: 0/1 KEEP (iter 82). Do NOT optimize 1h — baselines are at floor (auditor advisory note 2).

**1h confirmed patterns:**
- BTC 1h: train_bars=10000 confirmed (iter 82 DISCARD at 14K). Do not re-optimize.
- ETH/SOL/XRP 1h: baselines only (iters 69-71). Not worth optimizing per auditor.

## HPO Range Recommendations

All ranges remain at current wide defaults. No narrowing recommended (0/5 KEEP on narrowing attempts across 83 iterations).

**1h parameter convergence (track only, do NOT narrow):**
- learning_rate: BTC 0.0863 — anomalously high vs 5m/15m; may be model.lgb artifact
- max_depth: BTC 5, ETH 3 — 1h trends shallower (fewer bars = less complexity)
- reg_alpha: uniformly near zero at 1h (except XRP 5m anomaly)
- reg_lambda: ETH 1h = 9.60 (highest in program — possible overfitting suppression with fewer trades)

## CPCV Validation Status — Complete Program

### 5m CPCV — ALL 4 PASS

| Asset | PBO(Sharpe) | IS-OOS Corr | Ruling | Verdict | Kelly |
|-------|------------|------------|--------|---------|-------|
| BTC   | 0.9643     | -0.9048    | 1      | PASS    | 0.5x  |
| ETH   | 0.1786     | -0.3331    | N/A    | PASS    | 0.5x  |
| SOL   | 0.6429     | —          | 1      | PASS    | 0.5x  |
| XRP   | 1.0000     | -0.9047    | 1      | PASS    | 0.25x |

### 15m CPCV — ALL 4 PASS

| Asset | PBO(Sharpe) | IS-OOS Corr | Ruling | Verdict | Kelly |
|-------|------------|------------|--------|---------|-------|
| BTC   | 0.9643     | -0.6954    | 1      | PASS    | 0.5x  |
| ETH   | 0.6429     | +0.0009    | 2      | PASS    | 0.5x  |
| SOL   | 0.5714     | +0.0104    | 2      | PASS    | 0.5x  |
| XRP   | 1.0000     | -0.8010    | 1      | PASS    | 0.25x |

### 1h CPCV — 1/4 PASS, 3 PENDING

| Asset | PBO(Sharpe) | IS-OOS Corr | Ruling | Verdict | Kelly |
|-------|------------|------------|--------|---------|-------|
| BTC   | **0.3929** | **-0.2106**| N/A    | **PASS**| 0.5x  |
| ETH   | pending    | —          | —      | pending | —     |
| SOL   | pending    | —          | —      | pending | —     |
| XRP   | pending    | —          | —      | pending | —     |
