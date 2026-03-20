# Strategy Directive
Updated: 2026-03-23T03:00:00Z
After iteration: 103

## Program Status: POST-OVERRIDE Autonomous HPO Phase

The OVERRIDE is 100% complete (12/12 pulse_v2 models saved). Iter 103 was the first post-OVERRIDE autonomous experiment — a BTC/1h HPO narrowing attempt that correctly failed because the proposed lr lower bound (0.015) excluded the optimal lr=0.009. The researcher's self-diagnosis was accurate. The program is now in open-ended HPO exploration mode with no structural blockers.

The auditor (iter 102 report) authorized HPO exploration only — no code-change experiments ([MTF-1] deferred). This strategy directive assigns a focused priority queue for autonomous HPO.

---

## Priority Queue

1. **BTC/5m — full 40-trial HPO re-run** (highest urgency: only 22/40 trials at baseline, +74% Brier gap vs single-tp)
   - Knob changes: no changes to hpo_search_space bounds
   - Use: `--asset BTC --timeframe 5m --mode fast --save`
   - Constraints: keep lr lower bound at 0.005 (do NOT raise), keep max_depth ceiling at 6
   - Expected outcome: BTC/5m currently at 0.177295 with severely starved HPO. With full 40 trials, the sniper-pattern optimum (lr ~0.009-0.015, max_depth 4-5) has a higher chance of being found. Target: push toward 0.165-0.170 range.
   - KEEP criterion: any Brier improvement from 0.177295

2. **BTC/15m — full 40-trial HPO re-run** (second priority: only 18/40 trials, +83% Brier gap — worst HPO starvation in dataset)
   - Knob changes: no changes
   - Use: `--asset BTC --timeframe 15m --mode fast --save`
   - Same reasoning as BTC/5m: current baseline severely underexplored
   - Target: push from 0.171913 toward 0.160-0.165 range
   - KEEP criterion: any Brier improvement from 0.171913

3. **BTC/1h — min_child_samples increase experiment** (auditor recommended: "increasing min_child_samples to 500-800 to suppress early-bucket noise")
   - Knob change: narrow `hpo_search_space.min_child_samples` to [400, 800] (currently [100, 1000])
   - Rationale: iter 103 found min_child=468 as optimal even in the failed run. Concentrating search in this range should help HPO find better solutions faster. Critically, lr lower bound must remain at 0.005 to allow lr=0.009 to be discoverable.
   - Also narrow `hpo_search_space.num_leaves` to [16, 64] — iter 99 optimal was 51, iter 103 found 63. Narrower range saves HPO budget.
   - Use: `--asset BTC --timeframe 1h --mode fast --save`
   - KEEP criterion: any Brier improvement from 0.175668

4. **BTC/1h — num_leaves narrowing + lr preservation** (if item 3 discards)
   - Knob changes: narrow `hpo_search_space.num_leaves` to [32, 96], keep lr [0.005, 0.03] (enforce that lr space is concentrated near optimal 0.009)
   - This avoids the iter 103 mistake: DO NOT raise lr lower bound above 0.01
   - KEEP criterion: any Brier improvement from 0.175668

5. **ETH/1h — min_child_samples increase** (auditor noted this as 3rd priority)
   - Knob change: narrow `hpo_search_space.min_child_samples` to [200, 600]
   - Current ETH/1h best_params lr=0.010, max_depth=4, num_leaves=26 — already found with 40 trials, so space narrowing may help convergence quality
   - Use: `--asset ETH --timeframe 1h --mode fast --save`
   - KEEP criterion: any Brier improvement from 0.211438

6. **SOL/15m — additional HPO trials** (starvation: 16/40 trials)
   - Knob changes: no changes
   - Use: `--asset SOL --timeframe 15m --mode fast --save`
   - Target: push from 0.215443 with better HPO coverage
   - KEEP criterion: any Brier improvement from 0.215443

---

## Observations

**KEEP rates by category (post-migration rows only, iters 7-103):**
- Multi-TP revalidation (iters 92-102): 11/11 KEEP (100%) — expected, all are first-pass baselines
- HPO range narrowing (iters 10,13,15,19,20,103): 0/6 KEEP (0%) — BLACKLISTED when raising lower bounds
- Walk-forward tuning (train_bars, purge_period): 15/30 (50%) — productive lever
- Feature selection/addition (funding, regime, OI): 5/15 (33%)
- Objective tuning (primary, penalty weights): 1/6 (17%)
- Validation runs (CPCV, regime-bucketed): counted separately, not experiments

**HPO convergence patterns across multi-tp KEEP runs (iters 92-102):**
- BTC assets: lr clusters in [0.009, 0.025] — optimal is lr ~0.009. Never raise lower bound above 0.01.
- Tick-dominant (ETH/SOL/XRP): lr clusters in [0.010, 0.065] — wider acceptable range
- max_depth: BTC prefers 4-5, tick-dominant 5-6
- num_leaves: BTC/1h converges to 26-63 (median ~50); tick-dominant ranges 19-115 (no convergence)
- reg_alpha: BTC/1h iter 99 = 3.9e-5 (near-zero); ETH/1h iter 100 = 0.146 (notable L1); SOL/1h iter 101 = unreported; XRP/1h iter 102 = 3.1e-5 (near-zero)
- min_child_samples: iter 103 (BTC/1h DISCARD) found optimal = 468. This is the clearest signal for the BTC HPO space — needs [400, 800] range focus.

**Brier trajectory:**
- Multi-TP regime is a fundamentally different task than single-TP (averaging over 5 buckets including early noisy ones): all assets show 14-83% Brier increase. BTC sniper pattern causes the largest multi-tp degradation because early buckets (t10=42%, t20=49%) are far from the t80 signal.
- Post-OVERRIDE, the first lever is improving HPO coverage for the most underexplored runs (BTC/5m 22 trials, BTC/15m 18 trials, BTC/1h 27 trials).

---

## Risk Profile

- Max drawdown trend: stable — 1h assets at 0.06-0.28, 5m assets at 0.07-0.34 (within pre-OVERRIDE ranges)
- Trade count range across KEEP rows (iters 92-102): 5m 76K-81K, 15m 62K-77K, 1h 16K-19K (healthy)
- Win rate range: BTC-class 59-72% (sniper pattern), tick-dominant 49-52% (flat calibrated)
- HPO-OOS gap: hpo_objective ≈ oos_brier for all rows (trade penalty non-binding, brier primary). Gap is structural zero — no overfitting signal.
- XRP/1h ECE=0.0356 is the outlier — highest calibration error in the multi-tp suite. Monitor if it worsens.

---

## Timeframe Coverage

- 5m: 57 iterations, 25 KEEP/KEEP-VERIFIED/VALIDATION-PASS, best multi-tp Brier (BTC) = 0.177295 (iter 92)
- 15m: 22 iterations, 16 KEEP/KEEP-VERIFIED/VALIDATION-PASS, best multi-tp Brier (BTC) = 0.171913 (iter 95)
- 1h: 20 iterations, 11 KEEP/KEEP-VERIFIED/VALIDATION-PASS, best multi-tp Brier (BTC) = 0.175668 (iter 99)
- Recommendation: **focus on BTC HPO across all three timeframes** — BTC has the largest single-to-multi-tp gap and the most underexplored HPO space (18-27 trials vs 40 target). After BTC saturation, rotate to ETH/1h (item 5).

---

## Blacklist

- **HPO lower bound raising (lr > 0.01)**: 6/6 DISCARDs (iters 10, 13, 15, 19, 20, 103). Iter 103 definitively confirmed: BTC optimal lr=0.009 is below 0.015 new lower bound → always fails. PERMANENT blacklist: never raise lr lower bound above 0.005 for BTC.
- **Interaction features**: 1/1 DISCARD (iter 6, Brier +42% regression). No evidence of value in any subsequent SHAP data.
- **Funding features**: 0/3 KEEP across BTC (iter 2), ETH (iter 27), SOL (iter 43). Funding absent from top-10 SHAP in all assets. Permanently blacklisted.
- **n_splits reduction (8→6 for BTC)**: 1/1 DISCARD (iter 33, Brier +0.19% regression despite more HPO trials). Blacklisted for BTC.
- **max_depth > 6**: 1/1 DISCARD for SOL (iter 41). Blacklisted.
- **train_bars > 14000 for XRP/ETH 5m**: 1/1 DISCARD (iter 52 XRP, train_bars 14K→18K). Blacklisted.

---

## HPO Range Recommendations

- **learning_rate (BTC assets)**: keep lower bound at 0.005. Optimal is 0.009 (BTC/1h iter 99) and 0.021 (BTC/15m iter 95). Never raise lower bound — this is the most robust blacklist finding.
- **learning_rate (tick-dominant)**: current [0.005, 0.1] is fine. Optimal clusters in [0.010, 0.065] — no narrowing needed.
- **min_child_samples (BTC/1h)**: narrow to [400, 800]. Evidence: iter 103 found optimal=468 even in a failed run. Current range [100, 1000] wastes half the search space.
- **num_leaves (BTC/1h)**: consider narrowing to [16, 64]. Evidence: iter 99 optimal=51, iter 103 optimal=63. Upper range 64-128 consistently unused for BTC/1h.
- **num_leaves (ETH/SOL/XRP tick-dominant)**: keep at [16, 128]. These assets show wide optimal range (19-115) and do not benefit from narrowing.
- **max_depth**: keep at [2, 6] for all. BTC settles at 4-5, tick-dominant at 5-6 — current range is appropriately wide.
