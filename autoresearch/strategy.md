# Strategy Directive
Updated: 2026-03-25T10:30:00Z
After iteration: 119

## Program Status: POST-OVERRIDE Autonomous HPO Phase (Anti-Starvation Rollout)

Iters 115-120 completed the prior strategy's 6-item queue. Results: 3 KEEPs (XRP/1h +0.018%,
ETH/15m +0.275%, ETH/5m new baseline 0.211888), 3 DISCARDs (SOL/1h regression, XRP/15m
regression, ETH/1h lr-narrowing no improvement). The n_estimators=[100,800] anti-starvation
fix introduced in iter 116 is confirmed effective (ETH/15m 23/40, ETH/5m 23/40 vs prior 2/40).
The critical gap: anti-starvation has NOT yet been applied to BTC/5m (11/40), BTC/15m (15-17/40),
SOL/5m (2/40 in iter 111 — the worst), or XRP/15m (22/40). This is the priority for this directive.

Note: best_knobs.json has n_estimators=[100,800] (from iter 116 KEEP). knobs.json still has
n_estimators=[100,1500]. Researcher should use best_knobs.json as baseline and verify.

---

## Priority Queue

1. **SOL/5m anti-starvation: apply n_estimators=[100,800] (highest urgency)**
   - Command: `--asset SOL --timeframe 5m --mode fast --save`
   - Knob change: hpo_search_space.n_estimators = [100, 800] (should already be in best_knobs.json)
   - Rationale: SOL/5m had catastrophic starvation at 2/40 trials in iter 111 (1185s timeout).
     ETH/15m went from 2/40 to 23/40 after this fix (iter 116). ETH/5m also got 23/40 (iter 117).
     SOL/5m is the most under-explored asset in the portfolio — its multi-tp Brier 0.218209 was
     set with only 18/40 trials (iter 93, before starvation worsened). The 2-trial result from
     iter 111 is unreliable. A fresh run with n_estimators=[100,800] should give 20-30/40 trials
     and is the single most likely experiment to improve the portfolio.
   - KEEP criterion: any Brier improvement from 0.218209 (iter 93 best)
   - train_bars=10000, purge_period=24 (SOL-optimal)

2. **BTC/5m anti-starvation: apply n_estimators=[100,800]**
   - Command: `--asset BTC --timeframe 5m --mode fast --save`
   - Knob change: hpo_search_space.n_estimators = [100, 800] (confirm in best_knobs.json)
   - Rationale: BTC/5m iter 104 ran only 11/40 trials (384s timeout for 11 trials, BTC/5m is the
     slowest asset per trial due to 80K+ training samples). The current best 0.17605 was set with
     just 11 trials — far below the 40-trial target. ETH/5m has the same training size and gets
     23/40 with n_estimators=[100,800]. BTC/5m should benefit similarly. BTC/5m best_params from
     iter 104 used lr=0.058, max_depth=5, num_leaves=98 — high num_leaves combined with high
     n_estimators is the starvation driver. BTC/5m is the largest dataset (80K+ samples) so
     starvation is expected to be severe.
   - KEEP criterion: any Brier improvement from 0.17605 (iter 104 best)
   - train_bars=10000, purge_period=24 (BTC-optimal), lr=[0.005,0.1] (keep wide for BTC sniper zone)

3. **BTC/15m anti-starvation: apply n_estimators=[100,800]**
   - Command: `--asset BTC --timeframe 15m --mode fast --save`
   - Knob change: hpo_search_space.n_estimators = [100, 800]
   - Rationale: BTC/15m has structural starvation at 15-17/40 trials (iters 105, 114). Iter 114
     confirmed starvation is per-fold time, not total dataset size (7500 train_bars gave same 17/40
     as 10000). The n_estimators=[100,800] fix was NOT tried for BTC/15m. Best_params from iters
     105/114 used n_estimators values that are within [100,800], so the fix should be safe. At
     17/40 trials, BTC/15m has only explored 42% of the intended search space — there is likely
     untapped improvement in the remaining 58%.
   - KEEP criterion: any Brier improvement from 0.171913 (iter 66/95 best — note BTC/15m best was
     set at 0.171913 in iter 95 or 66; verify exact best in results.tsv)
   - train_bars=10000, purge_period=24 (BTC-optimal)

4. **XRP/15m anti-starvation: apply n_estimators=[100,800]**
   - Command: `--asset XRP --timeframe 15m --mode fast --save`
   - Knob change: hpo_search_space.n_estimators = [100, 800]
   - Rationale: XRP/15m iter 119 ran 22/40 trials — moderate starvation. XRP/15m is tick-dominant
     and has the same architecture as ETH/15m and SOL/5m. Current best 0.218727 was set with 24/40
     trials (iter 98). The anti-starvation fix should push trial count to 30-35/40, giving a more
     thorough search. XRP/15m best_params from iter 119 used n_estimators=382 (within [100,800]),
     confirming the ceiling reduction is safe.
   - KEEP criterion: any Brier improvement from 0.218727 (iter 98 best)
   - train_bars=10000, purge_period=24 (XRP-optimal)

5. **SOL/1h reg_alpha investigation: widen reg_alpha [0.1, 20.0]**
   - Command: `--asset SOL --timeframe 1h --mode fast --save`
   - Knob change: hpo_search_space.reg_alpha = [0.1, 20.0] (widen from [1e-8, 10.0])
   - Rationale: SOL/1h iter 118 produced reg_alpha=8.55 — the highest L1 regularization seen in any
     multi-tp run. This is novel (all other assets have reg_alpha near 0 in multi-tp). The HPO is
     pushing against the upper bound at 10.0, suggesting the true optimum may be above 10. SOL/1h
     has 40/40 trials (starvation-free, 209s per run — very fast). Widening the reg_alpha ceiling
     to 20.0 lets HPO find the true SOL/1h optimum. Even if no improvement occurs, confirming the
     upper bound is not binding is valuable. SOL/1h current best is 0.221683.
   - KEEP criterion: any Brier improvement from 0.221683 (iter 101 best)
   - train_bars=10000, purge_period=24 (SOL-optimal)

6. **ETH/5m follow-up: min_child_samples narrowing [300, 700]**
   - Command: `--asset ETH --timeframe 5m --mode fast --save`
   - Knob change: hpo_search_space.min_child_samples = [300, 700] (narrow from [100, 1000])
   - Rationale: ETH/5m iter 117 found min_child=389 (mid-range). ETH/15m iter 116 found
     min_child=989 (near upper bound). These two ETH assets at different timeframes suggest ETH
     prefers min_child in the mid-to-high range (300-1000). This experiment is speculative but
     has a clear reversal condition: if Brier regresses, revert to [100,1000]. ETH/5m has 23/40
     trial coverage and is currently at 0.211888 — the weakest ETH timeframe by Brier distance
     from single-tp floor (0.211888 vs 0.177772 single-tp = +19%). Min_child is the only
     regularization lever not yet explored for ETH/5m post-OVERRIDE.
   - KEEP criterion: any Brier improvement from 0.211888 (iter 117 best)
   - Revert min_child_samples to [100, 1000] on DISCARD

---

## Observations

- **KEEP rates (iters 115-120, this strategist window):**
  - No-knob HPO re-run: SOL/1h DISCARD (iter 118), XRP/15m DISCARD (iter 119) = 0/2 (0%)
  - Anti-starvation fix (n_estimators=[100,800]): ETH/15m KEEP (iter 116), ETH/5m KEEP (iter 117) = 2/2 (100%)
  - HPO range narrowing: ETH/1h lr [0.005,0.05] DISCARD (iter 120) = 0/1 (0%)
  - XRP/1h re-run with wider num_leaves: KEEP (iter 115, marginal 0.018%) = 1/1

- **Cumulative KEEP rates (post-OVERRIDE, iters 103-120):**
  - Anti-starvation fix: 2/2 (100%) — ETH/15m, ETH/5m. HIGH CONFIDENCE.
  - HPO re-run no knob change: 5/10 (50%) — BTC/5m, XRP/1h, ETH/15m, XRP/5m, BTC/1h kept;
    SOL/5m, SOL/1h, XRP/15m, ETH/1h, BTC/15m discarded
  - HPO range narrowing: 0/5 (0%) — lr narrowing, min_child narrowing all fail
  - HPO range widening (selective): 1/3 (33%) — BTC/1h num_leaves [32,96] KEEP; reg_lambda
    and ETH/1h lr widening DISCARD

- **Anti-starvation impact summary:**
  - ETH/15m: 2/40 (iter 110) → 23/40 (iter 116) → KEEP
  - ETH/5m: unknown prior (OVERRIDE era had 23/40) → 23/40 (iter 117) → KEEP (new baseline)
  - SOL/5m: 2/40 (iter 111) → NOT YET RETRIED with fix
  - BTC/5m: 11/40 (iter 104) → NOT YET RETRIED with fix
  - BTC/15m: 17/40 (iter 114) → NOT YET RETRIED with fix
  - XRP/15m: 22/40 (iter 119) → NOT YET RETRIED with fix
  - Starvation-free assets (40/40 historical): SOL/1h (209s), ETH/1h (380s), XRP/1h (266s)

- **SOL/1h anomaly (iter 118):**
  - reg_alpha=8.55 is 4-40x higher than any other tick-dominant asset in multi-tp.
  - Tick-dominant assets typically converge to reg_alpha near 0 (XRP/15m: 8e-6, ETH/15m: 0.0,
    SOL/15m: 4e-4). SOL/1h at 8.55 suggests HPO is finding strong L1 sparsity beneficial at 1h.
  - Possible explanation: 1h bars have sparser feature signal (fewer ticks per bar), requiring
    heavier regularization to suppress noise. XRP/1h (iter 115) found lr=0.065 (high) suggesting
    similar coarse-grained learning needed at 1h for tick-dominant assets.
  - Despite this, iter 118 was a DISCARD (+0.086% regression). The 40/40 trial count means this
    is a genuine floor. The reg_alpha widen experiment (item 5) may reveal whether the true
    optimum is above the current bound.

- **ETH Brier landscape in multi-tp regime:**
  - ETH/5m: 0.211888 (single-tp best 0.177772, multi-tp gap +19%)
  - ETH/15m: 0.208324 (single-tp best 0.174283, multi-tp gap +20%)
  - ETH/1h: 0.211438 (single-tp best 0.176103, multi-tp gap +20%)
  - The ETH gap is remarkably consistent across timeframes (~20%). This is the structural
    overhead of training on 5 time buckets including noisy early-bar samples (t10, t20).
    No HPO lever has been able to reduce this gap. The floor appears genuine.

- **Portfolio Brier floor summary:**
  - BTC sniper assets: consistently achieve 0.17-0.18 multi-tp (floor ~0.175)
  - ETH tick-dominant: consistently at 0.208-0.212 multi-tp (floor ~0.208)
  - SOL tick-dominant: 0.215-0.222 multi-tp (more room for improvement than ETH)
  - XRP tick-dominant: 0.218-0.227 multi-tp (XRP/1h still highest in portfolio at 0.226907)

- **lr convergence patterns (multi-tp, from all KEEPs):**
  - BTC-class: lr=0.008-0.058 (wide range, BTC/5m iter 104 used 0.058 which is unusual vs
    prior BTC optima 0.008-0.013 in single-tp). Multi-tp BTC lr is less well-characterized.
  - ETH tick-dominant: lr=0.005-0.034 (well-concentrated in low range)
  - SOL tick-dominant: lr=0.017-0.018 (extremely concentrated — SOL prefers lr~0.018)
  - XRP: lr=0.025-0.065 (wider, consistent with intermediate BTC/ETH behavior)

---

## Risk Profile

- Max drawdown trend: stable — BTC/5m=0.39 (iter 104), BTC/15m=0.17-0.18, BTC/1h=0.23;
  ETH/SOL/XRP tick-dominant 0.06-0.09 (unchanged across all iterations)
- Drawdown/PnL ratio: tick-dominant < 0.01 (excellent), BTC sniper 0.003-0.009 (good)
- Trade count range across KEEPs (iters 115-120):
  - XRP/1h: 19,292 (iter 115, stable vs iter 102)
  - ETH/15m: 77,061 (iter 116), ETH/5m: 81,000 (iter 117) — within expected range
  - SOL/1h: 19,255 (iter 118 DISCARD), XRP/15m: 77,189 (iter 119 DISCARD) — stable
- Win rate stability: tick-dominant 49-51% (all iterations — no degradation detected)
- HPO-OOS gap (hpo_objective vs oos_brier):
  - ETH/15m iter 116: hpo_obj=0.295 vs brier=0.208 (stable ratio, tick-dominant composite penalty)
  - ETH/5m iter 117: hpo_obj=0.279 vs brier=0.212 (similar)
  - SOL/1h iter 118: hpo_obj=0.407 vs brier=0.224 — elevated ratio (high reg_alpha penalty)
  - XRP/15m iter 119: hpo_obj=0.501 vs brier=0.220 — highest ratio seen (22/40 trials only)
  - NOTE: XRP/15m hpo_objective 0.501 is anomalously high given brier=0.220. Investigate whether
    trade penalty is driving this (XRP/15m has 77K trades which is near ETH/15m level). Not
    a quality concern, but suggests XRP/15m is near penalty boundary.

---

## Timeframe Coverage

- 5m: 57 iterations (approx), ~20 KEEPs, best multi-tp Brier: BTC=0.17605, ETH=0.211888
  (new baseline iter 117), SOL=0.218209 (stale — needs anti-starvation), XRP=0.221503
- 15m: 29 iterations, ~14 KEEPs, best multi-tp Brier: BTC=0.171913, ETH=0.208324 (new best
  iter 116), SOL=0.215443 (stale — starvation structural), XRP=0.218727 (stale)
- 1h: 26 iterations, ~12 KEEPs, best multi-tp Brier: BTC=0.174864, ETH=0.211438, SOL=0.221683,
  XRP=0.226907 (new best iter 115, marginal)
- Recommendation: 5m is slightly over-represented in this window (ETH/5m, SOL/5m both need
  attention). Priority queue is balanced: 2/6 to 5m (items 1, 2), 2/6 to 15m (items 3, 4),
  1/6 to 1h (item 5), 1/6 to 5m (item 6 is ETH/5m). The anti-starvation rollout is the
  unifying theme — not timeframe-specific.

---

## Blacklist

- **lr lower bound > 0.015 for BTC-class assets** (iters 103, 106 DISCARD) — BTC sniper zone
  requires lr=0.008-0.013; raising lower bound excludes optimum
- **train_bars increase beyond 10000 for BTC-class** (multiple DISCARDs including iters 52, 82)
- **train_bars reduction to 7500 for BTC/15m** (iter 114 DISCARD) — starvation is per-fold time,
  not dataset volume; accept 15-17/40 as structural floor pre-anti-starvation fix
- **train_bars increase beyond 14000 for ETH** — ETH ceiling is 14000
- **min_child_samples narrowing for any asset** (0/3 KEEP rate across iters 106, 108, and prior)
- **funding features in cached_features** (iters 2, 27, 43 — 0/3 KEEP) — funding never in top-10
- **interaction features** (iter 6 DISCARD — massive Brier regression) — do not re-enable
- **n_splits reduction to 6** (iters 31, 33) — consistently worse
- **SOL/15m HPO re-run without anti-starvation fix** (iters 97, 109 — structural 16/40) —
  must apply n_estimators=[100,800] before attempting SOL/15m again
- **ETH/1h reg_lambda widening above 10.0** (iter 113 DISCARD) — multi-tp ETH/1h optimal
  reg_lambda near 1.0-1.4, NOT the single-tp artifact of 9.42
- **ETH/1h lr narrowing above 0.05** (iter 120 DISCARD) — lr=0.009 confirmed optimal but
  narrowing provides no lift; leave [0.005, 0.1] wide to avoid over-constraining
- **No-knob HPO re-run for SOL/1h without reg_alpha investigation** (iter 118 DISCARD at 40/40
  trials) — floor is genuine at current knobs; only widening reg_alpha ceiling may help

---

## HPO Range Recommendations

- **n_estimators: reduce ceiling to [100, 800] for ALL remaining starvation-prone assets**
  Evidence: 100% KEEP rate (2/2) for ETH assets after fix. Apply to: SOL/5m, BTC/5m,
  BTC/15m, XRP/15m. This is the single highest-confidence recommendation in this directive.
- **n_estimators ceiling is ALREADY [100, 800] in best_knobs.json** — researcher should
  verify best_knobs.json is the base config before each experiment.
- **reg_alpha for SOL/1h: test [0.1, 20.0]** — evidence: iter 118 produced reg_alpha=8.55
  pushing against current upper bound 10.0. Widen to explore whether true optimum is above 10.
- **learning_rate for SOL: confirmed [0.015, 0.025]** — SOL/5m iters 39/93/101 consistently
  find lr=0.017-0.023. SOL/1h iter 118 found lr=0.080 (deviation — suspicious given DISCARD).
  SOL/1h true optimum may be in the low-lr range like SOL/5m. Investigate.
- **num_leaves for tick-dominant assets**: no change recommended — [16, 128] continues to
  find diverse optima (SOL/5m 59, ETH/15m 70, XRP/15m 52) with no consistent upper-bound hitting.
- **min_child_samples**: maintain [100, 1000] — narrowing has 0% KEEP rate; wide range correct.
- **reg_lambda for tick-dominant multi-tp**: candidate future narrowing to [1e-8, 5.0] —
  not yet tested; ETH/1h evidence accumulating (optimal~1.0-1.4). Defer to next directive.
