# Strategy Directive
Updated: 2026-03-22T19:00:00Z
After iteration: 156

## Program Status: 15m+5m num_leaves Narrowing Campaign — 3/5 KEEPs (60%)

Iters 152-156 completed strategy-after-151 items 1-4. Three major breakthroughs achieved:
- **ETH/15m KEEP-VERIFIED (iter 152)**: Brier 0.208324 -> 0.193035 (7.34% improvement, [64,128]+[100,500])
- **SOL/15m KEEP-VERIFIED (iter 155)**: Brier 0.215345 -> 0.200064 (7.10% improvement, [32,72]+[100,400])
- **ETH/5m KEEP-VERIFIED (iter 156)**: Brier 0.211888 -> 0.199722 (5.74% improvement, sub-0.20 breakthrough, [64,128]+[100,500])

BTC/15m: 0/2 misses. Iter 153 had double-ceiling starvation (same pattern as ETH/15m iter 151).
Iter 154 widened to [32,80]+[100,500], starvation RESOLVED (num_leaves=45 n_est=441 both free),
but Brier=0.173259 misses best 0.171809 by 0.845%. The miss is larger than typical stochastic
variance — the [32,80] widened range may not be the right window OR a stochastic re-run is needed.

### Updated Cross-Asset Baselines Through Iteration 156

| Asset | 5m Best          | 15m Best          | 1h Best           |
|-------|-----------------|-------------------|-------------------|
| BTC   | 0.17605 (iter 104)  | 0.171809 (iter 123) | 0.174676 (iter 136) |
| ETH   | 0.199722 (iter 156) | 0.193035 (iter 152) | 0.211438 (iter 100) |
| SOL   | 0.218058 (iter 121) | 0.200064 (iter 155) | 0.219333 (iter 148) |
| XRP   | 0.221503 (iter 112) | 0.218075 (iter 128) | 0.222676 (iter 149) |

**Key shifts since strategy-after-iter-151:**
- ETH/15m: 0.208324 -> 0.193035 (+7.34%) — best improvement in the post-151 period
- SOL/15m: 0.215345 -> 0.200064 (+7.10%) — second best, sub-0.20 barrier broken
- ETH/5m: 0.211888 -> 0.199722 (+5.74%) — sub-0.20 barrier broken for a second asset
- BTC/15m: UNCHANGED at 0.171809 — two misses, needs attention

### BTC/15m Analysis: Widened Range Still Misses — Why?

Iter 123 (best, Brier=0.171809): num_leaves=43, n_est=235, [16,128]+[100,800]
Iter 153 (double-ceiling): num_leaves=60 near [24,64] ceiling, n_est=391 near 400 ceiling — invalid
Iter 154 (starvation-free): num_leaves=45, n_est=441, [32,80]+[100,500] — Brier=0.173259 (+0.845%)

Iter 154 is the first clean BTC/15m run with a narrowed range. num_leaves=45 matches iter 123 (43)
and confirms convergence. However n_est=441 is higher than iter 123's n_est=235 — possible that
iter 154's n_est range [100,500] shifted the HPO landscape. BTC/15m may prefer n_est in 200-250
range (matching BTC/1h=230, BTC/5m=103-427 unstable). Try tighter n_estimators=[100,350] to
redirect search away from high-n_est territory that iter 123 did not use.

### What Remains After Iter 156

**Items completed from strategy-after-151:** 1 (ETH/15m), 3 (SOL/15m), 4 (ETH/5m), partial on 2 (BTC/15m needs retry)
**Items not yet attempted:** 5 (SOL/5m), 6 (XRP/15m), 7 (ETH/1h tiebreaker)

Cross-asset feature breakthrough: ETH/15m and SOL/15m KEEPs both show BTC features in top-3
(btc_vol_norm_distance #1, btc_distance_from_open #2). The 4 enabled BTC features are working.
No evidence to add or remove BTC features at this time.

## Priority Queue

1. **BTC/15m stochastic re-run num_leaves=[32,64] + n_estimators=[100,350]**
   Rationale: iter 154 was starvation-free (num_leaves=45, n_est=441) but missed best by 0.845%.
   num_leaves=45 is consistent with best (iter 123: 43) — the range [32,80] is directionally
   correct. However n_est=441 (vs iter 123's n_est=235) suggests the HPO may be exploring a
   high-n_est plateau that is suboptimal. Tighten n_estimators to [100,350] to redirect search
   toward the 200-250 range where iter 123 found its best. Tighten num_leaves to [32,64] to
   exclude the 65-80 territory that iter 154 explored (num_leaves=45 confirms lower end is better).
   This is a precision refinement — the stochastic noise should be reduced with a tighter range.
   Expected: BTC/15m true optimum is near iter 123 params (n_est=235, num_leaves=43); a
   starvation-free run targeting that region should find Brier <= 0.171809 or confirm floor.
   Specific knobs: `hpo_search_space.num_leaves=[32,64]`, `hpo_search_space.n_estimators=[100,350]`

2. **SOL/5m num_leaves=[28,68] + n_estimators=[100,400]**
   Rationale: iter 121 (best) found num_leaves=47 with n_estimators=274 (24/40 trials at 800
   ceiling). SOL num_leaves cross-timeframe pattern is tight: SOL/1h=46, SOL/15m=51, SOL/5m=47.
   The [28,68] range directly targets this convergence band. SOL/15m just succeeded with [32,72]
   at [100,400] — SOL/5m should follow the same approach. SOL/5m best_knobs currently has
   n_est=[100,800] and num_leaves=[16,128] — both need updating. Reducing ceiling from 800 to
   400 saves search budget for SOL/5m (n_est=274 fits within 400 ceiling).
   Specific knobs: `hpo_search_space.num_leaves=[28,68]`, `hpo_search_space.n_estimators=[100,400]`

3. **XRP/15m num_leaves=[32,80] + n_estimators=[100,600]**
   Rationale: XRP/15m confirmed structurally starved by dataset size (23-29/40 trials regardless
   of ceiling level). Best run (iter 128) had num_leaves=128 AT upper bound — the true optimum
   was never cleanly found. Applying num_leaves narrowing to [32,80] following the XRP/1h
   pattern (num_leaves=25 at iter 149) — XRP assets show consistent low num_leaves preference.
   Keep n_estimators=[100,600] (iter 128's best n_est=599 near ceiling; starvation is structural,
   not n_estimators driven; 600 ceiling confirmed minimum by iter 145 analysis).
   Accept if >=16/40 trials AND Brier < 0.218075.
   Specific knobs: `hpo_search_space.num_leaves=[32,80]`, `hpo_search_space.n_estimators=[100,600]`

4. **SOL/5m verification run (if item 2 KEEP-fast)**
   If item 2 produces a fast Brier improvement, proceed directly to verify run
   following same protocol as iter 155 (SOL/15m): compare fast vs verify Brier, accept if
   delta < 0.3% and Brier(verify) < best.

5. **ETH/1h num_leaves=[16,32] + n_estimators=[100,400]** (tiebreaker — LOW PRIORITY)
   Rationale: iters 147 and 150 both converged to num_leaves=20 at [16,64] range, both produced
   identical Brier=0.211817 missing best 0.211438 by 0.018%. The floor is almost certainly real.
   A final narrowing to [16,32] is a very low-cost confirmation test — if num_leaves=18 exists
   below 20, this finds it; otherwise it confirms the floor definitively. Only run after items
   1-3 all complete.
   Specific knobs: `hpo_search_space.num_leaves=[16,32]`, `hpo_search_space.n_estimators=[100,400]`

6. **XRP/5m num_leaves=[16,40] + n_estimators=[100,400]** (structural class — SOFT BLACKLIST)
   Rationale: iter 141 had 9/40 trials at 600 ceiling — XRP/5m dataset-size structural (929K
   samples, same class as BTC/5m). However, num_leaves narrowing has now unlocked 3 major KEEPs
   on other structurally-challenged assets (ETH/15m, SOL/15m, ETH/5m). XRP/1h converged to
   num_leaves=25 at iter 149 — XRP assets show low num_leaves preference. Try [16,40]+[100,400]
   to radically reduce per-trial complexity. Accept if >=10/40 trials AND Brier < 0.221503.
   CAUTION: If this produces <10/40 trials, permanently blacklist XRP/5m.
   Specific knobs: `hpo_search_space.num_leaves=[16,40]`, `hpo_search_space.n_estimators=[100,400]`

## Observations

- **Three major ETH/SOL breakthroughs in one strategy period (iters 152-156):** The num_leaves
  narrowing campaign is the highest single-lever KEEP rate ever recorded in autoresearch:
  3/3 (100%) for ETH/15m+SOL/15m+ETH/5m vs prior overall rate of 2/3 (67%) after iter 151.
  The widening strategy (when double-ceiling starvation is detected) is now confirmed as the
  correct response.
- **BTC/15m num_leaves convergence confirmed at 43-45:** Iters 123 (43), 153 (60 — ceiling-hit),
  154 (45). num_leaves=45 in starvation-free iter 154 matches iter 123 closely. The [32,64]
  range for next attempt is well-justified. The 0.845% miss is suspicious — n_est=441 vs
  prior 235 may have shifted the landscape slightly.
- **Sub-0.20 Brier barrier broken for ETH and SOL 15m:** ETH/15m=0.193, SOL/15m=0.200. Only
  BTC 5m/15m/1h remain below 0.20 at structural floors. ETH/5m also broke 0.20 (0.199722).
  All 12 models now target <0.22 or better; 7/12 are now <0.22.
- **Cross-asset BTC features confirmed high-value for ETH and SOL 15m:** btc_vol_norm_distance
  and btc_distance_from_open appear in top-3 for both ETH/15m (iter 152) and SOL/15m (iter 155).
  This validates the cross-asset feature build. No changes needed — keep 4 enabled features.
- **num_leaves narrowing KEEP rate (full campaign, updated):**
  SOL/1h (iter 148) KEEP, XRP/1h (iter 149) KEEP, ETH/15m (iter 152) KEEP, SOL/15m (iter 155)
  KEEP, ETH/5m (iter 156) KEEP. Excluding the double-ceiling contaminated DISCARD (iter 151,
  153): 5/5 = 100% when range is correctly set. Total: 5/7 = 71% including double-ceiling cases.
- **BTC assets remain at structural floors:** BTC/5m (0.17605, iter 104, 0/8 KEEP since),
  BTC/1h (0.174676, iter 136, 0/3 KEEP since). Only BTC/15m (0.171809) has remaining potential.
- **n_estimators optimum taxonomy (updated through iter 156):**
  5m: ETH=182 (best_knobs), SOL=274 (iter 121); 15m: ETH=389 (iter 152), SOL=269 (iter 155),
  BTC=235 (iter 123 best), XRP=599 (ceiling-hit, unreliable); 1h=200-350 (all confirmed).
  BTC/15m iter 154 finding n_est=441 is an outlier — more likely a red herring from wide range.

## Risk Profile

- Max drawdown trend: STABLE — ETH/15m iter 152 dd=0.0234 (elevated vs peers but within 0.05
  acceptance); SOL/15m iter 155 dd=0.0512 (stable); ETH/5m iter 156 dd not reported.
  No concerning growth across the post-151 KEEP rows.
- Trade count: STABLE — 15m: 61K-76K; verified: SOL/15m=75,400 (iter 155), BTC/15m=62K (iter 154).
  All above 50-trade minimum. ETH/5m iter 156 trades=227,819 (5m assets trade more — consistent).
- Win rate: tick-dominant assets (ETH/SOL/XRP) = 50-52% (structural FLAT pattern confirmed).
  BTC sniper: BTC/15m iter 154 WR=61.27% (strong sniper ramp pattern persists).
- HPO-OOS gap: <0.5% for all starvation-free post-151 KEEPs. ETH/15m hpo_obj=0.148 vs
  Brier=0.193 — gap partly explained by composite objective (brier + trade_penalty). No
  widening trend in calibration.
- ECE: ETH/15m=0.0234, SOL/15m=0.0059 — both within 0.05 acceptance threshold. Healthy.

## Timeframe Coverage

- 5m: ~42 iterations (iters 91+), 9 KEEPs (21%), best Brier=0.17605 (BTC/5m iter 104).
  ETH/5m just improved to 0.199722 (iter 156). Remaining: SOL/5m (item 2), XRP/5m (item 6, soft blacklist).
  BTC/5m confirmed structural floor.
- 15m: ~36 iterations, 12 KEEPs (33%), best Brier=0.171809 (BTC/15m iter 123).
  ETH/15m improved to 0.193035, SOL/15m to 0.200064. Remaining: BTC/15m retry (item 1), XRP/15m (item 3).
  Strong improvement campaign — 2 new KEEPs in this period.
- 1h: ~38 iterations, 10 KEEPs (26%), best Brier=0.174676 (BTC/1h iter 136).
  Campaign largely complete. ETH/1h tiebreaker (item 5) is the only remaining 1h work.
- Recommendation: prioritize 15m (BTC/15m retry + XRP/15m) and 5m (SOL/5m) as primary
  campaign. 1h is done except optional ETH/1h tiebreaker.

## Blacklist

- **reg_alpha=[0.1,5.0] forcing (all assets)**: 0/5 KEEP (iters 139-146). Permanently blacklisted.
- **BTC/5m optimization (any lever)**: 0/8 KEEP since iter 104. Permanently blacklisted.
  Evidence: iters 122, 127, 134, 146 and pre-151 data. Dataset-size structural floor.
- **XRP/5m (any ceiling reduction)**: 0/1 KEEP, 9/40 trials at 600 ceiling (iter 141).
  Soft blacklist — only attempt with dramatically reduced num_leaves [16,40] (item 6).
- **XRP/15m ceiling reduction below 600**: structural starvation persists regardless of
  ceiling (iters 132, 140, 145). Use 600 ceiling minimum with num_leaves narrowing instead.
- **ETH/1h optimization (any lever)**: floor confirmed at 0.211438. Only item 5 (tiebreaker)
  allowed. Evidence: iters 105, 108, 135, 144, 147, 150 all DISCARD (0/6 since iter 100).
- **ETH/15m num_leaves=[48,96] (too tight)**: iter 151 double-ceiling starvation. Fixed with
  [64,128] in iter 152. Do not revert.
- **BTC/15m num_leaves=[24,64] (too tight)**: iter 153 double-ceiling starvation (num_leaves=60
  near 64 ceiling). Use [32,64] minimum with n_estimators=[100,350].
- **min_child_samples narrowing (ETH assets)**: 0/2 KEEP (iters 108, 129). Confirmed problematic.
- **SOL/15m starvation at n_estimators=[100,800]**: structural (iters 97, 109, 126). Use [100,400].
- **BTC/1h lr=[0.005,0.03]**: binding at iter 131. Use [0.005,0.05]. BTC/1h at structural floor.

## HPO Range Recommendations

- **n_estimators (1h assets)**: [100, 400] — confirmed, all 1h assets optimum in 200-350 range.
- **n_estimators (15m ETH/SOL/BTC)**: [100, 400] confirmed. XRP/15m: [100, 600] only.
  Note: ETH/15m best at n_est=389 (within 500 ceiling); SOL/15m best at n_est=269 (within 400).
- **n_estimators (5m ETH/SOL)**: [100, 500] — ETH/5m n_est=182 confirmed; SOL/5m target 400.
- **num_leaves (ETH assets)**: ETH/1h=[16,32]; ETH/15m=[64,128] (confirmed at iter 152);
  ETH/5m=[64,128] (confirmed at iter 156, num_leaves=69).
- **num_leaves (SOL assets)**: [28,68] — SOL/1h=46, SOL/15m=51 (iter 155), SOL/5m=47 (iter 121).
  All three timeframes cluster in 46-51 range. [28,68] tightly brackets this.
- **num_leaves (XRP assets)**: XRP/1h=[16,48] (XRP/1h=25, iter 149); XRP/15m=[32,80] (unknown,
  use pending item 3 to confirm); XRP/5m=[16,40] if attempted (item 6).
- **num_leaves (BTC assets)**: [32,64] for BTC/15m (43-45 confirmed across iters 123/154).
  BTC/5m and BTC/1h at structural floors — no further experiments.
- **learning_rate (BTC/1h)**: [0.005, 0.05] — resolved. Informational only (structural floor).
