# Dutch Audit Report
After iteration 115 (2026-03-27T09:00:00Z)

## Directives

- FREEZE BTC_5m — PERMANENT (maintained): fill mechanics structural (P=5.6%), diagnostic iter 60 confirms no lever can fix this
- FREEZE BTC_15m — MAINTAINED: 3 consecutive zero-pair baselines; outcome sparsity structural (7.9%)
- FREEZE BTC_1h — MAINTAINED: extreme sparsity (2.9%); gate series exhausted
- FREEZE ETH_5m — MAINTAINED: DD=28.7% near 30% kill threshold; fill mechanics structural (P=5.8%); 3 consecutive zero-pair baselines
- FREEZE ETH_15m — MAINTAINED: gate series exhausted R4 (iters 5/17/40 all zero pairs); outcome sparsity structural (9.9%); strong latent signal (correct_side=71.2%) but structurally blocked
- FREEZE SOL_5m — MAINTAINED: 3 consecutive zero-pair runs; fill mechanics structural (P=4.2%); DD=23.2% elevated
- FREEZE SOL_15m — MAINTAINED: correct_side=45.5% (both measurements below 50%); directionally wrong; resume only when correct_side >50%
- FREEZE SOL_1h — MAINTAINED: 3 consecutive zero-pair baselines; outcome sparsity structural (8.6%)
- FREEZE XRP_5m — PERMANENT (maintained): structural fill_rate=15.6% floor; zero pairs at all tested gates
- FREEZE XRP_15m — MAINTAINED: correct_side declined monotonically 53.7%->50.0%->49.2%; gate series exhausted; confirmed degrading
- CONTINUE ETH_1h — ACTIVE: pair_cost=0.577 well below target; profit=+$0.19/bar positive; fill-sim category nearly exhausted; next lever cancel_distance 0.05->0.03; this is the system's single profitable pair
- CONTINUE XRP_1h — ACTIVE: pair_cost=0.785 meets target; profit improved -$0.08->-$0.026/bar after max_chase=3 KEEP; fill-sim nearly exhausted; next lever cancel_distance 0.05->0.03; approaching profitability

## Per-Pair Assessment

| Pair | Best PairCost | MatchedRatio | CorrectSide | MaxDD% | KEEP Rate (R6-R10) | Trajectory | Action |
|------|--------------|--------------|-------------|--------|-------------------|------------|--------|
| BTC_5m | 0.000 | 0% | 62.9% | 23.4% | 0/0 (frozen) | BLOCKED PERMANENT — fill mechanics (P=5.6%) | FREEZE PERMANENT |
| BTC_15m | 0.000 | 0% | 60.7% | 12.4% | 0/0 (frozen) | BLOCKED — outcome sparsity (7.9%) | FREEZE |
| BTC_1h | 0.000 | 0% | 70.0% | 3.9% | 0/0 (frozen) | BLOCKED — extreme sparsity (2.9%) | FREEZE |
| ETH_5m | 0.000 | 0% | 52.9% | 28.7% | 0/0 (frozen) | BLOCKED — fill mechanics (P=5.8%) + DD risk | FREEZE |
| ETH_15m | 0.000 | 0% | 71.2% | 7.1% | 0/0 (frozen) | BLOCKED — outcome sparsity (9.9%); strongest latent signal | FREEZE |
| ETH_1h | 0.577 (iter 78) | 1.9% | 67.7% | 11.2% | 3/5 active = 60% | STABLE: profit improving slowly +$0.18->+$0.19/bar (R9 KEEP marginal, R10 max_chase INERT) | CONTINUE |
| SOL_5m | 0.000 | 0% | 56.2% | 23.2% | 0/0 (frozen) | BLOCKED PERMANENT — fill mechanics (P=4.2%) | FREEZE |
| SOL_15m | 0.567* | 0.3% | 45.5% | 19.8% | 0/0 (frozen) | FROZEN — directionally wrong | FREEZE |
| SOL_1h | 0.000 | 0% | 54.5% | 8.3% | 0/0 (frozen) | BLOCKED — outcome sparsity (8.6%) | FREEZE |
| XRP_5m | N/A | 0% | 57.8% | 13.4% | 0/0 (frozen) | PERMANENT FREEZE | FREEZE PERMANENT |
| XRP_15m | 0.950 | 0.7% | 49.2% | 20.5% | 0/0 (frozen) | DEGRADING — correct_side declining | FREEZE |
| XRP_1h | 0.785 (iter 79) | 3.9% | 64.3% | 10.6% | 3/5 active = 60% | IMPROVING: profit -$0.14->-$0.08->-$0.026/bar trajectory (3 improvements since R6) | CONTINUE |

*SOL_15m: artificially low pair_cost (near-zero pairs)

## trader_a Gap Analysis

| Pair | PairCost | Target | Cost Gap | Profit/bar | DD | Status | ETA |
|------|----------|--------|----------|------------|-----|--------|-----|
| ETH_1h | 0.577 | <0.85 | -0.273 (BEATS by 32%) | +$0.19 | 11.2% | PROFITABLE — benchmark cost achieved; marginal fill-sim improvements remaining | 1-2 experiments before structural floor |
| XRP_1h | 0.785 | <0.85 | -0.065 (BEATS by 7.6%) | -$0.026 | 10.6% | IMPROVING — cost meets target; profit approaching zero; 1 more KEEP could reach profitability | 1-2 experiments before structural floor |
| All others | 0.000 or N/A | <0.85 | N/A | N/A | various | FROZEN — structural | Unblockable without engineering |

## Trajectory Analysis (iters 91-115, since last audit at iter 90)

### Rotation 8 completion (iter 91): 0 KEEPs from 1 active experiment

- Iter 91 XRP_1h max_onesided_cost 5.0->3.5 DISCARD: pair_cost stable 0.785, profit REGRESSED -0.08->-0.26/bar. No collapse (matched_ratio=3.9% stable). Onesided cap at 3.5 reduces spending headroom without collapsing — confirms floor at 5.0.

### Rotation 9 (iters 92-103): 1 KEEP from 2 active experiments (50%)

- Iters 92-96: 5 FROZEN SKIPs (BTC_5m through ETH_15m) — all maintained
- Iter 97 ETH_1h spread_offset 0.01->0.005 KEEP: profit +$0.18->+$0.19/bar (+$0.01/bar marginal). pair_cost stable at 0.577. This KEEP is in the noise floor region — only 4-5 resolved outcomes means $0.01/bar improvement = ~$0.04 total profit difference.
- Iters 98-102: 5 FROZEN SKIPs (SOL_5m through XRP_15m)
- Iter 103 XRP_1h spread_offset 0.01->0.005 DISCARD: pair_cost REGRESSED 0.818 (+0.033), profit -0.21/bar (-0.13 regression), fill_rate -3.3pp. Confirms spread_offset floor at 0.01 for XRP_1h (unlike ETH_1h where tight offset is marginal benefit). Asset-specific confirmed: wider natural spread in XRP requires more offset headroom.

### Rotation 10 (iters 104-115): 1 KEEP from 2 active experiments (50%)

- Iters 104-108: 5 FROZEN SKIPs — all maintained
- Iter 109 ETH_1h max_chase 2->3 DISCARD: ALL metrics IDENTICAL to iter 97 KEEP state. max_chase=3 completely inert — fill_rate already 86% means orders fill on first/second attempt; third attempt never triggers. Confirms max_chase floor at 2 for ETH_1h.
- Iters 110-114: 5 FROZEN SKIPs — all maintained
- Iter 115 XRP_1h max_chase 2->3 KEEP: pair_cost=0.785 stable, profit -$0.08->-$0.026/bar (+67.5% improvement), fill_rate 69.0%->74.3% (+5.3pp). max_chase=3 effective on XRP_1h where fill_rate was lower (69% vs ETH_1h 86%) — extra chase attempt finding fills after brief adverse XRP price moves. This is a genuine improvement, not noise: fill_rate increase (+5.3pp) mechanistically confirms the extra chase is triggering.

### KEEP Rate Summary (since last audit at iter 90)

| Rotation | Active Experiments | KEEPs | KEEP Rate |
|----------|--------------------|-------|-----------|
| R8 completion (iter 91) | 1 | 0 | 0% |
| R9 (iters 92-103) | 2 | 1 | 50% |
| R10 (iters 104-115) | 2 | 1 | 50% |
| **Total R8-R10 (post-audit 90)** | **5** | **2** | **40%** |
| **Cumulative (all rotations)** | **~20 non-baseline active** | **5** | **25%** |

## ETH_1h Detailed Trajectory (all KEEPs)

| Iter | Status | pair_cost | profit/bar | DD% | param |
|------|--------|-----------|------------|-----|-------|
| 18 (R2 baseline) | BASELINE | 0.594 | -$0.06 | 13.8% | baseline |
| 41 (R4 baseline) | BASELINE | 0.594 | +$0.08 | 7.6% | pace=0.35 |
| 78 (R7) | KEEP | 0.577 | +$0.18 | 11.2% | chase_threshold=0.05 |
| 85 (R8) | DISCARD | 0.577 | +$0.18 | 11.2% | pace_urgency_hi=1.5 (INERT) |
| 97 (R9) | KEEP | 0.577 | +$0.19 | 11.2% | spread_offset=0.005 (marginal) |
| 109 (R10) | DISCARD | 0.577 | +$0.19 | 11.2% | max_chase=3 (INERT) |

Assessment: ETH_1h is profitable at +$0.19/bar with pair_cost=0.577 (trader_a target ACHIEVED). The improvement trajectory has flattened. Two consecutive experiments produced either a marginal KEEP (+$0.01/bar noise) or a DISCARD (INERT). The fill-sim category has 1 remaining lever: cancel_distance 0.05->0.03. After cancel_distance, all known levers are exhausted. ETH_1h may be at or near its parametric ceiling given the current dataset size (36 bars, 4-5 resolved outcomes).

**ETH_1h fill-sim lever status:**
| Lever | Status |
|-------|--------|
| fill_ticks | 1 (DISCARD at 2; iter 66) — floor confirmed |
| chase_threshold | 0.05 (KEEP iter 78) — best result ever; floor confirmed |
| spread_offset | 0.005 (KEEP iter 97 marginal) — tested; floor confirmed |
| max_chase | 2 (DISCARD at 3; iter 109 inert) — floor confirmed |
| cancel_distance | 0.05 (UNTESTED) — NEXT experiment |

## XRP_1h Detailed Trajectory (all KEEPs)

| Iter | Status | pair_cost | profit/bar | DD% | param |
|------|--------|-----------|------------|-----|-------|
| 23 (R2 baseline) | BASELINE | 0.812 | +$0.10 | 8.0% | baseline |
| 47 (R4 baseline) | BASELINE | 0.812 | -$0.14 | 9.8% | onesided=5.0 |
| 72 (R6) | KEEP | 0.812 | -$0.13 | 9.8% | fill_ticks=2 (+$0.01/bar) |
| 79 (R7) | KEEP | 0.785 | -$0.08 | 8.9% | chase_threshold=0.05 (-3.3% cost, +$0.05/bar) |
| 91 (R8) | DISCARD | 0.785 | -$0.26 | 9.7% | onesided=3.5 (regression) |
| 103 (R9) | DISCARD | 0.818 | -$0.21 | 11.0% | spread_offset=0.005 (regression) |
| 115 (R10) | KEEP | 0.785 | -$0.026 | 10.6% | max_chase=3 (+$0.054/bar, fill_rate +5.3pp) |

Assessment: XRP_1h shows genuine continuous improvement with 3 KEEPs in 8 active experiments (37.5%). Profit trajectory: -$0.14 -> -$0.13 -> -$0.08 -> -$0.026/bar. At this rate (+$0.05-$0.054/bar per productive KEEP), one more KEEP would push profit positive. The pair has clear responsiveness to fill-sim tuning (fill_ticks=2, chase_threshold=0.05, max_chase=3 all contributed). cancel_distance is the last untested fill-sim lever and is the most promising remaining option.

**XRP_1h fill-sim lever status:**
| Lever | Status |
|-------|--------|
| fill_ticks | 2 (KEEP iter 72) — best result; floor confirmed at 1 |
| chase_threshold | 0.05 (KEEP iter 79) — best result; floor confirmed |
| spread_offset | 0.01 (DISCARD at 0.005; iter 103) — floor confirmed at 0.01 |
| max_chase | 3 (KEEP iter 115) — best result to date |
| cancel_distance | 0.05 (UNTESTED) — NEXT experiment |

## Parameter Category Effectiveness (cumulative)

| Category | ETH_1h tested | XRP_1h tested | KEEP rate | Status |
|----------|--------------|--------------|-----------|--------|
| magnitude_gate | Yes (0.08/0.04/0.0) | Yes | 0% | EXHAUSTED globally |
| pace (lo+hi) | Yes (0.25/0.30/1.5) | Yes (0.30/0.35) | 0% | EXHAUSTED for ETH_1h; floor=0.35 for XRP_1h |
| max_onesided_cost | No | Yes (2.0 collapse, 3.5 regression, 5.0 stable) | 0% | Floor=5.0 confirmed for XRP_1h |
| fill_ticks | Yes (2: DISCARD) | Yes (2: KEEP) | 50% | DIFFERENTIAL — ETH benefits from 1; XRP benefits from 2 |
| chase_threshold | Yes (0.05: KEEP) | Yes (0.05: KEEP) | 100% | BEST CATEGORY — both pairs improved |
| spread_offset | Yes (0.005: marginal KEEP) | Yes (0.005: DISCARD; floor=0.01) | 50% | ASSET-SPECIFIC — ETH tolerates tight; XRP requires 0.01+ |
| max_chase | Yes (3: DISCARD inert) | Yes (3: KEEP) | 50% | DIFFERENTIAL — ETH fill_rate too high for 3rd attempt; XRP benefits |
| cancel_distance | UNTESTED | UNTESTED | N/A | NEXT EXPERIMENT BOTH PAIRS |
| risk_budget | No | No | N/A | Low priority |
| conviction | No | No | N/A | Low priority (market_start GLOBAL BLACKLIST) |

## Risk Flags

1. **ETH_1h statistical noise ceiling**: All improvements since iter 78 are marginal (+$0.01/bar or INERT). On 4-5 resolved outcomes, $0.01/bar = ~$0.05 total difference — pure noise. The genuine, mechanistically-confirmed improvement was chase_threshold=0.05 (iter 78, +$0.10/bar). Subsequent changes are within noise floor. cancel_distance is the last lever; if also INERT, ETH_1h is at its parametric ceiling for the current dataset.

2. **XRP_1h improving but statistically thin**: max_chase=3 KEEP has mechanistic support (fill_rate +5.3pp confirms the 3rd attempt is triggering). However the underlying dataset is 37 bars, ~4-5 outcomes. Profit -$0.026/bar is near zero. The next KEEP could easily tip into profitability or remain marginal due to outcome volatility.

3. **Matched ratio bottleneck is permanent at current dataset size**: ETH_1h 1.9%, XRP_1h 3.9% — statistically insufficient for deployment confidence. Target is >5%. At 1 bar/hour for 1h pairs, reaching >5% matched_ratio requires approximately 6 additional months of live data (minimum 200+ resolved outcomes). No parameter tweak can fix this.

4. **Fill-sim category nearly exhausted for both pairs**: After cancel_distance, all known levers in the fill-sim category will have been tested. At that point, both pairs enter structural floors unless a new lever category is identified or the dataset grows substantially.

5. **ETH_1h knobs drift detected**: knobs_ETH_1h.json shows `spread_offset: 0.0` at the top level but `fill_simulator.spread_offset: 0.005`. The top-level spread_offset is a global parameter while fill_simulator.spread_offset is the fill simulator sub-parameter. This should not cause issues (the fill_simulator values are the relevant ones), but the researcher must confirm which field the backtest system reads when staging cancel_distance.

6. **XRP_1h knobs and best_knobs now fully aligned on max_chase=3**: Both files show max_chase=3 (confirmed KEEP iter 115). The best_knobs was updated by the researcher. This is correct state.

## Recommendations for Rotation 11 (iters 116-127 estimate)

### Tier 1 — Rotation 11 (MANDATORY NEXT EXPERIMENTS)

**ETH_1h — cancel_distance 0.05->0.03 (tighter cancellation)**
- Stage: modify fill_simulator.cancel_distance 0.05->0.03 in knobs_ETH_1h.json only (not best_knobs)
- Hypothesis: shorter cancel distance keeps limit orders near midpoint longer before cancelling and re-quoting; may improve matched_ratio or reduce pair_cost by keeping better-priced orders alive longer
- Baseline ref: pair_cost=0.577, profit=+$0.19/bar, DD=11.2%, matched_ratio=1.9% (iter 97 KEEP state)
- KEEP criteria: matched_ratio > 1.9% OR avg_profit > +$0.19/bar OR pair_cost < 0.577
- DISCARD if: pair_cost > 0.65 OR DD > 13% OR matched_ratio < 1.5%
- If KEEP: update best_knobs_ETH_1h.json with cancel_distance=0.03
- If DISCARD: restore cancel_distance=0.05; declare ETH_1h fill-sim EXHAUSTED
- NOTE: This is the FINAL fill-sim lever for ETH_1h. If DISCARD, all known parameter categories are exhausted.

**XRP_1h — cancel_distance 0.05->0.03 (tighter cancellation)**
- Stage: modify fill_simulator.cancel_distance 0.05->0.03 in knobs_XRP_1h.json only (not best_knobs)
- Hypothesis: same as ETH_1h; XRP_1h fill_rate at 74.3% (lower than ETH_1h 86%) means there is more room to improve fill quality by keeping orders alive longer; may push profit from -$0.026 to positive
- Baseline ref: pair_cost=0.785, profit=-$0.026/bar, DD=10.6%, matched_ratio=3.9% (iter 115 KEEP state)
- KEEP criteria: pair_cost < 0.785 OR avg_profit > -$0.026/bar
- IMMEDIATE DISCARD if: matched_ratio < 2.0% (collapse detection) OR DD > 15%
- If KEEP: update best_knobs_XRP_1h.json with cancel_distance=0.03; XRP_1h may reach profitability
- If DISCARD: restore cancel_distance=0.05; declare XRP_1h fill-sim EXHAUSTED
- NOTE: This is the FINAL fill-sim lever for XRP_1h. A KEEP here could push profit to +$0 or better.

### Tier 2 — Post fill-sim exhaustion assessment

If both ETH_1h and XRP_1h cancel_distance experiments DISCARD, the auditor must convene for a structural floor assessment. At that point:

1. **ETH_1h structural floor confirmed**: All fill-sim levers exhausted (fill_ticks=1 BEST, chase_threshold=0.05 KEEP, spread_offset=0.005 marginal KEEP, max_chase=2 INERT, cancel_distance=0.05 if DISCARD). pair_cost=0.577 and profit=+$0.19/bar are the parametric ceiling for the current dataset. ETH_1h is DEPLOYABLE as-is pending matched_ratio >5% (deployment criterion — not yet met).

2. **XRP_1h structural floor confirmed if DISCARD**: profit=-$0.026/bar is approaching but has not crossed zero. At structural floor: the only improvement path is dataset growth (1 bar/hour, 6 months to 500+ outcomes) or a new lever category. Escalate to STRATEGIST to identify any untested global parameters (onesided>5 has not been tested — currently at floor 5.0, potentially try higher to relax constraint; also vwap_tolerance, bar_budget).

3. **Engineering escalation unchanged from prior audit**:
   - Outcome resolution rate: current 8-14% for 1h pairs is the binding long-term constraint. OHLC-based outcome resolution would unfreeze ETH_15m (correct_side=71.2%), BTC_1h, SOL_1h.
   - Fill mechanics for 5m pairs: permanent structural block. Requires engine redesign (multi-bar window or market orders for small sizes).
   - Matched ratio minimum: >5% needed for deployment confidence. ETH_1h at 1.9%, XRP_1h at 3.9% — dataset growth is the only fix.

### Tier 3 — Do NOT run in rotation 11

- All 10 frozen pairs: maintained frozen without exception
- Specifically: do NOT attempt any frozen pair even if dataset grew since last audit
  - SOL_15m/XRP_15m: correct_side must return to >50% before any experiment
  - ETH_15m: correct_side=71.2% excellent but fill mechanics block pair formation structurally
  - BTC_1h/SOL_1h: outcome resolution <3-9% is structural barrier
  - 5m pairs: fill mechanics permanent (structural, requires engine redesign)

## Knobs State Audit

**ETH_1h knobs state (post iter 115):**
- knobs_ETH_1h.json: fill_ticks=1, chase_threshold=0.05, spread_offset=0.005, max_chase=2, cancel_distance=0.05
- best_knobs_ETH_1h.json: fill_ticks=1, chase_threshold=0.05, spread_offset=0.005, max_chase=2, cancel_distance=0.05
- State: ALIGNED (no staged experiment). Next experiment: stage cancel_distance=0.03 in knobs_ETH_1h.json only.
- NOTE: top-level spread_offset=0.0 in both files (correct — this is a different global parameter; fill_simulator.spread_offset=0.005 is the relevant lever and is correctly set).

**XRP_1h knobs state (post iter 115):**
- knobs_XRP_1h.json: fill_ticks=2, chase_threshold=0.05, max_chase=3, spread_offset=0.01, cancel_distance=0.05
- best_knobs_XRP_1h.json: fill_ticks=2, chase_threshold=0.05, max_chase=3, spread_offset=0.01, cancel_distance=0.05
- State: ALIGNED (both updated with max_chase=3 from iter 115 KEEP). Next experiment: stage cancel_distance=0.03 in knobs_XRP_1h.json only.
- CONFIRMED: best_knobs_XRP_1h correctly reflects max_chase=3 (KEEP iter 115).

## Researcher Compliance Assessment — Rotations 8-10 (iters 91-115)

Compliance: EXCELLENT — 100%
- Correctly ran XRP_1h onesided=3.5 (iter 91 DISCARD) per prior audit Tier 1 mandate
- Correctly restored onesided=5.0 after DISCARD; confirmed onesided floor at 5.0
- Correctly ran ETH_1h spread_offset=0.005 (iter 97 KEEP) per prior audit Tier 2 queue; KEEP achieved
- Correctly ran XRP_1h spread_offset=0.005 (iter 103 DISCARD) per strategy rotation-9 queue
- Correctly ran ETH_1h max_chase=3 (iter 109 DISCARD) per strategy rotation-10 queue item 1
- Correctly ran XRP_1h max_chase=3 (iter 115 KEEP) per strategy rotation-10 queue item 2
- Correctly SKIPped all 10 frozen pairs across rotations 8-10 without deviation
- Correctly updated best_knobs_XRP_1h.json with max_chase=3 after iter 115 KEEP

## System-Level Assessment

**System status: Approaching parametric ceiling on both active pairs.**

Rotation 10 completed with KEEP rate 50% (1/2 active experiments). Cumulative KEEP rate since R6 is healthy at 25%. However the improvement magnitudes are declining:

- R6 (fill_ticks=2 XRP): +$0.01/bar improvement
- R7 (chase_threshold=0.05 both): +$0.10/bar ETH, +$0.05/bar XRP — BEST ROTATION
- R8 (onesided+pace): 0 KEEPs
- R9 (spread_offset ETH KEEP marginal, XRP DISCARD): +$0.01/bar improvement
- R10 (max_chase ETH INERT, XRP KEEP): +$0.054/bar XRP — genuinely productive

XRP_1h is showing the steeper improvement curve currently: profit improved from -$0.14/bar baseline to -$0.026/bar current best (81.4% of the way to zero). The max_chase=3 KEEP is mechanistically confirmed by fill_rate +5.3pp. This pair could turn profitable on the next productive experiment.

ETH_1h is stable and profitable at +$0.19/bar. Its improvement has plateaued — two experiments since the last productive KEEP (R7 chase_threshold) have been marginal or inert. cancel_distance is the final lever.

**Deployment readiness assessment:**
- ETH_1h: CONDITIONALLY READY. pair_cost=0.577 (target met), profit=+$0.19/bar (target met), DD=11.2% (target met). BLOCKING criterion: matched_ratio=1.9% is too low for deployment confidence (need >5%). Dataset growth is the only fix. Could deploy in parallel with continued data accumulation.
- XRP_1h: NOT READY. profit=-$0.026/bar still negative (must be >0 before deployment). One productive experiment could change this.
- All other 10 pairs: FROZEN. Not deployable.

**Prognosis for rotation 11:**
- Optimistic: cancel_distance KEEPs for BOTH pairs. ETH_1h confirms floor at cancel_distance=0.03. XRP_1h crosses into profitability. Both pairs enter structural floor assessment in rotation 12.
- Neutral: cancel_distance KEEPs for XRP_1h only (more room to improve given lower fill_rate). ETH_1h DISCARD (already too high fill_rate for cancel_distance to help). XRP_1h approaches profitability.
- Pessimistic: Both cancel_distance experiments DISCARD (INERT). Both pairs fully exhausted. Dataset growth is the only remaining improvement path. Escalate to STRATEGIST for evaluation of non-fill-sim levers (vwap_tolerance, bar_budget increase, onesided>5 for XRP_1h).
