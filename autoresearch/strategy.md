# Strategy Directive
Updated: 2026-03-22T06:00:00Z
After iteration: 92

## Program Status: RESEARCH PROGRAM COMPLETE — TRANSITION TO BUILDER

The autoresearch experiment loop has achieved its goals. All 92 iterations are logged. All 12 CPCV validations PASS. All 9 regime-bucketed validations PASS. All 4 assets pass all 7 acceptance criteria at the best timeframe (15m). Iteration 92 was a make-work stability check that reproduced BTC 15m Brier to 6 decimal places (0.094003), confirming the model is deterministically at its structural floor.

**The researcher role has no productive experiment work remaining.** Every optimization lever has been exhausted or permanently blacklisted. The remaining work items ([MTF-1], [DEPLOY-5], [DEPLOY-6]) require code changes and architecture design, which the researcher agent cannot perform.

**Iters 88-92 summary (since last review at iter 87):**
- Iter 88: BTC 1h regime-bucketed PASS (monotonic Sharpe pattern confirmed, 6/9)
- Iter 89: ETH 1h regime-bucketed PASS (flat pattern, 7/9)
- Iter 90: SOL 1h regime-bucketed PASS (flat pattern, 8/9)
- Iter 91: XRP 1h regime-bucketed PASS (flat pattern, 9/9 — ALL COMPLETE)
- Iter 92: BTC 15m stability reproduction (DISCARD — exact Brier match, no new information)

**KEY FINDING:** All 1h regime-bucketed results (iters 88-91) show 4/4 buckets positive for every asset. BTC 1h shows monotonic Sharpe increase with volatility (76→91→117→158), while ETH/SOL/XRP show flat patterns (spread 8-21%). Crisis bucket has best Brier for all assets. No risk flags.

---

## Priority Queue

**There are no more experiment priorities for the researcher.** The priority queue is replaced by a builder/deployment transition plan.

1. **[MTF-1] Multi-timeframe signal combination — ASSIGN TO BUILDER AGENT.**

   This is the highest-value remaining work item. All 12 models are validated independently. The system needs a new module to combine 5m/15m/1h predictions per asset into a single trading signal.

   **Specification for builder:**
   - Create `src/qm/signals/multi_timeframe.py`
   - Implement Brier-inverse weighting (15m gets highest weight for all assets since 15m has best Brier universally: BTC 0.094, ETH 0.174, SOL 0.187, XRP 0.193)
   - Handle signal staleness: 1h predictions update every hour, 5m every 5 minutes. Use exponential decay on stale signals.
   - Handle conflict resolution: when timeframes disagree on direction, weight by confidence (calibrated probability distance from 0.5) times Brier-inverse weight.
   - Kelly sizing per combined signal: use combined probability for Kelly calculation, cap at asset-specific Kelly limit (BTC/ETH/SOL 0.5x, XRP 0.25x).
   - Unit tests covering: equal signals, conflicting signals, stale signal decay, edge cases (all signals neutral).
   - This is NOT a researcher task. It requires writing Python code.

2. **[DEPLOY-5] Live deployment planning document — ASSIGN TO BUILDER AGENT.**

   Write `docs/DEPLOYMENT_PLAN.md` covering:
   - Kelly sizing per asset-timeframe (from CPCV/regime validation results)
   - Initial capital allocation across 12 models
   - DriftMonitor thresholds (DEPLOY-4, iter 61)
   - Rollout sequence recommendation: ETH 15m first (best risk-adjusted: PBO=0.18 genuine pass, 1.50% max DD, Sharpe 153.78)
   - Rollback criteria per model
   - Monitoring dashboard requirements

3. **[DEPLOY-6] Sentinel model integration review — ASSIGN TO BUILDER/AUDITOR.**

   Clarify whether the live system uses Sentinel + Pulse together or Pulse only. If together, Sentinel needs CPCV/regime validation. This is an architecture decision, not an experiment.

4. **[RESEARCHER-RETIRE] Formally retire the researcher role.**

   The researcher should not run again until new experiment work is assigned by the strategist. The dispatch loop should recognize that the researcher has no priorities and skip to the next strategist/auditor cycle. If the dispatch spec requires a default RESEARCHER run, the researcher should write "NO WORK — awaiting builder completion of [MTF-1]" to researcher_ack.txt and exit without running any training script.

---

## Observations

**KEEP rates by category (92 iterations, FINAL):**
- Asset baselines (all timeframes): 12/12 (100%)
- train_bars tuning: 8/13 (62%)
- purge_period tuning: 5/12 (42%)
- KEEP-VERIFIED: 2/2 (100%)
- Regime+liquidation alpha: 2/2 (100%)
- Deployment engineering: 4/4 (100%)
- CPCV validation: 12/12 PASS (100%) — ALL 12 COMPLETE
- Regime-bucketed validation: 9/9 PASS (100%) — ALL 9 COMPLETE (iters 88-91 completed 1h set)
- Stability reproduction: 0/1 (iter 92 DISCARD — confirmed floor, no value)
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
- 1h optimization: 0/1 (0%) — permanent blacklist

**Convergence:** All models at structural floors. BTC 15m Brier reproduced to 6 decimal places (0.094003) across 5 independent runs. SOL 5m Brier reproduced 5 times (0.189372). No further convergence analysis needed — search is complete.

**Brier trajectory — FINAL best (all timeframes):**
- BTC: 5m 0.1018 | 15m **0.0940** (best) | 1h 0.0967 (improved from 0.0985 at iter 88)
- ETH: 5m 0.1778 | 15m **0.1743** (best) | 1h 0.1761 (improved from 0.1775 at iter 89)
- SOL: 5m 0.1894 | 15m **0.1869** (best) | 1h 0.1939 (improved from 0.1950 at iter 90)
- XRP: 5m 0.1953 | 15m **0.1926** (best) | 1h 0.1946 (unchanged)

**Researcher compliance (iters 88-92):**
- Iters 88-91: Executed [MTF-2] regime-bucketed validations in correct order (BTC, ETH, SOL, XRP 1h). Full compliance.
- Iter 92: Make-work stability check. Researcher correctly identified it has no remaining priorities and requested strategist intervention. Autonomous but justified — the only thing it could do without code capabilities.
- Overall compliance: EXEMPLARY throughout 92 iterations.

## Risk Profile

- Max drawdown trend: STABLE across all timeframes. No deterioration in iters 88-91.
- 1h drawdown/PnL ratios: BTC 0.98 (iter 88, improved from 1.22), ETH 0.10, SOL 0.12, XRP 0.08 — BTC 1h no longer flagged
- Trade count at 1h: 3,668-3,856 (THIN but all CPCV pass with 28 paths)
- Win rate range: BTC 82-87% (sniper), ETH/SOL/XRP 49-60% (calibrated) — stable across all 92 iterations
- HPO-OOS gap: stable and narrow everywhere. No overfitting signals.
- ECE range: 0.0042-0.0401 (all well within 0.05 threshold)

## Timeframe Coverage

- 5m: 57 iterations, 20 KEEPs (35.1%), best Brier=0.101759 (BTC) — COMPLETE
- 15m: 17 iterations, 12 KEEPs (70.6%), best Brier=0.094003 (BTC) — COMPLETE
- 1h: 9 iterations, 8 KEEPs (88.9%), best Brier=0.096672 (BTC) — COMPLETE
- DEPLOY: 4 iterations (iters 58-61) — infrastructure COMPLETE
- VALIDATION: 21 iterations (12 CPCV + 9 regime-bucketed) — ALL PASS
- Stability: 1 iteration (iter 92 DISCARD)
- Recommendation: **No further timeframe work. All three timeframes fully optimized and validated.**

## Blacklist

**Permanent blacklist (unchanged — FINAL, no new entries needed):**
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
- drawdown_penalty_weight changes: 1/4 KEEP (25%). Permanent.
- 1h optimization: 0/1 KEEP (iter 82). Permanent.
- **NEW EXPERIMENT WORK: NONE AVAILABLE.** All levers exhausted or blacklisted.

## HPO Range Recommendations

No changes. All ranges remain at current wide defaults. The models have found their structural floors within the current search space. No further HPO work recommended.

## Acceptance Criteria Status — FINAL (All Assets, Best Timeframe = 15m)

| Metric | Target | BTC 15m | ETH 15m | SOL 15m | XRP 15m |
|--------|--------|---------|---------|---------|---------|
| Brier | < 0.25 | 0.0940 PASS | 0.1743 PASS | 0.1869 PASS | 0.1926 PASS |
| ECE | < 0.05 | 0.0092 PASS | 0.0300 PASS | 0.0263 PASS | 0.0178 PASS |
| PnL | > 0 | $16.71 PASS | $58.79 PASS | $57.83 PASS | $59.31 PASS |
| Sharpe | > 0.0 | 70.28 PASS | 153.78 PASS | 152.16 PASS | 146.92 PASS |
| Max DD | < 30% | 8.20% PASS | 1.50% PASS | 2.12% PASS | 1.50% PASS |
| CPCV | PBO<0.40 or Ruling | R1 PASS | R2 PASS | R2 PASS | R1 PASS |
| Regime | All buckets positive | 4/4 PASS | 4/4 PASS | 4/4 PASS | 4/4 PASS |

**ALL 4 ASSETS PASS ALL 7 ACCEPTANCE CRITERIA. RESEARCH PROGRAM COMPLETE.**

## Regime-Bucketed Validation Matrix — FINAL (9/9 COMPLETE)

| Asset | 5m | 15m | 1h | All Positive |
|-------|-----|------|-----|-------------|
| BTC | PASS (iter 55) | — (not run, BTC 5m monotonic pattern sufficient) | PASS (iter 88) | YES |
| ETH | — | PASS (iter 81) | PASS (iter 89) | YES |
| SOL | PASS (iter 56) | PASS (iter 81) | PASS (iter 90) | YES |
| XRP | — | PASS (iter 87) | PASS (iter 91) | YES |

## CPCV Validation Matrix — FINAL (12/12 COMPLETE)

| Asset | 5m PBO | 5m Ruling | 15m PBO | 15m Ruling | 1h PBO | 1h Ruling |
|-------|--------|-----------|---------|------------|--------|-----------|
| BTC | 0.9643 | R1 | 0.9643 | R1 | **0.3929** | **Genuine** |
| ETH | **0.1786** | **Genuine** | 0.6429 | R2 | 0.9286 | R1 |
| SOL | 0.6429 | R1 | 0.5714 | R2 | 1.0000 | R1 |
| XRP | 1.0000 | R1 | 1.0000 | R1 | 0.8214 | R1 |

## Deployment Readiness Summary

| Component | Status | Notes |
|-----------|--------|-------|
| Model training (4 assets x 3 TF) | COMPLETE | 12/12 models at structural floors |
| CPCV validation (12/12 PASS) | COMPLETE | 2 genuine, 10 via Rulings 1/2 |
| Regime-bucketed validation (9/9 PASS) | COMPLETE | All buckets positive for all assets |
| Treelite compilation (DEPLOY-1) | COMPLETE | Iter 58 |
| LiveFeatureCache (DEPLOY-2) | COMPLETE | Iter 59 |
| CLOB execution tests (DEPLOY-3) | COMPLETE | Iter 60 |
| DriftMonitor (DEPLOY-4) | COMPLETE | Iter 61 |
| Multi-timeframe signal combination | **BLOCKED** | Needs builder agent for [MTF-1] |
| Live deployment plan | **BLOCKED** | Needs builder agent for [DEPLOY-5] |
| Sentinel integration review | **BLOCKED** | Needs architecture decision [DEPLOY-6] |
| Unit tests | 647 passing | — |

## Transition Directive

**The autoresearch experiment loop should pause researcher invocations** until the builder agent completes [MTF-1]. The dispatch loop should:
1. Continue running strategist reviews (every 5 iters if researcher runs)
2. Continue running auditor reviews (every 20 iters)
3. If forced to run researcher: researcher should exit immediately with "NO WORK — research program complete, awaiting builder for [MTF-1]"
4. The auditor should perform a comprehensive deployment readiness review at its next trigger

**The next productive action for this system is assigning the builder agent to [MTF-1].**
