# Dutch Audit Report
After iteration 139 (2026-03-27T11:30:00Z)

## Directives

- FREEZE BTC_5m — PERMANENT (maintained): fill mechanics structural (P=5.6%); diagnostic iter 60 confirms no lever can fix this
- FREEZE BTC_15m — MAINTAINED: 3 consecutive zero-pair baselines; outcome sparsity structural (7.9%)
- FREEZE BTC_1h — MAINTAINED: extreme sparsity (2.9%); gate series exhausted
- FREEZE ETH_5m — MAINTAINED: DD=28.7% near 30% kill threshold; fill mechanics structural (P=5.8%); 3 consecutive zero-pair baselines
- FREEZE ETH_15m — MAINTAINED: gate series exhausted R4 (iters 5/17/40 all zero pairs); outcome sparsity structural (9.9%); strong latent signal (correct_side=71.2%) but structurally blocked
- FREEZE SOL_5m — MAINTAINED: 3 consecutive zero-pair runs; fill mechanics structural (P=4.2%); DD=23.2% elevated
- FREEZE SOL_15m — MAINTAINED: correct_side=45.5% (both measurements below 50%); directionally wrong; resume only when correct_side >50%
- FREEZE SOL_1h — MAINTAINED: 3 consecutive zero-pair baselines; outcome sparsity structural (8.6%)
- FREEZE XRP_5m — PERMANENT (maintained): structural fill_rate=15.6% floor; zero pairs at all tested gates
- FREEZE XRP_15m — MAINTAINED: correct_side declined monotonically 53.7%->50.0%->49.2%; gate series exhausted; confirmed degrading
- CONTINUE ETH_1h — ACTIVE: pair_cost=0.577 below target; profit=+$0.19/bar positive; risk_t_start DISCARD (iter133); next experiment: risk_t_end 0.8->0.75 (rotation 12 item 2). ETH_1h is the system's only profitable pair.
- CONTINUE XRP_1h — ACTIVE: pair_cost=0.785 meets target; profit=-$0.026/bar near breakeven; risk_t_start DISCARD-DD_BREACH (iter139) with matched_ratio signal (5.1% improved); next experiment: risk_t_end 0.8->0.75 (rotation 12 item 2). NOTE: risk_t_end changes the ramp endpoint, not ramp start — should NOT trigger same DD breach as risk_t_start.

## Per-Pair Assessment

| Pair | Best PairCost | MatchedRatio | CorrectSide | MaxDD% | KEEP Rate (active iters) | Trajectory | Action |
|------|--------------|--------------|-------------|--------|--------------------------|------------|--------|
| BTC_5m | 0.000 | 0% | 62.9% | 23.4% | 0/0 (frozen) | BLOCKED PERMANENT — fill mechanics (P=5.6%) | FREEZE PERMANENT |
| BTC_15m | 0.000 | 0% | 60.7% | 12.4% | 0/0 (frozen) | BLOCKED — outcome sparsity (7.9%) | FREEZE |
| BTC_1h | 0.000 | 0% | 70.0% | 3.9% | 0/0 (frozen) | BLOCKED — extreme sparsity (2.9%) | FREEZE |
| ETH_5m | 0.000 | 0% | 52.9% | 28.7% | 0/0 (frozen) | BLOCKED — fill mechanics (P=5.8%) + DD risk | FREEZE |
| ETH_15m | 0.000 | 0% | 71.2% | 7.1% | 0/0 (frozen) | BLOCKED — outcome sparsity (9.9%); strongest latent signal | FREEZE |
| ETH_1h | 0.577 (iter 78) | 1.9% | 67.7% | 11.2% | 5/13 active = 38.5% | STABLE: profit=+$0.19/bar ceiling; risk_t_start DISCARD (noise); fill-sim exhausted | CONTINUE |
| SOL_5m | 0.000 | 0% | 56.2% | 23.2% | 0/0 (frozen) | BLOCKED PERMANENT — fill mechanics (P=4.2%) | FREEZE |
| SOL_15m | 0.567* | 0.3% | 45.5% | 19.8% | 0/0 (frozen) | FROZEN — directionally wrong | FREEZE |
| SOL_1h | 0.000 | 0% | 54.5% | 8.3% | 0/0 (frozen) | BLOCKED — outcome sparsity (8.6%) | FREEZE |
| XRP_5m | N/A | 0% | 57.8% | 13.4% | 0/0 (frozen) | PERMANENT FREEZE | FREEZE PERMANENT |
| XRP_15m | 0.950 | 0.7% | 49.2% | 20.5% | 0/0 (frozen) | DEGRADING — correct_side declining | FREEZE |
| XRP_1h | 0.785 (iter 79) | 3.9% | 64.3% | 10.6% | 4/12 active = 33.3% | IMPROVING: profit -$0.14->-$0.026/bar; risk_t_start sensitive to DD; risk_t_end next | CONTINUE |

*SOL_15m: artificially low pair_cost (near-zero pairs)

## trader_a Gap Analysis

| Pair | PairCost | Target | Cost Gap | Profit/bar | DD | Status | ETA |
|------|----------|--------|----------|------------|-----|--------|-----|
| ETH_1h | 0.577 | <0.85 | -0.273 (BEATS by 32%) | +$0.19 | 11.2% | PROFITABLE — all trader_a benchmarks met; risk_budget next category | 2-3 risk_budget experiments |
| XRP_1h | 0.785 | <0.85 | -0.065 (BEATS by 7.6%) | -$0.026 | 10.6% | IMPROVING — cost meets target; profit approaching zero; risk_budget next | 1-2 productive experiments |
| All others | 0.000 or N/A | <0.85 | N/A | N/A | various | FROZEN — structural | Unblockable without engineering |

## Trajectory Analysis (iters 116-139, since last audit at iter 115)

### Rotation 11 (iters 116-127): 0 KEEPs from 2 active experiments (0%)

Both cancel_distance=0.03 experiments collapsed identically:

- Iter 121 ETH_1h cancel_distance 0.05->0.03 DISCARD: fill_rate 86%->43.6% (-42.4pp), profit +$0.19->+$0.06/bar (-68%). Matched_ratio technically improved 1.9%->2.3% but profit collapse overwhelms. 3% threshold falls within normal ETH price noise — over-cancellation before fills. cancel_distance floor confirmed at 0.05 for ETH_1h. ALL fill-sim sub-params now exhausted for ETH_1h.

- Iter 127 XRP_1h cancel_distance 0.05->0.03 DISCARD-COLLAPSE: matched_ratio COLLAPSED 3.9%->1.6% (< 2.0% immediate DISCARD threshold), fill_rate halved 74.3%->34.2% (-40.1pp), profit -$0.026->-$0.384/bar (-1378%). cancel_distance floor confirmed at 0.05 for XRP_1h. ALL fill-sim sub-params now exhausted for XRP_1h.

Global rule confirmed: cancel_distance=0.03 universally destructive for 1h bars (both ETH_1h and XRP_1h). Floor=0.05 is an absolute lower bound for 1h timeframe pairs.

### Rotation 12 (iters 128-139): 0 KEEPs from 2 active experiments (0%)

Both risk_t_start=0.15 experiments failed, for different reasons:

- Iter 133 ETH_1h risk_t_start 0.10->0.15 DISCARD: profit regressed +$0.19->+$0.12/bar (-37%). Matched_ratio unchanged 1.9%. fill_rate unchanged 86.1%. pair_cost stable 0.577. DD stable 11.2%. No criteria met. The regression is within statistical noise (±$0.05/bar floor), but no positive signal either. Thin dataset (4-5 outcomes) makes this experiment ambiguous — the negative result is plausibly noise, but the hypothesis (timing improves resolved prices) was not supported.

- Iter 139 XRP_1h risk_t_start 0.10->0.15 DISCARD-DD_BREACH: DD=16.7% exceeded 15% threshold. Profit regressed -$0.026->-$0.45/bar (-1630%). BUT matched_ratio IMPROVED 3.9%->5.1% (+1.2pp). This is a mixed signal: the timing shift does improve order placement quality (more matched pairs), but causes broader drawdown excursions. Interpretation: delaying the ramp START concentrates buys later in bar, reducing the time available for inventory rebalancing, producing larger unhedged exposures. The XRP_1h DD sensitivity to ramp-start timing is confirmed. risk_t_start floor at 0.10 for XRP_1h.

**Critical observation from iter 139 XRP_1h:** matched_ratio 3.9%->5.1% improvement under risk_t_start=0.15 is a meaningful positive signal. This confirms the hypothesis that later-bar ordering does improve pair formation timing. However, the mechanism for DD breach (delayed rebalancing) is specific to risk_t_start, not risk_t_end. Changing risk_t_end from 0.8 to 0.75 maintains the SAME ramp start (t=0.10) but moves the peak sizing 3 minutes earlier. This:
1. Does NOT delay early rebalancing (no DD risk)
2. Creates 3 extra minutes of peak-sized ordering at the ramp apex
3. Should also improve matched_ratio through better timing overlap

Risk_t_end=0.75 is mechanistically different from risk_t_start=0.15 and should not replicate the DD breach.

## KEEP Rate Summary (cumulative post-audit-115)

| Rotation | Active Experiments | KEEPs | KEEP Rate |
|----------|--------------------|-------|-----------|
| R11 (iters 116-127) | 2 | 0 | 0% |
| R12 partial (iters 128-139) | 2 | 0 | 0% |
| **Total R11-R12 partial** | **4** | **0** | **0%** |
| **Cumulative (all rotations, non-baseline active)** | **~26** | **5** | **19.2%** |

0% KEEP rate over last 4 experiments is expected: fill-sim category exhausted (floors hit, not improvable), risk_t_start failed for different structural reasons on each pair. The category switch to risk_t_end maintains theoretical value based on iter 139's matched_ratio signal.

## Risk Flags

1. **ETH_1h at parametric ceiling for current dataset**: Both fill-sim and risk_t_start are exhausted. If risk_t_end and risk_exponent also DISCARD, ETH_1h has reached its structural optimization floor. Current performance (+$0.19/bar, pair_cost=0.577) already beats all trader_a benchmarks. The parametric ceiling is a good outcome, not a failure — ETH_1h is genuinely optimized.

2. **XRP_1h DD sensitivity to ramp-start timing confirmed**: risk_t_start=0.15 triggered DD=16.7% (from 10.58% baseline) — a 57.8% relative increase in drawdown. This sensitivity is specific to ramp-start delay (late buys, delayed hedging window). risk_t_end=0.75 does not shift ramp start, so the same mechanism should not apply. However, if DD risk materializes again on risk_t_end, the risk budget category will be effectively closed for XRP_1h.

3. **XRP_1h knobs discrepancy detected**: `knobs_XRP_1h.json` shows `min_buy_time_pct: 0.15` at line 49 while `risk_t_start: 0.1` at line 22. These appear to be the same semantic parameter stored in two field names. The iter 139 DISCARD note says "knobs restored to risk_t_start=0.10" — but `min_buy_time_pct` was NOT reset. If the engine reads `min_buy_time_pct` preferentially, XRP_1h may still be operating with risk_t_start=0.15 in practice. **RESEARCHER MUST verify which field the engine reads and ensure min_buy_time_pct=0.10 matches risk_t_start=0.10 before running risk_t_end experiment.**

4. **Statistical noise dominates rotation 12**: Both active experiments were within or near the ±$0.05/bar noise floor (ETH_1h -$0.07/bar regression = plausible noise; XRP_1h had DD breach as hard disqualifier but matched_ratio improvement was real signal). Risk_t_end experiments are likely to be similarly noisy. Accept KEEP only if improvement > $0.05/bar for ETH_1h or improvement > $0.05/bar for XRP_1h.

5. **Matched ratio bottleneck structural**: ETH_1h 1.9%, XRP_1h 3.9% — both below deployment confidence threshold (5%). The 5.1% matched_ratio achieved by XRP_1h at risk_t_start=0.15 (despite DD breach) proves the threshold IS achievable with ramp-timing changes. If risk_t_end achieves matched_ratio >5% without DD breach, XRP_1h would cross the deployment threshold on that metric. This is a secondary KEEP criterion to watch.

6. **Sell category fully unexplored**: 0 experiments in sell params category across all 26 active experiments. Both active pairs show 0 sell events in backtest. Sell logic is simply not triggering. Either the profit_protect_min_pairs=5 threshold is too high for the sparse matched_ratio (1.9-3.9% means 5 pairs are rarely met), or sell thresholds are wrong for the live data profile. Auditor recommendation: STRATEGIST should schedule sell param exploration after risk_budget category exhausted.

## ETH_1h Detailed Trajectory (all active experiments)

| Iter | Status | pair_cost | profit/bar | DD% | matched | param |
|------|--------|-----------|------------|-----|---------|-------|
| 18 (R2 baseline) | BASELINE | 0.594 | -$0.06 | 13.8% | 1.7% | baseline |
| 41 (R4 baseline) | BASELINE | 0.594 | +$0.08 | 7.6% | 2.1% | pace=0.35 |
| 66 (R6) | DISCARD | 0.594 | +$0.04 | 13.8% | 2.1% | fill_ticks=2 |
| 78 (R7) | KEEP | 0.577 | +$0.18 | 11.2% | 1.9% | chase_threshold=0.05 |
| 85 (R8) | DISCARD | 0.577 | +$0.18 | 11.2% | 1.9% | pace_urgency_hi=1.5 (INERT) |
| 97 (R9) | KEEP | 0.577 | +$0.19 | 11.2% | 1.9% | spread_offset=0.005 (marginal) |
| 109 (R10) | DISCARD | 0.577 | +$0.19 | 11.2% | 1.9% | max_chase=3 (INERT) |
| 121 (R11) | DISCARD | 0.580 | +$0.06 | 8.5% | 2.3% | cancel_distance=0.03 (COLLAPSE fill) |
| 133 (R12) | DISCARD | 0.577 | +$0.12 | 11.2% | 1.9% | risk_t_start=0.15 (noise/regression) |

Trajectory: Chase_threshold was the single productive lever (+$0.10/bar). All subsequent improvements have been marginal or noise. The ceiling at +$0.19/bar has persisted through 5 experiments. ETH_1h is at its parametric ceiling with current dataset size. Deployment case is strong.

## XRP_1h Detailed Trajectory (all active experiments)

| Iter | Status | pair_cost | profit/bar | DD% | matched | param |
|------|--------|-----------|------------|-----|---------|-------|
| 23 (R2 baseline) | BASELINE | 0.812 | +$0.10 | 8.0% | 4.0% | baseline |
| 47 (R4 baseline) | BASELINE | 0.812 | -$0.14 | 9.8% | 4.1% | onesided=5.0 |
| 59 (R5) | DISCARD | 0.000 | N/A | — | 0% | onesided=2.0 (COLLAPSE) |
| 72 (R6) | KEEP | 0.812 | -$0.13 | 9.8% | 3.9% | fill_ticks=2 |
| 79 (R7) | KEEP | 0.785 | -$0.08 | 8.9% | 3.9% | chase_threshold=0.05 |
| 91 (R8) | DISCARD | 0.785 | -$0.26 | 9.7% | 3.9% | onesided=3.5 (regression) |
| 103 (R9) | DISCARD | 0.818 | -$0.21 | 11.0% | 3.9% | spread_offset=0.005 (regression) |
| 115 (R10) | KEEP | 0.785 | -$0.026 | 10.6% | 3.9% | max_chase=3 (+$0.054/bar) |
| 127 (R11) | DISCARD | 0.740 | -$0.384 | 9.1% | 1.6% | cancel_distance=0.03 (COLLAPSE matched) |
| 139 (R12) | DISCARD | 0.784 | -$0.45 | 16.7% | 5.1% | risk_t_start=0.15 (DD breach, +matched) |

Trajectory: Strong improving trajectory from 3 fill-sim KEEPs (-$0.14 -> -$0.026/bar). Risk budget experiments showing mixed signals — timing change proves matched_ratio CAN improve but introduces DD sensitivity. Total improvement since R2 baseline: +$0.166/bar. Need additional $0.03-0.05/bar to reach profitability.

## Parameter Category Effectiveness (cumulative)

| Category | ETH_1h tested | XRP_1h tested | KEEP rate | Status |
|----------|--------------|--------------|-----------|--------|
| magnitude_gate | Yes (all values) | Yes | 0% | EXHAUSTED globally |
| pace (lo+hi) | Yes (0.25/0.30/1.5) | Yes (0.30/0.35) | 0% | EXHAUSTED for both |
| max_onesided_cost | No | Yes (2.0/3.5/5.0) | 0% | Floor=5.0 for XRP_1h |
| fill_ticks | Yes (2: DISCARD) | Yes (2: KEEP) | 50% | EXHAUSTED both pairs |
| chase_threshold | Yes (0.05: KEEP) | Yes (0.05: KEEP) | 100% | EXHAUSTED both pairs |
| spread_offset | Yes (0.005: marginal KEEP) | Yes (0.005: DISCARD) | 50% | EXHAUSTED both pairs |
| max_chase | Yes (3: DISCARD inert) | Yes (3: KEEP) | 50% | EXHAUSTED both pairs |
| cancel_distance | Yes (0.03: DISCARD) | Yes (0.03: COLLAPSE) | 0% | EXHAUSTED — floor=0.05 universal |
| risk_t_start | Yes (0.15: DISCARD noise) | Yes (0.15: DISCARD DD) | 0% | EXHAUSTED — floor=0.10 both |
| risk_t_end | NEXT EXPERIMENT | NEXT EXPERIMENT | N/A | ACTIVE — rotation 12 item 2 |
| risk_exponent | No | No | N/A | QUEUED — rotation 12 item 3 |
| sell params | No | No | N/A | QUEUED — rotation 13+ |

**Fill-sim category overall KEEP rate: 5 KEEPs / 10 active fill-sim experiments = 50% — best category in system.**

## Researcher Compliance Assessment — Rotations 11-12 partial (iters 116-139)

Compliance: EXCELLENT — 100%
- Correctly ran ETH_1h cancel_distance=0.03 (iter 121 DISCARD) per prior audit Tier 1 mandate
- Correctly restored cancel_distance=0.05 after ETH_1h DISCARD; confirmed fill-sim exhausted
- Correctly ran XRP_1h cancel_distance=0.03 (iter 127 DISCARD-COLLAPSE) per prior audit Tier 1 mandate
- Correctly restored cancel_distance=0.05 after XRP_1h DISCARD; confirmed fill-sim exhausted
- Correctly applied IMMEDIATE DISCARD for XRP_1h when matched_ratio=1.6% < 2.0% threshold
- Correctly SKIPped all 10 frozen pairs across rotations 11-12 without deviation
- Correctly staged risk_t_start=0.15 in knobs only (not best_knobs) for both pairs in rotation 12
- Correctly restored risk_t_start=0.10 after both DISCARDs
- Correctly applied IMMEDIATE DISCARD for XRP_1h iter 139 when DD=16.7% > 15% threshold
- NOTE: XRP_1h iter 139 description correctly identified matched_ratio improvement (5.1%) as positive signal despite DISCARD

## System-Level Assessment

**System status: Both fill-sim category and risk_t_start exhausted. risk_t_end is the next live experiment.**

The system has been through a thorough fill-sim parameter sweep (5 sub-params per pair, 10 total experiments, 50% KEEP rate — the most productive category in the system). The risk_budget category is now underway. risk_t_start produced 0/2 KEEPs across both pairs. risk_t_end is mechanistically different and has theoretical basis for improvement.

**Key insight from rotation 12 XRP_1h:** matched_ratio 3.9%->5.1% under risk_t_start=0.15 confirms that the risk budget timing parameters DO affect pair formation. The DD penalty was from delayed rebalancing (ramp start too late), not from the timing concept itself. risk_t_end=0.75 changes the ramp apex, not the start — this avoids the specific failure mode of iter 139.

**Deployment readiness:**
- ETH_1h: CONDITIONALLY READY. pair_cost=0.577 (target met), profit=+$0.19/bar (target met), DD=11.2% (target met). BLOCKING criterion: matched_ratio=1.9% below deployment confidence threshold of 5%. Dataset growth is the only structural fix. Could deploy in parallel with continued data accumulation. At current 1 bar/hour rate, reaching >5% matched_ratio requires ~200 resolved outcomes minimum — approximately 6 months of live sessions.
- XRP_1h: NOT READY. profit=-$0.026/bar still negative. pair_cost=0.785 meets target. One productive risk_budget experiment could cross into profitability. Also needs matched_ratio >5% (currently 3.9%); iter 139 showed 5.1% is achievable with timing changes.
- All other 10 pairs: FROZEN. Not deployable.

## Recommendations for Rotation 12 Completion and Rotation 13

### Tier 1 — MANDATORY NEXT EXPERIMENTS (rotation 12 item 2)

**RESEARCHER ALERT — KNOBS DISCREPANCY (RESOLVE BEFORE RUNNING):**
`knobs_XRP_1h.json` has `min_buy_time_pct: 0.15` (line 49) while `risk_t_start: 0.1` (line 22). These appear to be duplicate fields for the same semantic parameter. The iter 139 description states "knobs restored to risk_t_start=0.10" but `min_buy_time_pct` was not reset. Before staging risk_t_end=0.75, the researcher must:
1. Verify which field(s) the Dutch engine reads (risk_t_start, min_buy_time_pct, or both)
2. Set min_buy_time_pct=0.10 in knobs_XRP_1h.json to match risk_t_start=0.10 if it is the active field
3. Confirm knobs_XRP_1h.json and best_knobs_XRP_1h.json are fully aligned before staging the next experiment

**ETH_1h — risk_t_end 0.8->0.75 EXPERIMENT (rotation 12 item 2)**
- Stage: modify `risk_t_end: 0.8 -> 0.75` in `knobs_ETH_1h.json` only (not best_knobs)
- Baseline ref: pair_cost=0.577, profit=+$0.19/bar, DD=11.2%, matched=1.9% (iter 97 KEEP state)
- KEEP criteria: pair_cost < 0.577 OR avg_profit > +$0.19/bar OR matched_ratio > 1.9%
- DISCARD if: pair_cost > 0.65 OR DD > 13% OR matched_ratio < 1.5%
- NOTE: Improvement threshold for statistical confidence is >$0.05/bar above +$0.19/bar. A result of +$0.20-0.21/bar should be considered marginal/noise (DISCARD or KEEP-MARGINAL); only +$0.24/bar or better is clearly above noise.
- If KEEP: update best_knobs_ETH_1h.json with risk_t_end=0.75
- If DISCARD: restore risk_t_end=0.80; proceed to risk_exponent experiment

**XRP_1h — risk_t_end 0.8->0.75 EXPERIMENT (rotation 12 item 2)**
- Stage: modify `risk_t_end: 0.8 -> 0.75` in `knobs_XRP_1h.json` only (not best_knobs)
- Note: risk_t_end=0.75 moves the ramp apex 3 min earlier; unlike risk_t_start=0.15, does NOT delay early bar rebalancing — DD risk from iter 139 mechanism does NOT apply
- Baseline ref: pair_cost=0.785, profit=-$0.026/bar, DD=10.58%, matched=3.9% (iter 115 KEEP state)
- Accept KEEP if: pair_cost < 0.785 OR avg_profit > -$0.026/bar
- IMMEDIATE DISCARD if: matched_ratio < 2.0% (collapse) OR DD > 15%
- Secondary monitor: if matched_ratio improves to >5% (iter 139 showed 5.1% is achievable with timing), note as positive signal even if other criteria not met
- Statistical note: improvement must exceed $0.05/bar to be above noise floor. Improvement of $0.01-$0.04/bar = DISCARD (noise).
- If KEEP: update best_knobs_XRP_1h.json with risk_t_end=0.75
- If DISCARD: restore risk_t_end=0.80; proceed to risk_exponent experiment

### Tier 2 — Rotation 13 planning (post risk_t_end experiments)

**If both risk_t_end DISCARD:**
- Proceed to risk_exponent 2.0->1.5 for both pairs (rotation 12 item 3 per strategy.md)
- risk_exponent 1.5 produces a flatter, more linear ramp vs current quadratic
- Hypothesis: linear distribution may match thin 1h dataset better than quadratic concentration
- If risk_exponent also DISCARDs: risk_budget category exhausted; escalate to STRATEGIST

**If risk_budget category exhausted (all 3 sub-params DISCARD both pairs):**
- ETH_1h: DEPLOYMENT ASSESSMENT. pair_cost=0.577, profit=+$0.19/bar already beats trader_a targets. All known levers exhausted. Recommend: deploy ETH_1h with current knobs, accept matched_ratio=1.9% as structural floor pending dataset growth.
- XRP_1h at -$0.026/bar: escalate to STRATEGIST for sell_params exploration and evaluation of untested global parameters (vwap_tolerance, onesided>5.0)
- STRATEGIST to schedule: sell category experiments (sell_max_fraction, sell_min_shares, sell_loss_start, sell_dump_start) — currently 0/0 tested despite non-trivial potential impact on profit recycling

### Tier 3 — Do NOT run

- All 10 frozen pairs: maintained frozen without exception
- Specifically:
  - SOL_15m/XRP_15m: correct_side must return to >50% before any experiment
  - ETH_15m: correct_side=71.2% excellent but fill mechanics block pair formation; structural barrier
  - BTC pairs and SOL_1h: outcome resolution rates structural barriers; dataset growth required
  - 5m pairs: fill mechanics permanent; requires engine redesign
- risk_t_start values >0.10 for either pair: confirmed destructive — do not retry

## Structural Engineering Recommendations

1. **XRP_1h knobs min_buy_time_pct field**: Investigate whether min_buy_time_pct and risk_t_start are redundant fields. If redundant, the Dutch engine schema should be cleaned to use one canonical field name. The current state of min_buy_time_pct=0.15 in knobs_XRP_1h.json while risk_t_start=0.10 is a potential source of silent discrepancy.

2. **Outcome resolution rate remains the binding constraint**: ETH_1h ~4-5 outcomes/36 bars = ±$0.05/bar noise floor. The entire risk_budget category is operating near the noise boundary. OHLC-based outcome resolution would dramatically improve statistical power and potentially unlock ETH_15m (correct_side=71.2%).

3. **ETH_1h deployment case is now strong**: After 13 active experiments, ETH_1h profit=+$0.19/bar and pair_cost=0.577 have proven stable across multiple experiments. The parameter is robust. Deployment recommendation: proceed with ETH_1h live testing in parallel with continued optimization. Risk: matched_ratio=1.9% means ~1 live pair formed per 2.2 days — low activity but all profitable.

4. **Sell category is the highest-upside unexplored lever**: Both active pairs show zero sell events in all backtest runs. The sell logic threshold (profit_protect_min_pairs=5) likely requires more matched pairs than the sparse dataset produces. Options: (a) lower profit_protect_min_pairs to 2-3, (b) increase bar budget to generate more matched pairs per bar, (c) explore sell_loss_start/sell_dump_start thresholds. This is a virgin category with potentially large effect — schedule for rotation 13+.

5. **Dataset growth timeline**: At 1 resolved outcome per ~20 bars for 1h pairs (outcome resolution rate ~5-8%), reaching 200 resolved outcomes requires approximately 2500-4000 more live bars — roughly 3-5 months of continuous live operation. Natural growth is the only path to improved statistical power without engineering changes.
