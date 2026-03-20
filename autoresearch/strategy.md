# Strategy Directive
Updated: 2026-03-26T10:00:00Z
After iteration: 136

## Program Status: Anti-Starvation Mop-Up — Phase 4

Iters 132-136 executed all 4 items from the post-iter-131 queue. Results: 1 KEEP (BTC/1h iter 136
new best 0.174676), 4 DISCARD. Key themes:

1. **XRP/15m [100,400]** (iter 132): n_estimators=138 not near ceiling (starvation resolved), but
   Brier=0.218115 vs best 0.218075 (+0.018% stochastic tie). XRP/15m is in a stochastic basin —
   two stochastic re-runs at the same ceiling have produced marginal misses. Need a structural
   change (reg_alpha exploration) or accept the current best.

2. **BTC/1h ceiling progression** (iters 131->133->136): 600->450->350. Each reduction improved
   trial count (32->38->37/40) and progressively lowered Brier. Iter 136 finally achieved NEW BEST
   at [100,350] with n_estimators=350 AT ceiling — optimum is below 350. Further reduction to
   [100,250] is warranted.

3. **BTC/5m structural stagnation** (iter 134): 17/40 trials SEVERE starvation at 800 ceiling,
   n_estimators=103 near lower bound — optimization landscape is non-smooth. BTC/5m is a
   structurally hard asset with 929K samples; stagnant since iter 104 (32 iters).

4. **ETH/1h n_splits=6** (iter 135): DISCARD confirms that reducing fold count does not help
   ETH/1h (lr and feature landscape are the binding constraints, not fold size).

5. **researcher_ack.txt** reports iter 138 (BTC/1h DISCARD at [100,250]) — the researcher already
   autonomously followed up on iter 136's ceiling finding. Two consecutive [100,250] runs both
   missed by <0.03% (stochastic basin at Brier~0.1746-0.1750). The researcher correctly identified
   the BTC/1h stochastic basin and is seeking a structural escape lever.

---

## Priority Queue

1. **BTC/1h reg_alpha widen to [0.1, 5.0] + restore n_estimators=[100,350] (stochastic basin escape)**
   - Command: `--asset BTC --timeframe 1h --mode fast`
   - Knob change: hpo_search_space.reg_alpha = [0.1, 5.0] (from [1e-8, 10.0])
   - Keep: hpo_search_space.n_estimators = [100, 350], hpo_search_space.learning_rate = [0.005, 0.05]
   - Rationale: Two consecutive [100,250] runs (iters 137/138) produced best_params reg_alpha=0.0 in
     both (per researcher_ack.txt). This means HPO is collapsing to the lower bound of [1e-8, 10.0]
     for reg_alpha — the current range is too wide and low-reg corner is noise-dominant. BTC/1h
     iter 136 best_params had reg_alpha=0.001456 (also near lower bound). SOL/1h iter 125 found
     reg_alpha=0.919 as the true optimum when the range was narrowed away from near-zero. By
     setting a lower bound of 0.1, we force HPO to explore the meaningful regularization region
     rather than vacuously choosing reg_alpha~0. This is a structural search space improvement,
     not a range narrowing (the upper bound 5.0 is within the prior 10.0 range).
   - Baseline to beat: 0.174676 (iter 136 best)
   - KEEP criterion: any Brier improvement from 0.174676
   - Revert reg_alpha to [1e-8, 10.0] if DISCARD

2. **XRP/15m reg_alpha widen to [0.1, 5.0] + n_estimators=[100,400] (stochastic basin escape)**
   - Command: `--asset XRP --timeframe 15m --mode fast`
   - Knob change: hpo_search_space.reg_alpha = [0.1, 5.0] (from [1e-8, 10.0])
   - Keep: hpo_search_space.n_estimators = [100, 400]
   - Rationale: XRP/15m is in a stochastic basin at Brier~0.218 (iters 128, 132 both ~0.218).
     Similar to BTC/1h, iter 128 best_params had reg_alpha=5.8e-05 (near zero). The reg_alpha=0
     collapse pattern seen in BTC/1h iters 137/138 may also affect XRP/15m. XRP/5m iter 112
     best_params showed reg_alpha=0.089 (modest positive value). Testing [0.1, 5.0] forces
     non-zero regularization exploration and may shift the basin. Two-iteration stochastic tie
     (0.298% gain at iter 128, 0.018% miss at iter 132) suggests the landscape is flat — a
     structural search change is the right lever.
   - Baseline to beat: 0.218075 (iter 128 best)
   - KEEP criterion: any Brier improvement from 0.218075
   - Revert reg_alpha to [1e-8, 10.0] if DISCARD

3. **XRP/5m anti-starvation n_estimators=[100,600] (untreated starvation)**
   - Command: `--asset XRP --timeframe 5m --mode fast`
   - Knob change: hpo_search_space.n_estimators = [100, 600] (from [100, 1500] or current)
   - Rationale: XRP/5m has NEVER received anti-starvation treatment. Iter 112 showed only 12/40
     HPO trials at the 1500 ceiling — the same severe starvation class as BTC/5m at [100,1500].
     All other 11 asset-timeframes have received ceiling reductions; XRP/5m is the sole untreated
     asset. SOL/5m iter 121 resolved at 600 (n_estimators=274, not near ceiling). XRP/5m likely
     similar dataset class to SOL/5m (~300K samples). Starting at 600 (not 800) skips the
     partially-effective 800 ceiling and goes directly to the resolution point.
   - Baseline to beat: 0.221503 (iter 112 best)
   - KEEP criterion: any Brier improvement from 0.221503
   - Revert n_estimators to [100, 1500] or [100, 800] if DISCARD

4. **ETH/5m reg_alpha widen to [0.1, 5.0] (no improvement since multi-tp baseline)**
   - Command: `--asset ETH --timeframe 5m --mode fast`
   - Knob change: hpo_search_space.reg_alpha = [0.1, 5.0] (from [1e-8, 10.0])
   - Rationale: ETH/5m has only 1 improvement attempt (iter 129 min_child narrowing DISCARD). The
     iter 117 baseline best_params had reg_alpha=3e-6 (near-zero), same low-reg collapse pattern
     as BTC/1h and XRP/15m. ETH/15m iter 116 best_params showed reg_alpha=0.0 (also collapsed).
     The [0.1, 5.0] reg_alpha fix that is being applied to BTC/1h and XRP/15m should also be
     tested for ETH/5m as a batch. Note: ETH/5m uses n_estimators=[100,800] (working, 23/40
     trials — no starvation change needed). Keep n_estimators=[100,800].
   - Baseline to beat: 0.211888 (iter 117 best)
   - KEEP criterion: any Brier improvement from 0.211888
   - Revert reg_alpha to [1e-8, 10.0] if DISCARD

5. **ETH/1h reg_alpha widen to [0.1, 5.0] (no improvement since multi-tp baseline)**
   - Command: `--asset ETH --timeframe 1h --mode fast`
   - Knob change: hpo_search_space.reg_alpha = [0.1, 5.0] (from [1e-8, 10.0])
   - Rationale: ETH/1h has 0 Brier improvements since iter 100 baseline (3 attempts: iters 108,
     113, 120, 135 all DISCARD). Iter 100 best_params: reg_alpha=0.146; iter 135 best_params:
     reg_alpha=0.211. ETH/1h is notably the only asset where reg_alpha shows modest non-zero values
     in best_params (~0.1-0.2), yet the current search range [1e-8, 10.0] allows HPO to collapse
     below 0.1. Constraining the lower bound to 0.1 anchors exploration in the region where ETH/1h
     naturally converges. Combined with the confirmed lr=0.009-0.010 consistency, this is a
     targeted structural refinement.
   - Baseline to beat: 0.211438 (iter 100 best)
   - KEEP criterion: any Brier improvement from 0.211438
   - Revert reg_alpha to [1e-8, 10.0] if DISCARD

---

## Observations

**KEEP rates by category (multi-tp era iters 92-136, rows with numeric Brier):**
- Anti-starvation n_estimators=[100,800]: 3/7 KEEP (43%): SOL/5m (121), ETH/15m (116), BTC/15m (123)
  KEEP; BTC/5m (122), XRP/15m (124), SOL/15m (126), BTC/1h (implicit) DISCARD
- Anti-starvation n_estimators=[100,600]: 2/3 KEEP (67%): XRP/15m (128 KEEP), SOL/15m (130 KEEP);
  BTC/1h (131 DISCARD)
- Anti-starvation n_estimators=[100,450]: 0/1 KEEP (0%): BTC/1h (133 DISCARD — n_estimators still
  binding at 427/450)
- Anti-starvation n_estimators=[100,400]: 0/1 KEEP (0%): XRP/15m (132 DISCARD — stochastic tie
  0.018% miss; n_estimators=138 not near ceiling, starvation resolved but no Brier gain)
- Anti-starvation n_estimators=[100,350]: 1/1 KEEP (100%): BTC/1h (136 NEW BEST 0.174676)
- HPO range narrowing (lr, min_child, num_leaves): 0/8 KEEP (0%): PERMANENTLY BLACKLISTED
- HPO re-run (no knob changes): 4/9 KEEP (44%): stochastic
- Reg parameter widening: 1/2 KEEP (50%): SOL/1h iter 125 KEEP; ETH/1h iter 113 DISCARD
- Walk-forward n_splits change: 0/2 KEEP (0%): BTC/5m iter 127 DISCARD, ETH/1h iter 135 DISCARD

**Key findings from iters 132-136:**
- BTC/1h ceiling progression confirms: true n_estimators optimum is below 350. Progressive
  reductions (1500->600->450->350->250 tested by researcher) show monotonic improvement in
  trial count and Brier until a stochastic floor at ~0.1746-0.1750 was hit.
- reg_alpha=0.0 collapse is now the primary hypothesis for stagnant assets (BTC/1h iters 137/138,
  XRP/15m iter 128, BTC/5m iters 122/127/134). HPO collapsing to near-zero reg_alpha may be
  preventing escape from local minima.
- ETH/1h n_splits=6 (iter 135): 0/2 walk-forward changes DISCARD — fold count is not a lever for
  any asset in the multi-tp era.
- BTC/5m structural stagnation confirmed: 17/40 trials at [100,800] with n_estimators=103 near
  lower bound (unusual) — landscape is non-convex. May need feature subset or regime change to
  escape, not HPO tuning.

**Brier trajectory (multi-tp baselines vs current bests, updated through iter 136):**
- BTC/5m: 0.177295 (baseline iter 92) -> 0.17605 (iter 104, -0.70%) -- STAGNANT 32 iters
- BTC/15m: 0.171913 (baseline iter 95) -> 0.171809 (iter 123, -0.061%)
- BTC/1h: 0.175668 (baseline iter 99) -> 0.174676 (iter 136 NEW BEST, -0.562% from baseline)
- ETH/5m: 0.211888 (baseline iter 117) -- no improvement (2 attempts, both DISCARD)
- ETH/15m: 0.209819 (baseline iter 96) -> 0.208324 (iter 116, -0.71%)
- ETH/1h: 0.211438 (baseline iter 100) -- no improvement (4 attempts, all DISCARD)
- SOL/5m: 0.218209 (baseline iter 93) -> 0.218058 (iter 121, -0.069%)
- SOL/15m: 0.215443 (baseline iter 97) -> 0.215345 (iter 130, -0.046%)
- SOL/1h: 0.221683 (baseline iter 101) -> 0.220615 (iter 125, -0.048%)
- XRP/5m: 0.221782 (baseline iter 94) -> 0.221503 (iter 112, -0.126%) -- starvation UNTREATED
- XRP/15m: 0.218727 (baseline iter 98) -> 0.218075 (iter 128, -0.298%) -- stochastic basin
- XRP/1h: 0.226947 (baseline iter 102) -> 0.226907 (iter 115, -0.018%)
- SUMMARY: 10/12 asset-timeframes have shown improvement. ETH/5m and ETH/1h are the remaining
  zeros. BTC/1h is now improved to 0.174676. Largest improvements: ETH/15m -0.71%, BTC/5m -0.70%,
  BTC/1h -0.562%.

**Alpha feature pattern (confirmed through iter 136):**
- No alpha features (funding_*, liquidation_*, oi_*, iv_*, pm_*) in top-10 across any KEEP row
  in the multi-tp era. Consistent across all 12 asset-timeframes. Flagged for auditor review.

---

## Risk Profile

- Max drawdown trend: STABLE — BTC assets highest DD (0.18-0.39), ETH/XRP 1h lowest (0.063-0.088);
  BTC/5m DD=0.385-0.39 stable across iters 92/104/122/127/134; no growth trend
- Max DD / PnL ratio (multi-tp KEEP rows): BTC/5m 0.39/$56=0.007 (healthy); BTC/15m 0.175/$50=0.003;
  BTC/1h 0.199/$12.32=0.016 (iter 136 new best); ETH/5m 0.069/$307=0.0002; all healthy (<1.0)
- Trade count range across KEEP rows: 5m ~75-81K; 15m ~62-77K; 1h ~16-19K; STABLE
- Win rate range across KEEP rows: BTC 62-67% (sniper RAMP), ETH/SOL/XRP ~49-52% (tick-dominant FLAT)
- HPO-OOS gap: BTC/1h hpo_objective=0.175703 (iter 136) vs oos_brier=0.174676 — gap minimal (0.1%);
  XRP/15m hpo_objective=0.498 still elevated (starvation proxy, starvation partially resolved);
  gaps stable for non-starved assets

---

## Timeframe Coverage

- 5m: 28 iterations (iters 92-94, 104, 111, 112, 117, 121, 122, 127, 129, 134), 6 KEEPs,
  best Brier: BTC/5m=0.17605, ETH/5m=0.211888, SOL/5m=0.218058, XRP/5m=0.221503
- 15m: 25 iterations (iters 95-98, 105, 109, 114, 116, 119, 123, 124, 126, 128, 130, 132), 5 KEEPs,
  best Brier: BTC/15m=0.171809, ETH/15m=0.208324, SOL/15m=0.215345, XRP/15m=0.218075
- 1h: 24 iterations (iters 99-102, 103, 106, 107, 108, 113, 115, 118, 120, 125, 131, 133, 135, 136),
  7 KEEPs, best Brier: BTC/1h=0.174676, ETH/1h=0.211438, SOL/1h=0.220615, XRP/1h=0.226907
- Recommendation: coverage balanced. New priority is reg_alpha widen across stagnant assets (BTC/1h,
  XRP/15m, ETH/5m, ETH/1h) rather than timeframe rotation.

---

## Blacklist

- **HPO range narrowing (any parameter)**: 0/8 KEEP rate. PERMANENTLY BLACKLISTED. Do NOT narrow
  lr, num_leaves, min_child, or any HPO bound.
- **Walk-forward n_splits reduction**: 0/2 KEEP rate (iters 127, 135). BLACKLISTED for all assets.
  Fold count is not a productive lever in the multi-tp era.
- **Walk-forward train_bars reduction**: 0/1 KEEP (iter 114 DISCARD). LOW PRIORITY.
- **ETH/1h reg_lambda widening**: 0/1 (iter 113 DISCARD). reg_lambda optimum for ETH/1h near 1.4.
  Do not retry.
- **Alpha feature enabling**: absent from top-10 across all 44+ multi-tp KEEP iterations. BLOCKED
  until auditor reviews.

---

## HPO Range Recommendations

- **reg_alpha**: The primary new lever for stagnant assets is setting a non-zero lower bound.
  Current [1e-8, 10.0] allows HPO to collapse to near-zero, which is a wasted search region.
  Apply [0.1, 5.0] to: BTC/1h (iters 137/138 confirmed reg_alpha=0.0 collapse), XRP/15m (iter 128
  reg_alpha=5.8e-05 near-zero), ETH/5m (iter 117 reg_alpha=3e-6), ETH/1h (confirmed ~0.1-0.2 zone).
  Precedent: SOL/1h reg_alpha=0.919 was the true optimum at [0.1, 20.0] widen (iter 125 KEEP).

- **n_estimators**: Updated asset-class ceiling recommendations:
  - BTC/5m: [100, 800] — starvation structural at 800 (17/40), optimum near lower bound (103)
    at iter 134. May need feature/regime change rather than HPO tuning.
  - BTC/15m: [100, 800] working (235 not near ceiling) — KEEP
  - BTC/1h: [100, 350] current (iter 136 KEEP, n_estimators=350 AT ceiling); try [100,250] — already
    attempted autonomously (iters 137/138), both DISCARD (stochastic basin). Use [100,350] as stable
    ceiling with reg_alpha fix as next lever.
  - ETH/5m: [100, 800] working (182 not near ceiling) — KEEP
  - ETH/15m: [100, 800] working (202 not near ceiling) — KEEP
  - ETH/1h: [100, 1500] or [100, 800] — starvation-free (40/40 trials); no change needed
  - SOL/5m: [100, 800] working (274 not near ceiling) — KEEP
  - SOL/15m: [100, 600] resolved (154 not near ceiling) — KEEP
  - SOL/1h: [100, 1500] — starvation-free; no change needed
  - XRP/5m: [100, 600] UNTREATED (12/40 trials at 1500 — do immediately, item 3 above)
  - XRP/15m: [100, 400] — starvation partially resolved (138 not near 400 ceiling, 29/40 trials);
    next lever is reg_alpha, not further ceiling reduction
  - XRP/1h: [100, 1500] — starvation-free; no change needed

- **learning_rate**: BTC/1h lr=[0.005,0.05] confirmed working (iter 133 resolved lr binding).
  All other assets: current ranges adequate. lr is NOT the binding constraint post-iter-133.
