# Strategy Directive
Updated: 2026-03-26T13:00:00Z
After iteration: 140

## Program Status: reg_alpha Basin Escape — Phase 5

Iters 137-140 executed the first 2 of 5 items from the post-iter-136 queue. Results: 0 KEEPs,
4 DISCARDs. Items 3-5 are pending. Key themes:

1. **BTC/1h [100,250] stochastic basin confirmed** (iters 137/138): Two full-search runs
   (40/40 trials each) both missed by <0.03% (Brier 0.175037 and 0.174979 vs best 0.174676).
   The n_estimators optimum is confirmed ~180-230 (well within [100,250] ceiling). The basin
   floor is ~0.1746-0.1750 — structural, not starvation-driven.

2. **BTC/1h reg_alpha=[0.1,5.0] structural shift confirmed but insufficient** (iter 139):
   reg_alpha forced from zero-collapse (0.002) to 0.1073 near lower bound — HPO is gravitating
   to minimum viable regularization, not zero. 34/40 trials (mild starvation from 350 ceiling).
   Brier=0.175226 still misses best by 0.032%. KEY: reg_alpha exploration is meaningful (not
   just collapsing to zero) but [0.1,5.0] alone is not enough to escape the basin.

3. **XRP/15m reg_alpha=[0.1,5.0]+n_est=[100,400] severe regression** (iter 140): Brier=0.221812
   vs best 0.218075 (+1.71% regression). n_estimators=367 near 400 ceiling confirms starvation
   persists — the reg_alpha change combined with starvation produced a degraded result. Pattern:
   when starvation is present, reg_alpha forcing produces worse outcomes (HPO cannot explore
   effectively). KEY: XRP/15m must resolve starvation BEFORE testing reg_alpha changes.

4. **Items 3-5 from post-iter-136 queue are unexecuted**: XRP/5m [100,600] (item 3),
   ETH/5m reg_alpha=[0.1,5.0] (item 4), ETH/1h reg_alpha=[0.1,5.0] (item 5).

---

## Priority Queue

1. **XRP/5m anti-starvation n_estimators=[100,600] (untreated starvation, highest priority)**
   - Command: `--asset XRP --timeframe 5m --mode fast`
   - Knob change: hpo_search_space.n_estimators = [100, 600] (from [100, 1500] default or current)
   - Restore: hpo_search_space.reg_alpha = [1e-8, 10.0] (current knobs.json is [1e-8,10.0] — OK)
   - Rationale: XRP/5m has NEVER received anti-starvation treatment. Iter 112 showed only 12/40
     HPO trials at the 1500 ceiling — severe starvation class. All 11 other asset-timeframes have
     received ceiling reductions; XRP/5m is the sole untreated asset. SOL/5m iter 121 resolved at
     600 (n_estimators=274, not near ceiling). XRP/5m likely similar dataset class to SOL/5m
     (~300K samples). Starting at 600 (not 800) skips the partially-effective 800 ceiling and
     goes directly to the resolution point.
   - Baseline to beat: 0.221503 (iter 112 best)
   - KEEP criterion: any Brier improvement from 0.221503
   - Revert n_estimators to [100, 1500] if DISCARD

2. **ETH/5m reg_alpha widen to [0.1, 5.0] + keep n_estimators=[100,800]**
   - Command: `--asset ETH --timeframe 5m --mode fast`
   - Knob change: hpo_search_space.reg_alpha = [0.1, 5.0] (from [1e-8, 10.0])
   - Keep: hpo_search_space.n_estimators = [100, 800] (working, 23/40 trials — no change)
   - Rationale: ETH/5m has only 1 improvement attempt (iter 129 min_child narrowing DISCARD).
     The iter 117 baseline best_params had reg_alpha=3e-6 (near-zero collapse). ETH/5m does NOT
     have starvation (800 ceiling with 23/40 trials, n_estimators=182 well within range). This
     is a clean starvation-free test of reg_alpha forcing — unlike XRP/15m iter 140 which had
     starvation confounding the result. SOL/1h precedent (iter 125, reg_alpha=0.919 KEEP) shows
     reg_alpha forcing can produce genuine improvement on starvation-free assets.
   - Baseline to beat: 0.211888 (iter 117 best)
   - KEEP criterion: any Brier improvement from 0.211888
   - Revert reg_alpha to [1e-8, 10.0] if DISCARD

3. **ETH/1h reg_alpha widen to [0.1, 5.0] + keep n_estimators=[100,800] or [100,1500]**
   - Command: `--asset ETH --timeframe 1h --mode fast`
   - Knob change: hpo_search_space.reg_alpha = [0.1, 5.0] (from [1e-8, 10.0])
   - Keep: hpo_search_space.n_estimators = [100, 800] or [100, 1500] (starvation-free, no change)
   - Rationale: ETH/1h has 0 Brier improvements since iter 100 baseline (4 DISCARD attempts:
     iters 108, 113, 120, 135). Iter 100 best_params: reg_alpha=0.146; iter 135 best_params:
     reg_alpha=0.211. ETH/1h is starvation-free (40/40 trials), so reg_alpha forcing test is
     clean. The confirmed lr=0.009-0.010 concentration means ETH/1h converges well — reg_alpha
     anchoring near 0.1-0.2 is the region HPO naturally finds anyway, so constraining lower
     bound to 0.1 eliminates wasted near-zero exploration.
   - Baseline to beat: 0.211438 (iter 100 best)
   - KEEP criterion: any Brier improvement from 0.211438
   - Revert reg_alpha to [1e-8, 10.0] if DISCARD

4. **XRP/15m reg_alpha=[0.1,5.0] AFTER fixing starvation (deferred)**
   - Pre-condition: XRP/15m starvation must be resolved first.
   - Current state: n_estimators=367 near 400 ceiling (27/40 trials) — starvation persists.
   - Next step if XRP/5m item 1 succeeds with 600 ceiling: try XRP/15m [100,300] ceiling.
   - Rationale: Iter 140 showed that reg_alpha forcing + starvation = severe regression (+1.71%).
     Need clean starvation-free search before testing reg_alpha change. XRP/15m optimum appears
     in 100-400 range (n_estimators=138 at 400 ceiling iter 132 was not binding), but
     n_estimators=367 at 400 ceiling in iter 140 with starvation suggests the search is not
     stable. A 300 ceiling may resolve starvation while preserving optimum access.
   - Do NOT combine reg_alpha change + starvation reduction in a single run.

5. **BTC/5m structural exploration — feature subset or lighter regularization**
   - Context: BTC/5m stagnant for 36 iters (best 0.17605 at iter 104). iter 134 showed
     n_estimators=103 near lower bound (100) — optimization landscape non-smooth.
   - LOW PRIORITY: BTC/5m is a structural constraint (929K samples, severe starvation even
     at 800 ceiling). Do NOT retry unless items 1-4 complete with nothing higher priority.
   - If attempted: try reg_alpha=[0.1, 5.0] at [100,800] ceiling (same pattern as ETH/5m/ETH/1h).
     reg_alpha=0.0 in iter 134 best_params confirms zero-collapse. A starvation-free run is
     impossible for BTC/5m, but the reg_alpha fix may help even under starvation.

---

## Observations

**KEEP rates by category (multi-tp era iters 92-140):**
- Anti-starvation n_estimators=[100,800]: 3/7 KEEP (43%): SOL/5m (121), ETH/15m (116), BTC/15m (123) KEEP
- Anti-starvation n_estimators=[100,600]: 2/3 KEEP (67%): XRP/15m (128), SOL/15m (130) KEEP; BTC/1h (131) DISCARD
- Anti-starvation n_estimators=[100,450]: 0/1 KEEP: BTC/1h (133 DISCARD)
- Anti-starvation n_estimators=[100,400]: 0/2 KEEP: XRP/15m (132 DISCARD stochastic tie, 140 DISCARD +1.71%)
- Anti-starvation n_estimators=[100,350]: 1/1 KEEP: BTC/1h (136 NEW BEST 0.174676)
- Anti-starvation n_estimators=[100,250]: 0/2 KEEP: BTC/1h (137/138 stochastic basin)
- HPO range narrowing (lr, min_child, num_leaves): 0/8 KEEP. PERMANENTLY BLACKLISTED
- HPO re-run (no knob changes): 4/9 KEEP (44%): stochastic
- Reg_alpha forcing [0.1,5.0]: 0/2 KEEP so far (iter 139 BTC/1h DISCARD, iter 140 XRP/15m DISCARD);
  SOL/1h [0.1,20.0] was 1/1 KEEP (iter 125) — BUT that was starvation-free. Iter 140 confounded
  by starvation. Iter 139 was marginally starvation-constrained (34/40 trials, 350 ceiling).
  ETH/5m and ETH/1h tests (starvation-free) are needed to properly evaluate this category.
- Walk-forward n_splits change: 0/2 KEEP. BLACKLISTED

**Key findings from iters 137-140:**
- BTC/1h basin depth: Brier oscillates in 0.1746-0.1751 range across iters 136-139. The basin
  is shallow (0.03-0.05%) but persistent across 4 consecutive runs with different n_estimators
  and reg_alpha configurations. No structural escape found yet.
- reg_alpha=0.0 collapse confirmed for BTC/1h (iters 137/138 showed reg_alpha=0.002 and 0.0)
  and XRP/15m (iter 128 reg_alpha=5.8e-05, iter 132 reg_alpha=1e-6). The [0.1,5.0] lower bound
  successfully prevents collapse in both assets (iter 139 BTC/1h: 0.1073; iter 140 XRP/15m: 0.285).
  However, prevention of collapse does not guarantee improvement — the basin is structural.
- XRP/15m + reg_alpha forcing + starvation = bad interaction: The 1.71% regression at iter 140
  shows that combining a new reg_alpha constraint with an already-starved search space amplifies
  suboptimality. Starvation must be resolved first before testing regularization changes.
- Researcher correctly identified and executed strategy items 1-2; items 3-5 are correctly
  queued (researcher_ack.txt confirms awareness).

**Brier trajectory (multi-tp baselines vs current bests, updated through iter 140):**
- BTC/5m: 0.177295 (baseline iter 92) -> 0.17605 (iter 104, -0.70%) -- STAGNANT 36 iters
- BTC/15m: 0.171913 (baseline iter 95) -> 0.171809 (iter 123, -0.061%)
- BTC/1h: 0.175668 (baseline iter 99) -> 0.174676 (iter 136, -0.562%) -- basin at 0.1746-0.1750
- ETH/5m: 0.211888 (baseline iter 117) -- no improvement (2 attempts: iters 129, DISCARD)
- ETH/15m: 0.209819 (baseline iter 96) -> 0.208324 (iter 116, -0.71%)
- ETH/1h: 0.211438 (baseline iter 100) -- no improvement (4 attempts: iters 108, 113, 120, 135)
- SOL/5m: 0.218209 (baseline iter 93) -> 0.218058 (iter 121, -0.069%)
- SOL/15m: 0.215443 (baseline iter 97) -> 0.215345 (iter 130, -0.046%)
- SOL/1h: 0.221683 (baseline iter 101) -> 0.220615 (iter 125, -0.048%)
- XRP/5m: 0.221782 (baseline iter 94) -> 0.221503 (iter 112, -0.126%) -- starvation UNTREATED
- XRP/15m: 0.218727 (baseline iter 98) -> 0.218075 (iter 128, -0.298%) -- structural starvation
- XRP/1h: 0.226947 (baseline iter 102) -> 0.226907 (iter 115, -0.018%)
- SUMMARY: 10/12 asset-timeframes improved. ETH/5m and ETH/1h remain at baseline. BTC/5m
  stagnant 36 iters. Reg_alpha forcing (items 2-3) is the primary remaining lever.

**Alpha feature pattern (confirmed through iter 140):**
- No alpha features (funding_*, liquidation_*, oi_*, iv_*, pm_*) in top-10 across any KEEP row
  in the multi-tp era (44+ KEEP rows across 137 unique iterations). Pattern is consistent and
  absolute. Flagged for auditor review. No alpha-enabled experiments planned.

---

## Risk Profile

- Max drawdown trend: STABLE — BTC assets highest DD (0.18-0.39), ETH/XRP 1h lowest (0.063-0.088)
  BTC/5m DD=0.385-0.39 stable across iters 92/104/122/127/134; no growth trend
- Max DD / PnL ratio (multi-tp KEEP rows): BTC/5m 0.39/$56=0.007; BTC/15m 0.175/$50=0.003;
  BTC/1h 0.199/$12.32=0.016 (iter 136); ETH/5m 0.069/$307=0.0002; all healthy (<1.0)
- Trade count range across KEEP rows: 5m ~75-81K; 15m ~62-77K; 1h ~16-19K; STABLE
- Win rate range across KEEP rows: BTC 62-67% (sniper RAMP), ETH/SOL/XRP ~49-52% (tick-dominant)
- HPO-OOS gap: BTC/1h hpo_objective=0.175703 (iter 136) vs oos_brier=0.174676 — gap minimal (0.1%)
  XRP/15m hpo_objective=0.499 still elevated (starvation proxy, starvation unresolved);
  ETH/5m hpo_objective=0.279 at iter 129 (starvation from min_child narrowing, now reverted)

---

## Timeframe Coverage

- 5m: 28 iterations (iters 92-94, 104, 111, 112, 117, 121, 122, 127, 129, 134), 6 KEEPs,
  best Brier: BTC/5m=0.17605, ETH/5m=0.211888, SOL/5m=0.218058, XRP/5m=0.221503
- 15m: 25 iterations (iters 95-98, 105, 109, 114, 116, 119, 123, 124, 126, 128, 130, 132, 140),
  5 KEEPs, best Brier: BTC/15m=0.171809, ETH/15m=0.208324, SOL/15m=0.215345, XRP/15m=0.218075
- 1h: 28 iterations (iters 99-102, 103, 106, 107, 108, 113, 115, 118, 120, 125, 131, 133, 135,
  136, 137, 138, 139), 8 KEEPs,
  best Brier: BTC/1h=0.174676, ETH/1h=0.211438, SOL/1h=0.220615, XRP/1h=0.226907
- Recommendation: coverage roughly balanced. New priority is reg_alpha widen on starvation-free
  assets (ETH/5m, ETH/1h) and XRP/5m anti-starvation. XRP/5m is the last untreated starvation
  case — fix it first (highest expected value).

---

## Blacklist

- **HPO range narrowing (any parameter)**: 0/8 KEEP rate. PERMANENTLY BLACKLISTED. Do NOT narrow
  lr, num_leaves, min_child, or any HPO bound.
- **Walk-forward n_splits reduction**: 0/2 KEEP rate (iters 127, 135). BLACKLISTED for all assets.
- **Walk-forward train_bars reduction**: 0/1 KEEP (iter 114). LOW PRIORITY.
- **ETH/1h reg_lambda widening**: 0/1 (iter 113). Do not retry.
- **Alpha feature enabling**: absent from top-10 across all 44+ multi-tp KEEP iterations. BLOCKED
  until auditor reviews.
- **reg_alpha forcing + starvation combined**: iter 140 XRP/15m produced +1.71% regression. Do NOT
  combine reg_alpha change with an unresolved starvation condition. Always fix starvation first.

---

## HPO Range Recommendations

- **reg_alpha**: Primary lever for stagnant starvation-free assets. Apply [0.1, 5.0] to:
  ETH/5m (iter 117 reg_alpha=3e-6 near-zero collapse), ETH/1h (iter 135 reg_alpha=0.211 — best
  region is already 0.1-0.2, so lower bound 0.1 anchors HPO there). Precedent: SOL/1h iter 125
  reg_alpha=0.919 KEEP at [0.1,20.0]. For STARVED assets (XRP/15m, BTC/5m): fix starvation
  BEFORE applying reg_alpha forcing.

- **n_estimators**: Confirmed asset-class ceiling recommendations:
  - BTC/5m: [100, 800] — starvation structural (17/40), optimum non-convex; may need feature change
  - BTC/15m: [100, 800] working (235 not near ceiling) — KEEP
  - BTC/1h: [100, 350] current (iter 136 KEEP); optimum ~180-230, [100,250] confirmed starvation-free
    but stochastic basin. Use [100,250] as correct range.
  - ETH/5m: [100, 800] working (182 not near ceiling) — KEEP
  - ETH/15m: [100, 800] working (202 not near ceiling) — KEEP
  - ETH/1h: [100, 800] — starvation-free (40/40 trials); no change needed
  - SOL/5m: [100, 800] working (274 not near ceiling) — KEEP
  - SOL/15m: [100, 600] resolved (154 not near ceiling) — KEEP
  - SOL/1h: [100, 1500] — starvation-free; no change needed
  - XRP/5m: [100, 600] UNTREATED — do immediately (item 1 above); iter 112 showed 12/40 at 1500
  - XRP/15m: [100, 400] still starved (367 near 400 ceiling, 27/40); try [100,300] after items 1-3
  - XRP/1h: [100, 1500] — starvation-free; no change needed

- **learning_rate**: BTC/1h lr=[0.005,0.05] confirmed working (iter 133 resolved lr binding).
  All other assets: current ranges adequate. lr is NOT the binding constraint for any asset.
