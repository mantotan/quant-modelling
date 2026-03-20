# Strategy Directive
Updated: 2026-03-25T16:00:00Z
After iteration: 125

## Program Status: POST-OVERRIDE Anti-Starvation Rollout — Phase 2

The strategy queue from iter 119 is 5/6 executed (items 1-5 complete). Item 6 (ETH/5m min_child
narrowing [300,700]) is SKIPPED per audit note 3: range contraction has 0/5 KEEP rate and must
not be pursued until the full anti-starvation rollout is complete. SOL/15m has 16/40 trial
starvation and has NEVER received the n_estimators=[100,800] fix — this is the top remaining
anti-starvation target. Additionally, the auditor's conditional unlock of BTC/5m n_splits=6
(after items 3-6 complete) is now eligible since items 3-5 are done and item 6 is being skipped.
XRP/15m remains structurally starved with n_estimators=658 near ceiling even with [100,800] range.

---

## Priority Queue

1. **SOL/15m anti-starvation: apply n_estimators=[100,800] (highest urgency)**
   - Command: `--asset SOL --timeframe 15m --mode fast --save`
   - Knob change: hpo_search_space.n_estimators is already [100, 800] in knobs.json — no change needed
   - Rationale: SOL/15m has had persistent 16/40 trial starvation at EVERY run (iters 97, 109). This
     is the only multi-tp asset that has NOT yet received anti-starvation treatment. ETH/15m went
     16/40 -> 2/40 (worsened before fix) -> 23/40 after fix (iter 116 +0.275% KEEP). SOL/5m went
     2/40 -> 24/40 after fix (iter 121 +0.069% KEEP). n_estimators=[100,800] is ALREADY in
     knobs.json (set at iter 116 KEEP). Verify that best_knobs.json also has n_estimators=[100,800]
     before running. Expected result: 20-25/40 trials and likely Brier improvement from best 0.215443.
   - KEEP criterion: any Brier improvement from 0.215443 (iter 97 best)

2. **BTC/5m n_splits=6 experiment (auditor conditional unlock)**
   - Command: `--asset BTC --timeframe 5m --mode fast`
   - Knob change: walk_forward.n_splits = 6 (from 8)
   - Rationale: Auditor note 2 (iter 122 audit) conditionally suspends the BTC/5m n_splits blacklist
     after items 3-6 of the strategy queue complete. BTC/5m remains the most starved asset at 22/40
     trials even after the n_estimators=[100,800] fix (iter 122 DISCARD). Root cause: 929K
     samples/8 folds = ~116K samples/fold, each fold taking ~50s. Reducing to 6 folds means ~155K
     samples/fold (larger folds but fewer of them, net 25% time reduction). Expected: 28-32/40 trials.
     n_estimators=709 near ceiling with 8 folds; with 6 folds, HPO may converge to lower n_estimators
     (less starvation-driven ceiling pressure). Note: revert to n_splits=8 if DISCARD.
   - KEEP criterion: any Brier improvement from 0.17605 (iter 104 best)
   - Risk: smaller n_splits = less CV robustness; monitor OOS Brier carefully

3. **XRP/15m further ceiling reduction: n_estimators=[100,600]**
   - Command: `--asset XRP --timeframe 15m --mode fast`
   - Knob change: hpo_search_space.n_estimators = [100, 600] (from [100, 800])
   - Rationale: Iter 124 showed XRP/15m has n_estimators=658 near the 800 ceiling (same pattern as
     BTC/5m with 709 near ceiling). XRP/15m dataset = 309K samples. Reducing ceiling to 600 forces
     HPO to explore lower n_estimators; combined with XRP's num_leaves=106 per trial (high model
     complexity), this should significantly reduce per-trial time. Risk: XRP/15m true optimum may
     genuinely be at 600-700 n_estimators (similar to BTC/5m optimum near 709); test whether 600
     ceiling binds or not.
   - KEEP criterion: any Brier improvement from 0.218727 (iter 98 best)
   - Revert n_estimators to [100, 800] if DISCARD

4. **ETH/5m min_child narrowing [300,700] (deferred from item 6)**
   - Command: `--asset ETH --timeframe 5m --mode fast`
   - Knob change: hpo_search_space.min_child_samples = [300, 700] (from [100, 1000])
   - Rationale: This was item 6 in the previous strategy queue. It is queued here LAST because the
     auditor note 3 prohibits range contraction until anti-starvation is complete. After items 1-3
     above complete the remaining starvation fixes, this experiment is eligible. ETH/5m best_params
     min_child=389 (iter 117) — within [300,700] range. However, min_child narrowing has 0/5 KEEP
     rate historically. Only attempt if items 1-3 above are completed and the queue needs filling.
   - KEEP criterion: any Brier improvement from 0.211888 (iter 117 best)
   - NOTE: High prior probability of DISCARD based on 0/5 historical KEEP rate for range narrowing

---

## Observations

**KEEP rates by category (multi-tp era, iters 92-125, only rows with numeric Brier):**
- Anti-starvation n_estimators=[100,800]: 3/5 KEEP (60%): SOL/5m, ETH/15m, BTC/15m KEEP;
  BTC/5m and XRP/15m DISCARD (structural starvation persists — dataset too large for 800 ceiling)
- HPO range narrowing (lr, min_child, num_leaves): 0/6 KEEP (0%): iters 103, 105, 106, 108, 113,
  120 all DISCARD; BLACKLISTED
- HPO re-run (no knob changes): 4/8 KEEP (50%): iters 104, 107, 112, 115 KEEP; stochastic
- Reg parameter widening (reg_alpha, reg_lambda): 1/2 KEEP (50%): SOL/1h iter 125 KEEP;
  ETH/1h iter 113 DISCARD (reg_lambda widen)
- Walk-forward parameter changes (train_bars, purge_period): 2/5 KEEP in this era

**Convergence patterns from KEEP rows (multi-tp era):**
- n_estimators: Tick-dominant assets (ETH/SOL/XRP) converge to 182-274; BTC sniper assets prefer
  235-381 but press against 800 ceiling when dataset is large (BTC/5m 709, XRP/15m 658)
- learning_rate: BTC/1h uniquely low at 0.008-0.010; BTC/5m/15m: 0.021-0.027; ETH/SOL: 0.019-0.051;
  XRP: 0.012-0.065; current range [0.005, 0.1] adequate — no narrowing recommended
- max_depth: BTC consistent at 4-5; ETH/SOL/XRP consistent at 5-6; no ceiling hits
- min_child_samples: Wide 291-989 across assets — NOT converging; leave bounds unchanged
- reg_alpha: SOL/1h confirmed optimum ~0.919 (iter 125 KEY FINDING; current range [0.1, 20.0] is
  technically wasteful above ~3.0 but does not cause starvation — low priority to narrow)
- reg_lambda: Near-zero for most assets (1e-8 to 0.06); ETH/1h baseline was 9.42 but iter 113
  widen DISCARD confirmed [1e-8, 10.0] is correct range

**Feature importance stability (top-10 across all KEEP rows):**
- Universal top-3: partial_bar_position, partial_range (or vol_norm_distance for BTC sniper),
  elapsed_pct / time_remaining_pct
- BTC assets: vol_norm_distance rank 1-2, distance_from_open rank 2-3 (sniper pattern)
- ETH/SOL/XRP assets: partial_bar_position rank 1, partial_range rank 2
- Alpha features: NONE appear in top-10 across any KEEP row in multi-tp era. Funding, liquidation,
  OI features consistently absent from top-10 despite being in cached_features. These features
  may be contributing below top-10 or not at all — flag for auditor review.
- regime_vol_zscore: Appears in BTC KEEP rows (rank 6-10) but absent from ETH/SOL/XRP tick-dominant
  assets; SOL/1h iter 125 does NOT have it in top-5 (consistent with tick-dominant pattern)

**Brier trajectory (multi-tp baselines vs current bests):**
- BTC/5m: 0.177295 (baseline iter 92) -> 0.17605 (iter 104, -0.70%)
- BTC/15m: 0.171913 (baseline iter 95) -> 0.171809 (iter 123, -0.061%)
- BTC/1h: 0.175668 (baseline iter 99) -> 0.174864 (iter 107, -0.46%)
- ETH/5m: 0.211888 (baseline iter 117) — no improvement yet (single run)
- ETH/15m: 0.209819 (baseline iter 96) -> 0.208324 (iter 116, -0.71%)
- ETH/1h: 0.211438 (baseline iter 100) — no improvement (narrowing attempts failed)
- SOL/5m: 0.218209 (baseline iter 93) -> 0.218058 (iter 121, -0.069%)
- SOL/15m: 0.215443 (baseline iter 97) — NO improvement yet (anti-starvation untried)
- SOL/1h: 0.221683 (baseline iter 101) -> 0.220615 (iter 125, -0.048%)
- XRP/5m: 0.221782 (baseline iter 94) -> 0.221503 (iter 112, -0.126%)
- XRP/15m: 0.218727 (baseline iter 98) — no improvement (starvation prevents it)
- XRP/1h: 0.226947 (baseline iter 102) -> 0.226907 (iter 115, -0.018%)
- SUMMARY: 8/12 asset-timeframes have shown improvement from multi-tp baseline. SOL/15m and
  XRP/15m have not improved — both starvation-limited. ETH/5m and ETH/1h also flat.
  Largest gains: BTC/5m -0.70%, ETH/15m -0.71%, BTC/1h -0.46%.

---

## Risk Profile

- Max drawdown trend: stable — BTC assets highest DD (0.22-0.39), ETH/XRP 1h lowest (0.063-0.088)
  BTC/5m DD=0.39 is stable across iters 92/104/122; no growth trend detected
- Max DD / PnL ratio: BTC/5m 0.39/56=$0.39 vs $56 PnL (ratio 0.007 — healthy); BTC/15m 0.18/$50
  (ratio 0.004); BTC/1h 0.22/$12 (ratio 0.018); all within acceptable range (<1.0)
- Trade count range (KEEP rows, multi-tp era): 5m ~80K, 15m ~60-77K, 1h ~18-19K; stable
- Win rate range: BTC 62-67% (sniper), ETH/SOL/XRP ~49-51% (tick-dominant); STABLE
- HPO-OOS gap: XRP/15m hpo_objective=0.498 elevated (Brier-scale penalty; consistent with XRP/15m
  starvation generating suboptimal models); other assets: hpo_objective tracks oos_brier within 3%
  typical gap; no widening trend detected

---

## Timeframe Coverage

- 5m: 33 iterations, 16 KEEPs (11/12 KEEP+VALIDATION-PASS+KEEP-VERIFIED), best: BTC 0.17605
- 15m: 29 iterations, 13 KEEPs, best: BTC 0.171809
- 1h: 27 iterations, 12 KEEPs, best: BTC 0.174864
- Recommendation: BALANCED — all timeframes adequately covered. Rotate per priority queue above.
  SOL/15m anti-starvation (item 1) addresses the only untreated starvation case.

---

## Blacklist

- HPO range narrowing (lr, min_child, num_leaves, reg_lambda bounds): 0/6 KEEP across all
  assets/timeframes (iters 103, 105, 106, 108, 113, 120). PERMANENT BLACKLIST until further notice.
  Exception: widen-type experiments (expanding bounds) remain eligible (1/2 KEEP from reg_alpha
  widen iter 125)
- BTC/5m n_splits=8 for HPO coverage improvement: DISCARD at iters 104 and 122 — 8 folds causes
  structural starvation at BTC/5m scale; n_splits=6 is the conditional path (item 2 above)
- max_depth > 6 for any asset: DISCARD at iter 41 (SOL); current [2,6] range confirmed correct
- train_bars increases above per-asset ceiling (BTC 10K, SOL/XRP 10K, ETH 14K): multiple DISCARDs
- drawdown_penalty_weight increases: non-binding for tick-dominant assets (iters 40, 54); DISCARD
- objective.primary = sharpe: no improvement vs brier-primary (iter 42); DISCARD
- ETH/5m min_child narrowing [300,700]: HIGH PRIOR PROBABILITY OF DISCARD (0/5 narrowing rate);
  only attempt as queue-filler after items 1-3 complete

---

## HPO Range Recommendations

- n_estimators: KEEP [100, 800] for all assets. BTC/5m and XRP/15m may need further ceiling
  reduction (see priority items 2 and 3 above), but global range stays at [100, 800].
- learning_rate: KEEP [0.005, 0.1]. Lower bound 0.005 is needed for BTC/1h (optimal lr=0.008-0.010).
  Upper bound 0.1 occasionally used by XRP. No change.
- reg_alpha: SOL/1h optimum ~0.919 confirmed. Current range [0.1, 20.0] is mildly wasteful above
  ~3.0 but does NOT cause starvation at SOL/1h scale (40/40 trials, 241s). Low priority to narrow;
  leave unchanged for now.
- reg_lambda: KEEP [1e-8, 10.0]. ETH/1h confirms optimal near lower end (~0.014). No change.
- min_child_samples: KEEP [100, 1000]. No convergence signal; changing this causes DISCARDs.
- num_leaves: KEEP [16, 128]. XRP/1h consistently optimizes to 34 (mid-range); BTC uses 40-100;
  ETH/SOL use 33-70. Range is adequate.

---

## Notes for Next Auditor

- SOL/15m anti-starvation (item 1) is the clearest remaining anti-starvation lever. A KEEP here
  would complete the anti-starvation rollout for all 6 originally identified starved assets.
- After item 1, if BTC/5m n_splits=6 (item 2) yields a KEEP, consider whether the BTC/5m
  blacklist for n_splits should be updated to allow n_splits=6 as the BTC/5m standard.
- Alpha features (funding, liquidation, OI, IV, polymarket) have NOT appeared in any top-10
  feature importance across the multi-tp era. This is a potential signal that these features
  are not contributing — consider adding an explicit alpha-ablation experiment to future queue.
- Tick-dominant pattern (partial_bar_position + partial_range dominating SHAP) is remarkably
  stable across all assets/timeframes in multi-tp era. This suggests the model primarily learns
  bar micro-structure rather than market context. The Polymarket deployment value depends on
  whether this micro-structure edge is exploitable via limit orders.
