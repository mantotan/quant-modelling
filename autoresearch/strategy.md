# Strategy Directive
Updated: 2026-03-21T01:00:00Z
After iteration: 62

## Program Status: 15m TIMEFRAME EXPANSION — PHASE 1

All 4 assets fully validated on 5m (iters 1-57). Deployment infrastructure complete (iters 58-61).
Iteration 62 opened the 15m timeframe with a BTC baseline that BEAT the 5m structural floor
(Brier 0.0949 vs 0.1018, 6.8% improvement). This is the most significant new signal since
iter 14 (time_pcts reduction). The 15m expansion is now the primary research frontier.

---

## Priority Queue

The following are ordered experiments for the 15m timeframe expansion. The researcher should
execute these in order, applying the same systematic methodology proven across 57 iterations
of 5m optimization. Each experiment is one iteration.

1. **[15m-2] ETH 15m baseline — establish ETH 15m anchor with BTC-optimal knobs.**

   Use identical knobs as BTC 15m iter 62 (train_bars=14000, purge_period=24, n_splits=8,
   time_pcts=[0.30,0.50,0.80], 22 cached features + regime). ETH was tick-dominant on 5m;
   test whether 15m preserves or changes the feature profile. Expected: ETH 15m Brier in
   range 0.16-0.19 (15m should improve ETH similarly to BTC since longer bars give more
   microstructure signal per snapshot).

   Rationale: BTC 15m showed regime_vol_zscore SHAP rank 6 (BTC-class confirmed at 15m).
   ETH 15m will reveal whether tick-dominance persists or regime features gain importance
   at the longer timeframe. This is the highest-information experiment available.

2. **[15m-3] SOL 15m baseline — establish SOL 15m anchor.**

   Same knobs as ETH 15m. SOL was tick-dominant on 5m with the weakest Brier (0.1894).
   15m may offer proportionally larger gains for SOL since tick features aggregate more
   information over longer bars. Compare SOL 15m vs SOL 5m improvement ratio against
   BTC 15m vs BTC 5m ratio (6.8%) to detect asset-class differences at 15m.

3. **[15m-4] XRP 15m baseline — complete 15m asset rotation.**

   Same knobs. XRP was the last 5m asset; complete the 15m baseline sweep. XRP's
   BTC-class fold behavior (IS-OOS corr=-0.90) may produce different 15m dynamics.
   Watch for reg_alpha changes — XRP had extreme L1 (4.13) at 5m.

4. **[15m-5] BTC 15m train_bars exploration — test 10000 vs 14000 ceiling.**

   BTC 5m ceiling was 10000 bars (lower than ETH/SOL/XRP at 14000). At 15m, bars are
   3x longer in wall-clock time, so 14000 bars covers 3x more temporal history. Test
   train_bars=10000 to see if BTC 15m follows the 5m pattern (shallower tree, lower
   train_bars ceiling). If BTC 15m Brier improves at 10000, this confirms the
   asset-class-specific ceiling scales with bar duration.

5. **[15m-6] Best-performing 15m asset: purge_period optimization.**

   After baselines for all 4 assets, take the best 15m performer and test purge_period.
   At 15m, the temporal leakage horizon may differ from 5m — 6 bars of embargo covers
   90 minutes (vs 30 min at 5m). The optimal purge_period may need adjustment for the
   longer timeframe.

6. **[1h-1] BTC 1h baseline — open the third timeframe.**

   After 15m baselines are complete for all 4 assets, open 1h with BTC. The 1h timeframe
   is the final frontier. Expected: further Brier improvement if the 5m→15m pattern
   (6.8% improvement) extrapolates, but diminishing returns are likely as bar duration
   increases.

---

## Observations

**KEEP rates by category (all 62 iterations, final 5m + early 15m):**
- Asset baselines: 5/5 (100%) — iters 7 (BTC 5m), 23 (ETH 5m), 37 (SOL 5m), 51 (XRP 5m), 62 (BTC 15m)
- KEEP-VERIFIED runs: 2/2 (100%) — iters 8, 14
- train_bars extension: 5/7 (71%) — KEEP iters 8, 18, 25, 38; DISCARD iter 52 (XRP ceiling)
- purge_period tuning: 4/8 (50%) — KEEP iters 22, 29, 39, 53
- Regime+liquidation alpha features (BTC): 2/2 (100%)
- drawdown_penalty_weight: 1/2 (50%)
- Deployment engineering: 4/4 (100%) — iters 58-61
- Validation/CPCV runs: 11/11 complete — ETH PASS, BTC PASS (regime), SOL PASS (regime), XRP PASS (composite)
- Funding features: 0/3 (0%) — permanent blacklist
- HPO range narrowing: 0/5 (0%) — permanent blacklist
- Interaction features: 0/1 (0%) — permanent blacklist
- n_splits changes: 0/4 (0%) — permanent blacklist
- embargo_period changes: 0/2 (0%) — permanent blacklist

**15m vs 5m comparison (BTC iter 62 vs BTC 5m best):**
- Brier: 0.0949 vs 0.1018 (6.8% improvement at 15m)
- OOS accuracy: 0.8707 vs 0.8598 (1.3% higher at 15m)
- Backtest PnL: $16.34 vs $45.55 (fewer bars at 15m = fewer trades)
- Backtest Sharpe: 68.01 vs 109.25 (lower due to fewer trades)
- Max DD: 7.31% vs 13.61% (lower at 15m — better risk profile)
- Trades: 14,834 (15m) vs 43,721 (5m) — 3x fewer trades as expected from 3x longer bars
- SHAP: regime_vol_zscore rank 6 (vs rank 7 at 5m) — regime features slightly MORE important at 15m
- reg_alpha: 0.0 at 15m (vs 2.854 at 5m) — dramatically different regularization regime
- Key new finding: distance_from_open and vol_norm_distance dominate at 15m (tick features evolve)

**Brier trajectory — current state:**
- BTC 5m: 0.101759 (frozen since iter 22, structural floor)
- BTC 15m: 0.094907 (iter 62, NEW BEST across all timeframes)
- ETH 5m: 0.177772 (frozen since iter 32)
- SOL 5m: 0.189372 (frozen since iter 39)
- XRP 5m: 0.195309 (frozen since iter 53)
- ETH/SOL/XRP 15m: not yet tested

**Researcher compliance:**
The researcher followed the previous strategy directive completely:
- DEPLOY-1 through DEPLOY-4 executed in order (iters 58-61)
- 15m expansion initiated with BTC baseline (iter 62)
- Iteration 62 used existing knobs (train_bars=14000, appropriate for 15m)
- Results properly logged with timeframe column

## Risk Profile

- Max drawdown trend: BTC 15m shows 7.31% (improved from 13.61% at 5m)
- Trade count: 14,834 at 15m (expected 3x reduction from 5m's 43,721)
- Win rate: 86.4% at 15m (vs 86.97% at 5m — stable, consistent)
- HPO-OOS gap: 0.090246 (HPO) vs 0.094907 (OOS Brier) = 0.00466 gap (4.9%, healthy)
- bs_sharpe: 54.20 at 15m (single-side 68.01 dominant — BTC-class confirmed at 15m)
- DD/PnL ratio: 7.31/16.34 = 0.447 (healthy, below 1.0 threshold)

**Key risk observation:** BTC 15m reg_alpha=0 is a notable departure from BTC 5m reg_alpha=2.854.
This suggests the 15m feature landscape is less prone to overfitting (longer bars = less noise),
allowing the model to use all features without L1 sparsity. Monitor whether this persists across
ETH/SOL/XRP 15m baselines — if all 15m models converge to reg_alpha~0, the 15m timeframe may
produce simpler, more robust models.

## Timeframe Coverage

- 5m: 57 iterations, 20 KEEPs (40.8%), best Brier=0.101759 (BTC) — COMPLETE, all 4 assets at structural floor
- 15m: 1 iteration, 1 KEEP (100%), best Brier=0.094907 (BTC) — JUST STARTED, 3 baselines pending
- 1h: 0 iterations — deferred until 15m baselines complete
- Recommendation: **Focus on 15m for next 5-8 iterations** (4 baselines + optimization of best performer). Open 1h after 15m asset sweep.

## Blacklist

All 5m blacklist items remain in force. Additionally:

**Inherited from 5m (apply to all timeframes unless 15m data contradicts):**
- Interaction features: 0/1 KEEP (iter 6, +41% Brier regression). Permanent.
- Funding features in cached_features: 0/3 KEEP (iters 2, 27, 43). Permanent for 5m. Test once at 15m for one asset — funding settles every 8h, so 15m bars (4 per hour) may capture more funding variance than 5m bars (12 per hour). If DISCARD at 15m, permanent blacklist extends to all timeframes.
- HPO range narrowing: 0/5 KEEP (iters 10, 13, 15, 19, 20). Permanent all timeframes.
- n_splits != 8: 0/4 KEEP. Permanent all timeframes.
- embargo_period != 6: 0/2 KEEP. Permanent all timeframes (but note: 6 bars = 90min at 15m vs 30min at 5m — if 15m models show leakage patterns, revisit).
- max_depth > 6: 0/1 KEEP (SOL iter 41). Permanent all timeframes.
- Sharpe-primary objective: 0/1 KEEP (SOL iter 42). Permanent all timeframes.
- regime_params window changes: 0/3 KEEP. Permanent all timeframes.
- Manual feature pruning: 0/2 KEEP. Permanent all timeframes.

**New observation to track at 15m:**
- BTC 15m reg_alpha=0 (vs 2.854 at 5m). Do NOT attempt to force reg_alpha at 15m — let HPO find the landscape. If all 15m assets converge to reg_alpha~0, document as a structural finding.

## HPO Range Recommendations

All ranges remain at current wide defaults — validated as optimal across 57 iterations of 5m work.
No narrowing recommended. The wide [0.005, 0.1] learning_rate range is especially important at 15m
where the optimal lr may differ from 5m values (BTC 15m has not yet been deeply explored).

**15m-specific notes:**
- train_bars=14000 at 15m covers 3x more wall-clock time than at 5m. If 15m assets show HPO
  starvation (< 25 trials), reduce train_bars to 10000 as first diagnostic before other changes.
- The n_splits=8 setting may need reassessment at 15m: fewer total bars at 15m means each fold
  is smaller. Monitor if OOS evaluation quality degrades. But do NOT change n_splits preemptively —
  only if 15m baselines show anomalous validation behavior.

---

## 15m Expansion Protocol

For each 15m baseline, the researcher should:
1. Generate 15m dataset for the target asset (if not already cached)
2. Use current knobs.json (train_bars=14000, purge_period=24, n_splits=8)
3. Run standard HPO (40 trial target, 600s timeout)
4. Log to results.tsv with timeframe=15m
5. Compare Brier vs same-asset 5m best to measure timeframe lift
6. Note any SHAP feature profile changes vs 5m (especially regime vs tick dominance)

After all 4 baselines complete, rank assets by 15m Brier and select the top performer
for 2-3 optimization iterations (train_bars, purge_period only — skip blacklisted knobs).

## Deployment Integration

The 15m models are additive to the 5m deployment. They do NOT replace 5m models. The eventual
live system should run both timeframes:
- 5m model: fires at t=0.80 of each 5m bar (every 4 minutes)
- 15m model: fires at t=0.80 of each 15m bar (every 12 minutes)
- Signal combination: to be designed after 15m validation. Options include ensemble averaging,
  timeframe-weighted Kelly, or independent position sizing per timeframe.

This is a research question for a future strategist review after 15m CPCV validation.
