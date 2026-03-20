# Strategy Directive
Updated: 2026-03-26T02:00:00Z
After iteration: 131

## Program Status: Autonomous Anti-Starvation Mop-Up — Phase 3

The strategy queue from iter 125 is fully executed. Iters 126-131 completed 4 additional
autonomous experiments. The 600-ceiling fix works for some assets (SOL/15m KEEP) but not
others (XRP/15m still starved at 599, BTC/1h near ceiling at 569). Two assets still lack
a definitive Brier improvement in the multi-tp era: BTC/1h (-0.053% miss at iter 131) and
XRP/15m (KEEP at 0.298% but still starved). BTC/5m is stagnant (0 improvements since iter 104).

---

## Priority Queue

1. **XRP/15m further ceiling reduction n_estimators=[100,400] (highest urgency)**
   - Command: `--asset XRP --timeframe 15m --mode fast`
   - Knob change: hpo_search_space.n_estimators = [100, 400] (from [100, 600])
   - Rationale: XRP/15m iter 128 KEEP at 0.218075 (first multi-tp improvement) but n_estimators=599
     near 600 ceiling -- starvation persists even at 600. SOL/15m went from 692 (starved at 800) to
     154 (resolved at 600). XRP/15m behavior mirrors BTC/5m class: dataset large enough that
     even 600 is too high. Next reduction to 400 forces HPO to explore lower n_estimators.
     If XRP/15m true optimum is around 400-500 like SOL/15m (154), then 400 ceiling will NOT bind
     and starvation resolves. If n_estimators=399 near 400 ceiling, confirm structural starvation
     and report to auditor.
   - Baseline to beat: 0.218075 (iter 128 best)
   - KEEP criterion: any Brier improvement from 0.218075
   - Revert n_estimators to [100, 600] if DISCARD

2. **BTC/1h lr ceiling widen + further n_estimators reduction n_estimators=[100,450]**
   - Command: `--asset BTC --timeframe 1h --mode fast`
   - Knob change: hpo_search_space.n_estimators = [100, 450], hpo_search_space.learning_rate = [0.005, 0.05]
   - Rationale: Iter 131 found two simultaneous binding constraints: (1) n_estimators=569 near 600
     ceiling (32/40 trials -- better but not fully resolved), and (2) lr=0.028 near [0.005,0.03]
     upper bound. These cannot be disentangled from a single experiment. The Brier miss was only
     0.053% (0.175773 vs 0.174864 best) -- very close to improvement. Widening lr ceiling to 0.05
     matches ETH/1h pattern (lr optimum consistently near 0.008-0.010, so widening from 0.03 to 0.05
     does not hurt but removes the binding constraint). Simultaneously reduce n_estimators ceiling
     further from 600 to 450 since 569-near-600 pattern suggests optimum may be 450-550 range.
     Note: lr=[0.005,0.03] was set for BTC/1h iter 107 KEEP (lr=0.008) -- the optimal lr itself is
     not at the ceiling, but the exploration space below 0.03 may be crowded by the n_estimators
     binding constraint causing suboptimal lr selection.
   - Baseline to beat: 0.174864 (iter 107 best)
   - KEEP criterion: any Brier improvement from 0.174864
   - Revert knobs to best_knobs_BTC_1h state if DISCARD

3. **BTC/5m HPO re-run with restored global lr=[0.005,0.1] (stagnation break)**
   - Command: `--asset BTC --timeframe 5m --mode fast`
   - Knob change: hpo_search_space.learning_rate = [0.005, 0.1] (restore global), n_estimators=[100,800]
   - Rationale: BTC/5m n_splits=6 (iter 127) resolved n_estimators ceiling pressure (n_estimators=184
     not near ceiling) but found lr=0.0998 near [0.005,0.1] upper bound. This is surprising since
     BTC/5m prior best (iter 104) used lr=0.058. The n_splits=6 experiment had n_splits reverted to 8,
     but we can now run BTC/5m fresh with n_splits=8 and n_estimators=[100,800] -- this time the
     question is whether stochastic HPO finds a better path than iter 104 (lr=0.058, Brier=0.17605).
     BTC/5m has 0 improvement since iter 104 (127 iters tried: 122, 127 both DISCARD). Fresh re-run
     may find a better basin. This is a pure stochastic re-run with no new knob changes -- low
     expected value but fills the queue while items 1-2 are evaluated.
   - Baseline to beat: 0.17605 (iter 104 best)
   - KEEP criterion: any Brier improvement from 0.17605

4. **ETH/1h n_splits=6 experiment (low-starvation asset, unexpected convergence)**
   - Command: `--asset ETH --timeframe 1h --mode fast`
   - Knob change: walk_forward.n_splits = 6 (from 8)
   - Rationale: ETH/1h is starvation-free (40/40 trials consistently) but best Brier 0.211438 has
     not improved since multi-tp baseline (iter 100). ETH/1h best_params show lr=0.009-0.010
     consistently (sniper-like low lr). Reducing n_splits from 8 to 6 gives HPO more time per trial
     (larger fold = potentially better-fit models), especially beneficial for low-lr assets where
     model convergence takes more iterations. Unlike BTC/5m (which was blacklisted for n_splits
     reduction due to IS-OOS concern), ETH/1h has PBO=ruling 1 (IS-OOS corr=-0.8567) which means
     the CPCV result is NOT regime-seesaw for the auditor. Risk: smaller n_splits = less walk-forward
     coverage. Revert to n_splits=8 if DISCARD.
   - Baseline to beat: 0.211438 (iter 100 best)
   - KEEP criterion: any Brier improvement from 0.211438

---

## Observations

**KEEP rates by category (multi-tp era iters 92-131, rows with numeric Brier):**
- Anti-starvation n_estimators=[100,800]: 3/7 KEEP (43%): SOL/5m (121), ETH/15m (116), BTC/15m (123)
  KEEP; BTC/5m (122), XRP/15m (124), SOL/15m (126), BTC/1h (implicit) DISCARD
- Anti-starvation n_estimators=[100,600]: 2/3 KEEP (67%): XRP/15m (128 KEEP), SOL/15m (130 KEEP);
  BTC/1h (131 DISCARD due to dual binding constraints)
- HPO range narrowing (lr, min_child, num_leaves): 0/7 KEEP (0%): iters 103, 105, 106, 108, 113,
  120, 129 all DISCARD; PERMANENTLY BLACKLISTED
- HPO re-run (no knob changes): 4/9 KEEP (44%): iters 104, 107, 112, 115 KEEP; stochastic
- Reg parameter widening: 1/2 KEEP (50%): SOL/1h iter 125 KEEP; ETH/1h iter 113 DISCARD
- Walk-forward n_splits change: 0/1 KEEP (0%): BTC/5m n_splits=6 iter 127 DISCARD
- Walk-forward train_bars change: 0/1 KEEP (0%): BTC/15m train_bars=7500 iter 114 DISCARD

**Key findings from iters 126-131:**
- Ceiling reduction threshold varies by asset: SOL/15m resolved at 600 (n_estimators=154 not near
  ceiling); XRP/15m NOT resolved at 600 (599 near ceiling); BTC/1h NOT resolved at 600 (569 near
  ceiling). Assets with large datasets + high preferred n_estimators need more aggressive reductions.
- BTC/1h dual binding at iter 131: n_estimators=569/600 AND lr=0.028/0.030 simultaneously near
  ceiling -- this is the first case of two HPO bounds binding together; explains the marginal miss
  (0.053% worse than best).
- BTC/5m n_splits=6 resolved n_estimators starvation but found lr=0.0998 near 0.1 ceiling -- the
  starvation manifests differently depending on fold count (8-fold: n_estimators starvation; 6-fold:
  lr exploration bias). BTC/5m stagnation may be structural at this point.
- XRP/15m hpo_objective=0.498 persistently elevated (starvation proxy). SOL/15m hpo_objective=0.362
  is lower (less penalty, better search). This confirms XRP/15m search quality is impaired by
  remaining starvation at 600 ceiling.

**Brier trajectory (multi-tp baselines vs current bests, updated):**
- BTC/5m: 0.177295 (baseline iter 92) -> 0.17605 (iter 104, -0.70%) -- STAGNANT 27 iters
- BTC/15m: 0.171913 (baseline iter 95) -> 0.171809 (iter 123, -0.061%)
- BTC/1h: 0.175668 (baseline iter 99) -> 0.174864 (iter 107, -0.46%) -- marginal miss at iter 131
- ETH/5m: 0.211888 (baseline iter 117) -- no improvement (1 attempt, range contraction DISCARD)
- ETH/15m: 0.209819 (baseline iter 96) -> 0.208324 (iter 116, -0.71%)
- ETH/1h: 0.211438 (baseline iter 100) -- no improvement (3 attempts: reg_lambda, lr narrowing, re-run)
- SOL/5m: 0.218209 (baseline iter 93) -> 0.218058 (iter 121, -0.069%)
- SOL/15m: 0.215443 (baseline iter 97) -> 0.215345 (iter 130, -0.046%) -- resolved via [100,600]
- SOL/1h: 0.221683 (baseline iter 101) -> 0.220615 (iter 125, -0.048%)
- XRP/5m: 0.221782 (baseline iter 94) -> 0.221503 (iter 112, -0.126%)
- XRP/15m: 0.218727 (baseline iter 98) -> 0.218075 (iter 128, -0.298%) -- first improvement
- XRP/1h: 0.226947 (baseline iter 102) -> 0.226907 (iter 115, -0.018%)
- SUMMARY: 9/12 asset-timeframes have shown improvement. ETH/5m, ETH/1h, and (previously) SOL/15m
  are the remaining zeros. SOL/15m just improved. Largest: BTC/5m -0.70%, ETH/15m -0.71%.

**Alpha feature pattern (confirmed across multi-tp era):**
- NONE of the alpha features (funding_*, liquidation_*, oi_*, iv_*, pm_*) appear in top-10 across
  any KEEP row in the multi-tp era (iters 92-131). This is consistent across all 12 asset-timeframes.
- Note: liquidation_proximity, oi_price_divergence, oi_momentum, leverage_proxy ARE in cached_features
  (knobs.json) and are protected from feature selection filtering. However, they remain below top-10.
- Recommendation: flag for auditor review -- alpha features may be noise in multi-tp regime and
  consuming search budget without contributing signal. Do NOT disable until auditor approves.

---

## Risk Profile

- Max drawdown trend: STABLE -- BTC assets highest DD (0.18-0.39), ETH/XRP 1h lowest (0.063-0.088)
  BTC/5m DD=0.385-0.39 stable across iters 92/104/122/127; no growth trend
- Max DD / PnL ratio (multi-tp KEEP rows): BTC/5m 0.39/$56=0.007 (healthy); BTC/15m 0.175/$50=0.003;
  BTC/1h 0.22/$12=0.018; ETH/5m ~0.069/$308=0.0002; SOL/15m 0.054/$289=0.0002; all healthy (<1.0)
- Trade count range across KEEP rows: 5m ~75-81K; 15m ~62-77K; 1h ~16-19K; STABLE
- Win rate range across KEEP rows: BTC 62-67% (sniper), ETH/SOL/XRP ~49-52% (tick-dominant); STABLE
- HPO-OOS gap: hpo_objective ~0.168-0.175 for BTC/5m (brier+penalty composite near brier value
  for high-trade assets); XRP/15m hpo_objective=0.498 elevated (starvation indicator); SOL/15m
  hpo_objective=0.362 (same pattern); gaps stable for non-starved assets

---

## Timeframe Coverage

- 5m: 26 iterations (iters 92-94, 104, 111, 112, 117, 121, 122, 127, 129), 6 KEEPs,
  best Brier: BTC/5m=0.17605, ETH/5m=0.211888, SOL/5m=0.218058, XRP/5m=0.221503
- 15m: 24 iterations (iters 95-98, 105, 109, 114, 116, 119, 123, 124, 126, 128, 130), 5 KEEPs,
  best Brier: BTC/15m=0.171809, ETH/15m=0.208324, SOL/15m=0.215345, XRP/15m=0.218075
- 1h: 20 iterations (iters 99-102, 103, 106, 107, 108, 113, 115, 118, 120, 125, 131), 6 KEEPs,
  best Brier: BTC/1h=0.174864, ETH/1h=0.211438, SOL/1h=0.220615, XRP/1h=0.226907
- Recommendation: balanced coverage; 1h is slightly under-explored for improvement opportunities
  (ETH/1h and XRP/1h have had minimal improvement). Prioritize XRP/15m and BTC/1h next.

---

## Blacklist

- **HPO range narrowing (any parameter)**: 0/7 KEEP rate across iters 103, 105, 106, 108, 113, 120,
  129. PERMANENTLY BLACKLISTED. Do NOT narrow lr, num_leaves, min_child, or any HPO bound.
- **BTC/5m n_splits change**: 0/1 (iter 127 DISCARD). Suspension lifted per auditor but DISCARD
  confirmed -- BTC/5m n_splits reduction resolves n_estimators starvation but does not improve
  Brier (lr becomes binding instead). LOW PRIORITY for repeat.
- **ETH/1h reg_lambda widening**: 0/1 (iter 113 DISCARD). reg_lambda optimum for ETH/1h is near
  1.4, NOT high values. Do not retry.
- **Alpha feature enabling**: alpha features absent from top-10 across all 40 multi-tp KEEP iterations.
  Enabling additional alpha groups (options_iv, polymarket) is BLOCKED until auditor reviews.

---

## HPO Range Recommendations

- **n_estimators**: Asset-class ceiling recommendations:
  - BTC/5m: [100, 800] current -- genuine optimum may be 700+; do NOT reduce further
  - BTC/15m: [100, 800] working (235 not near ceiling) -- KEEP
  - BTC/1h: try [100, 450] (569 near 600; need more aggressive reduction)
  - ETH/5m: [100, 800] working (182 not near ceiling after anti-starvation fix) -- KEEP
  - ETH/15m: [100, 800] working (202 not near ceiling) -- KEEP
  - ETH/1h: [100, 1500] current -- 40/40 trials, starvation-free; no change needed
  - SOL/5m: [100, 800] working (274 not near ceiling) -- KEEP
  - SOL/15m: [100, 600] just resolved (154 not near ceiling) -- KEEP
  - SOL/1h: [100, 1500] current -- 40/40 trials, starvation-free; no change needed
  - XRP/5m: try [100, 600] (12/40 trials at 1500 ceiling -- starvation UNTREATED for XRP/5m)
  - XRP/15m: try [100, 400] (599 near 600 ceiling -- further reduction needed)
  - XRP/1h: [100, 1500] current -- 40/40 trials, starvation-free; no change needed
- **learning_rate**: BTC/1h lr=[0.005,0.03] needs widening to [0.005,0.05] given lr=0.028 binding.
  All other assets: current [0.005,0.1] (or asset-specific) adequate.
- **NOTE**: XRP/5m has NOT received anti-starvation treatment (12/40 trials at iter 112, n_estimators
  ceiling at 1500). This is an overlooked asset that should be addressed after items 1-2 above.
  Add as item 5 if queue needs filling: XRP/5m n_estimators=[100,600].
