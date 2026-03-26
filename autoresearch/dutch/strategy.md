# Dutch Strategy
Updated: after iteration 36 (2026-03-27T13:00:00Z) — STRATEGIST rotation 3 post-analysis

## Summary

Rotation 3 complete (iters 25-36): 4 BASELINEs + 7 DISCARDs + 1 carried DISCARD from rotation 2 cleanup + 2 SKIPs.
**KEEP rate this rotation: 0/12 = 0%** (all gate=0.0 baselines collapsed; pace series experiments universally ineffective).

**Critical finding from rotation 3:**
- Gate=0.0 fails for all tested pairs in rotation 3: BTC_15m (iter 25), BTC_1h (iter 26), ETH_5m (iter 27), SOL_1h (iter 32)
- BTC_5m rotation 4 gate=0.0 baseline (iter 36): still zero pairs — 4th consecutive failure — gate exhaustion COMPLETE
- **Root cause confirmed: outcome sparsity (not magnitude_gate) is the structural bottleneck for 7 pairs**
- XRP_1h collapse at pace=0.30 (iter 35): floor confirmed at 0.35 — pace series exhausted for XRP_1h
- ETH_1h pace=0.25 undetectable (iter 29): thin dataset makes pace changes invisible
- XRP_15m pace=0.25 undetectable (iter 34): too few pairs (0.72%) to detect pace parameter effects
- ETH_15m pace=0.25 knobs drift (iter 28): confirmed ineffective, restored to 0.35

**Researcher compliance:** COMPLIANT. Correctly skipped XRP_5m and SOL_15m (frozen). Applied risk_ceil fix to BTC_1h before iter 26. Ran gate=0.0 baselines for all blocked pairs per strategy directives. Ran pace experiments for active pairs. Restored knobs after DISCARDs. Pre-staged pace_urgency_lo=0.30 for BTC_5m rotation 4 (iter 36 notes).

---

## AUDITOR FREEZES (active)

- **SOL_15m**: FROZEN — correct_side=45.5% (below 50%). Do NOT run experiments.
- **XRP_5m**: FROZEN (permanent). Skip in all rotations.

## ESCALATION TO AUDITOR (rotation 4 mandatory)

The following pairs have confirmed outcome-sparsity structural blocks. The gate series is fully
exhausted on all of them. Auditor must formally rule on what experiment approach to use next:

- **BTC_5m**: 4 consecutive zero-pair baselines (gate=0.08/0.04/0.02/0.0). 40/420 outcomes (9.5%)
- **BTC_15m**: 3 consecutive zero-pair baselines (gate=0.08/0.04/0.0). 11/139 outcomes (7.9%)
- **BTC_1h**: 3 consecutive zero-pair baselines (gate=0.08/0.04/0.0). 1/34 outcomes (2.9%)
- **ETH_5m**: 3 consecutive zero-pair baselines (gate=0.08/0.04/0.0). 36/414 outcomes (8.7%)
- **SOL_5m**: 3 consecutive zero-pair baselines (gate=0.08/0.04/0.0). 28/407 outcomes (6.9%)
- **SOL_1h**: 3 consecutive zero-pair baselines (gate=0.08/0.04/0.0). 3/35 outcomes (8.6%)

Pending auditor investigation, these pairs should NOT receive further gate or pace experiments.
Candidate directions for auditor to explore: bar_budget reduction, outcome window expansion,
fill_ticks increase, sweep_threshold reduction, or declaring structural dead-end.

---

## BTC_5m (pair_cost=0.000 at gate=0.0, KEEP rate 0% post-RESET)

Iter 36: magnitude_gate=0.0 BASELINE. Zero pairs AGAIN — 4th consecutive gate failure.
40/420 outcomes (9.5% resolution). correct_side=62.9% solid directional signal.
fill_rate=23.1% — limit orders rarely fill in 5m window.
max_dd=23.4% from unmatched inventory accumulation.

**Gate series exhausted** — magnitude_gate=0.08, 0.04, 0.02, 0.0 all confirmed collapse.
Current knobs: magnitude_gate=0.0, max_onesided_cost=2.0, pace_urgency_lo=0.30 (pre-staged by researcher).

**Root cause analysis:** With only 40 resolved outcomes in 420 bars:
- Very few bars qualify as outcome-resolved buys
- Pair formation requires BOTH an up-buy AND a down-buy with resolved outcomes to close
- At 9.5% resolution, the probability of two matching outcomes within the same evaluation
  window is ~0.9%, explaining near-zero matched_ratio
- Gate changes cannot fix this — gate only affects which buys to skip, not outcome resolution

Priority queue for rotation 4:
1. **HOLD** — escalate to auditor for outcome-sparsity investigation. Do NOT run experiments
   until auditor lifts the escalation or provides specific directives.
2. Pre-staged: pace_urgency_lo=0.30 in knobs — keep this for when escalation resolves.
3. When auditor clears: try bar_budget reduction (200->100) to concentrate on resolved windows.
   Hypothesis: smaller bar_budget forces more focus on immediately-resolved predictions.

Blacklist (cumulative): gate=0.02/0.04/0.08/0.0 (all collapse), skip 0.45/0.55,
onesided 2.0->1.5 (COLLAPSE pre-RESET), conviction_market_start (GLOBAL BLACKLIST).

---

## BTC_15m (pair_cost=0.000 at gate=0.0, KEEP rate 0% post-RESET)

Iter 25: gate=0.0 + onesided=2.0 BASELINE. Zero pairs AGAIN — 3rd consecutive.
11/139 outcomes (7.9% resolution). correct_side=60.7% moderate signal.
max_dd=12.4% safe. fill_rate=40.3%.
Current knobs: magnitude_gate=0.0, max_onesided_cost=2.0, pace_urgency_lo=0.35.

Gate series exhausted (0.08, 0.04, 0.0 all fail). Outcome sparsity confirmed structural.

Priority queue for rotation 4:
1. **HOLD** — escalate to auditor. Same outcome-sparsity block as BTC_5m.
2. Do NOT run further gate or pace experiments until auditor reviews.
3. Knobs clean: magnitude_gate=0.0 already set, max_onesided_cost=2.0 correct.

Blacklist (cumulative): gate=0.04 (collapse), skip=0.45 (3x collapse), bar_budget 400,
conviction_market_start (GLOBAL BLACKLIST).

---

## BTC_1h (pair_cost=0.000 at gate=0.0, KEEP rate 0% post-RESET)

Iter 26: risk_ceil=0.15 fix + gate=0.0 BASELINE. Zero pairs AGAIN — 3rd consecutive.
1/34 outcomes (2.9% resolution — extreme). correct_side=70.0% strong signal.
max_dd=3.88% very safe. fill_rate=58.8%.
Current knobs: magnitude_gate=0.0, max_onesided_cost=2.0, pace_urgency_lo=0.45, risk_ceil=0.15.

Gate series exhausted. 1 outcome per 34 bars = virtually impossible to form pairs.
risk_ceil stale knob fixed (0.20->0.15) before iter 26. Confirmed correct.

Priority queue for rotation 4:
1. **HOLD** — escalate to auditor. Extreme outcome sparsity (1/34 = 2.9%).
2. Do NOT run any experiment until auditor directs.
3. Note: pace_urgency_lo=0.45 is high — queued to reduce to 0.35 eventually, but useless
   while zero pairs. Do not change until pair formation is resolved.

Blacklist (cumulative): gate=0.04 (collapse), risk_ceil 0.10/0.20, skip 0.50, onesided 5->3,
conviction_market_start (GLOBAL BLACKLIST).

---

## ETH_5m (pair_cost=0.000 at gate=0.0, KEEP rate 0% post-RESET)

Iter 27: gate=0.0 DISCARD. Zero pairs AGAIN — 3rd consecutive.
36/414 outcomes (8.7% resolution). correct_side=52.9% minimal edge (near random).
max_dd=28.7% DANGEROUS — close to 30% threshold from unmatched inventory.
fill_rate=24.6%. Knobs restored to best_knobs after DISCARD.
Current knobs: magnitude_gate=0.04 (restored from 0.0 — needs fix), max_onesided_cost=1.5,
pace_urgency_lo=0.35.

**KNOBS FIX NEEDED: ETH_5m knobs has no magnitude_gate key (missing entirely). Add magnitude_gate=0.0.**

Gate series exhausted (0.08, 0.04, 0.0 all fail).

CAUTION: max_dd=28.7% is near the 30% kill threshold. The unmatched inventory accumulation
is genuinely dangerous on ETH_5m. If outcome sparsity can't be resolved, this pair should
be considered for deactivation (similar to XRP_5m permanent freeze).

Priority queue for rotation 4:
1. **HOLD** — escalate to auditor. Both outcome sparsity AND dangerous DD risk.
2. KNOBS FIX: add magnitude_gate=0.0 to knobs_ETH_5m.json (key is absent).
3. Auditor should consider whether ETH_5m DD risk warrants a freeze pending investigation.

Blacklist (cumulative): gate=0.04 (collapse), skip 0.60, onesided 1.5->1.0 (COLLAPSE),
conviction_market_start (GLOBAL BLACKLIST).

---

## ETH_15m (pair_cost=0.000 at gate=0.0, KEEP rate 0% post-RESET)

Iter 28: pace=0.25 knobs drift DISCARD. Zero pairs same as iters 5 and 17.
8/139 outcomes (5.8% resolution). correct_side=71.0% strong (2nd highest in system).
avg_profit=+$0.12/bar positive (unmatched inventory). max_dd=7.1% safe.
Knobs restored to best_knobs after DISCARD. Current knobs: magnitude_gate=0.0, pace=0.35,
max_onesided_cost=1.5.

Gate series: 0.08 (iter 5) and 0.04 (iter 17) both failed. Gate=0.0 is in knobs but not
formally baselined for ETH_15m (iter 28 was pace drift, not gate baseline).

**correct_side=71.0% is the 2nd strongest signal in system — high strategic value if pair
formation can be unlocked.**

Priority queue for rotation 4:
1. magnitude_gate=0.0 BASELINE — technically not yet formally baselined for ETH_15m
   in rotation 3 (iter 28 was a pace drift experiment, not a clean gate=0.0 baseline).
   Run gate=0.0 baseline to formally confirm gate exhaustion for ETH_15m.
   Knobs already have magnitude_gate=0.0. Run as baseline.
   If zero pairs: escalate to auditor same as other sparsity-blocked pairs.
2. If gate=0.0 gives non-zero pairs: pace_urgency_lo 0.35->0.30 next.
   ETH_15m has strong signal; pace reduction should improve pair quality if pairs form.
3. HOLD all other experiments.

Blacklist (cumulative): skip above 0.50, onesided above 1.5 or below 1.5 (COLLAPSE at 1.0),
gate=0.04 (collapse), conviction_market_start (GLOBAL BLACKLIST).

---

## ETH_1h (pair_cost=0.594 at gate=0.04, KEEP rate 0% post-RESET)

Iter 29: pace_urgency_lo=0.25 DISCARD. pair_cost=0.5941 IDENTICAL to baseline 0.594 (iter 18).
34 bars, 3 outcomes (8.8% resolution). avg_profit=-$0.05/bar marginal.
Knobs restored to best_knobs. Current knobs: magnitude_gate=0.04, pace=0.35, onesided=2.0.

**Situation:** ETH_1h has pair formation at gate=0.04 (2% matched_ratio) with pair_cost=0.594
which is already well below 0.85 target. But dataset is too thin (34 bars) for pace experiments
to be detectable. The signal is real but the evaluation window is too small.

**KNOBS NOTE:** ETH_1h knobs shows magnitude_gate=0.04 — the strategy queue item was to test
gate=0.0 eventually but pair formation exists at gate=0.04. pace_urgency_lo=0.35 in knobs
(was 0.30 at iter 18 baseline). Check: iter 18 baseline ran with pace=0.30? If so, the
knobs_restore put it back to 0.35 but the working pair_cost was at 0.30. This is a discrepancy.

**Recommendation:** Verify ETH_1h baseline — iter 18 notes say "pace_urgency_lo=0.30 in knobs"
but current knobs shows 0.35. The best_knobs restoration after DISCARD may have reverted to 0.35.
If iter 18's pair_cost=0.594 was at pace=0.30, and current knobs is at 0.35, then 0.35 has not
been baselined. Run a baseline at current knobs (pace=0.35) to establish new reference.

Priority queue for rotation 4:
1. ETH_1h BASELINE at current knobs (pace=0.35, gate=0.04) — to establish clean reference
   after knobs restoration. Compare to iter 18 (pace=0.30, pair_cost=0.594).
2. If baseline shows pair_cost similar to iter 18: pace_urgency_lo 0.35->0.30 experiment.
   Accept KEEP if pair_cost improves >2% vs baseline.
3. max_onesided_cost 5.0->2.0 — actually knobs already shows 2.0. This was already applied
   (baseline iter 18 used onesided=2.0). Confirmed applied.

**KNOBS FIX: magnitude_gate=0.04 in ETH_1h knobs. Queue item calls for gate=0.0 eventually.
For rotation 4, keep gate=0.04 (pair formation active). Stage gate=0.0 as rotation 5 item.**

Blacklist (cumulative): onesided above 5, skip 0.40, risk_ceil 0.20, bar_budget 250/300,
conviction_market_start (GLOBAL BLACKLIST).

---

## SOL_5m (pair_cost=0.000 at gate=0.0, KEEP rate 0% post-RESET)

Iter 30: gate=0.04+pace=0.30 DISCARD. Zero pairs — 3rd consecutive.
28/417 outcomes (6.7% resolution). correct_side=56.2% weak-moderate.
max_dd=23.2% elevated from unmatched inventory. Knobs restored to best_knobs.
Current knobs: magnitude_gate=0.0, max_onesided_cost=2.0, pace_urgency_lo=0.35.

Gate series exhausted. Outcome sparsity confirmed structural.

Priority queue for rotation 4:
1. **HOLD** — escalate to auditor. Outcome sparsity + elevated DD risk.
2. Knobs clean: magnitude_gate=0.0 already correct.

Blacklist (cumulative): skip 0.55, onesided 2.0->1.5 (COLLAPSE), gate=0.04 (collapse),
conviction_market_start (GLOBAL BLACKLIST).

---

## SOL_15m (pair_cost=0.567 at gate=0.04, KEEP rate 0% post-RESET)

AUDITOR FREEZE ACTIVE — correct_side=45.5% at gate=0.04 (iter 20), down from 47.7% at gate=0.08 (iter 8).
Two consecutive below-50% results confirm directional model degradation on SOL_15m.

Current knobs: magnitude_gate=0.04, max_onesided_cost=5.0 (BLACKLISTED), pace=0.30, risk_ceil=0.20.

**CRITICAL KNOBS ISSUES (to fix when freeze lifts):**
- risk_ceil=0.20 — should be 0.15 per audit directive
- max_onesided_cost=5.0 — BLACKLISTED for SOL_15m (COLLAPSE confirmed pre-RESET)
- bar_budget=300 — stale from old experiment (bar_budget=300 is blacklisted for SOL_15m per prior analysis? Verify)

Priority queue for rotation 4:
1. **HOLD** — auditor freeze active. Do NOT run any SOL_15m experiments.
2. When freeze lifts: FIX stale knobs first (risk_ceil 0.20->0.15, check onesided).
3. Auditor should assess whether lowering magnitude_gate causes correct_side degradation
   by sampling borderline-quality predictions below the magnitude threshold.

Blacklist (cumulative): skip 0.40 (COLLAPSE), onesided ANY reduction from 5.0 (COLLAPSE),
bar_budget 400, conviction_market_start (GLOBAL BLACKLIST).
NOTE: onesided=5.0 in knobs is the BLACKLISTED value — this is a stale knobs state.
The blacklist means onesided should NOT go below 5.0 — so 5.0 itself is the floor, not blacklisted.
CLARIFICATION: onesided=5.0 is the floor. Do not reduce. Do not increase above 5.0 either (not tested).

---

## SOL_1h (pair_cost=0.000 at gate=0.0, KEEP rate 0% post-RESET)

Iter 32: gate=0.0 DISCARD. Zero pairs — 3rd consecutive.
3/35 outcomes (8.6% resolution). correct_side=54.5% moderate.
max_dd=8.3% safe. Knobs restored to best_knobs.
Current knobs: magnitude_gate not set (key absent — needs adding), max_onesided_cost=5.0,
pace_urgency_lo=0.35.

Gate series exhausted. Outcome sparsity confirmed structural.
Pre-RESET pair_cost=0.655, avg_profit=+$1.49/bar — high-value target if unblocked.

Priority queue for rotation 4:
1. **HOLD** — escalate to auditor.
2. KNOBS FIX: add magnitude_gate=0.0 to knobs_SOL_1h.json (key is absent).
3. When auditor resolves: onesided 5.0->2.0 may be first lever (once pairs form).

Blacklist (cumulative): skip 0.35 (COLLAPSE), skip 0.40, risk_ceil 0.20,
conviction_market_start (GLOBAL BLACKLIST).

---

## XRP_5m (FROZEN — permanent)

FROZEN permanently. Structural dead-end confirmed.
fill_rate=15.6% structural microstructure floor. Zero pairs at all tested gates.
Do NOT run experiments. Skip in all rotations.

---

## XRP_15m (pair_cost=0.950 at gate=0.04, KEEP rate 0% post-RESET)

Iter 34: pace_urgency_lo=0.25 DISCARD. pair_cost=0.9500 IDENTICAL to baseline 0.950 (iter 22).
13/141 outcomes (9.2% resolution). correct_side=50.0%.
avg_profit=-$0.23/bar. matched_ratio=0.70% (too thin to detect pace changes).
Knobs restored. Current knobs: magnitude_gate=0.0, pace_urgency_lo=0.30, onesided=2.0.

**Situation:** Pace experiments show zero detectable effect at 0.72% matched_ratio.
With only ~1 pair forming per 140 bars, any parameter change is statistically invisible.
Need MORE pairs to form before pace parameters can be tested effectively.

**Shift strategy for XRP_15m:** Expand pair formation rather than tune pace.
magnitude_gate=0.0 is already in knobs. The next lever is max_onesided_cost reduction or
bar_budget changes to force more pairs into each evaluation window.

Priority queue for rotation 4:
1. magnitude_gate=0.0 BASELINE — formally baseline with gate=0.0 already in knobs.
   Prior baselines used gate=0.04 (iter 22). Need gate=0.0 baseline for clean comparison.
   This is the first clean gate=0.0 baseline for XRP_15m.
   Expected: pair_cost may improve from 0.950 if more pairs form at gate=0.0.
2. If gate=0.0 baseline shows matched_ratio > 1.5%: pace_urgency_lo 0.30->0.25 again.
   Need sufficient pairs for signal to be detectable.
3. If gate=0.0 still shows <1% matched_ratio: consider bar_budget 200->300 to increase
   capital deployed per bar, creating more pair-eligible trades.

Blacklist (cumulative): skip 0.40 (COLLAPSE), bar_budget 300 (D), risk_ceil 0.20,
conviction_market_start (GLOBAL BLACKLIST).
NOTE: Pace experiments are ineffective below ~2% matched_ratio — insufficient statistical power.

---

## XRP_1h (pair_cost=0.812 at gate=0.04, KEEP rate 0% post-RESET)

Iter 35: pace_urgency_lo=0.30 DISCARD — COMPLETE COLLAPSE (matched_ratio 0% vs 4.24% baseline).
pair_cost=0.000 vs 0.812 at baseline. avg_profit=-$0.13/bar vs +$0.10 baseline.
Knobs restored. Current knobs: magnitude_gate=0.04, pace_urgency_lo=0.35, onesided=5.0.

**pace_urgency floor confirmed at 0.35 for XRP_1h.** pace_lo=0.30 causes urgency to fire before
pairs can form in the thin XRP_1h market.

**Pace series exhausted** — pace_lo=0.30 collapses (iter 35), pace_lo=0.45 is the BLACKLISTED
direction (D iter 103 pre-RESET). pace_lo=0.35 is the ONLY viable value for XRP_1h.

**Next lever:** max_onesided_cost reduction. XRP_1h currently has onesided=5.0 in knobs.
Audit Tier 2 item 4 called for onesided 5.0->2.0. Baseline iter 23 used onesided=2.0 already
(knobs_XRP_1h.json shows onesided=5.0 — was restored to best_knobs?).

CHECK: iter 23 baseline at gate=0.04 showed pair_cost=0.812. Current knobs has onesided=5.0.
If iter 23 was run with onesided=5.0, then onesided=2.0 test has NOT been baselined yet.
If iter 23 was run with onesided=2.0 (as prior strategy noted), then 5.0 is the current stale
restored state. The researcher DISCARD restore after iter 35 put knobs back to best_knobs.

**KNOBS AUDIT for XRP_1h:** Current knobs shows onesided=5.0 and magnitude_gate=0.04.
Strategy rotation 2 note: "knobs shows max_onesided_cost=2.0" — this means the researcher
had already applied 2.0 before iter 23. But post-DISCARD restore puts it back to best_knobs=5.0.
The iter 23 baseline was at onesided=2.0. Current baseline reference is onesided=2.0, cost=0.812.
Running onesided=2.0 again is NOT a new experiment — it recreates the baseline.

**RESOLUTION:** XRP_1h at onesided=5.0 (post-restore) has NOT been baselined. It's possible
that onesided=5.0 performs differently from onesided=2.0. Run baseline at current knobs (5.0)
to compare. If pair_cost improves: KEEP at 5.0. If worse: revert to 2.0 (best_knobs baseline).

Priority queue for rotation 4:
1. XRP_1h BASELINE at current knobs (onesided=5.0, gate=0.04, pace=0.35) — establish
   comparison vs iter 23 onesided=2.0 baseline (pair_cost=0.812).
   Accept KEEP if pair_cost < 0.812. If worse: restore to onesided=2.0 as confirmed floor.
2. max_onesided_cost 5.0->2.0 experiment — only if baseline at 5.0 shows cost > 0.812.
   This re-confirms the onesided=2.0 superiority demonstrated in iter 23.
3. pace_urgency_hi 0.85->0.75 — alternative lever for XRP_1h now that pace_lo is floored.
   Untested on XRP_1h. May help pair quality at the urgency transition.
4. STAGE: magnitude_gate 0.04->0.0 as rotation 5 item (not yet needed while pairs form at 0.04).

Blacklist (cumulative): skip 0.45/0.55, bar_budget 300, risk_ceil 0.20,
pace_urgency_lo 0.30 (COLLAPSE iter 35), pace_urgency_lo 0.45 (D iter 103 pre-RESET),
conviction_market_start (GLOBAL BLACKLIST).
PACE_LO FLOOR: 0.35 confirmed. Do NOT go below 0.35 on XRP_1h.

---

## Cross-Pair Observations

**Rotation 3 critical finding — outcome sparsity is the universal bottleneck:**

Gate series is FULLY EXHAUSTED for 6 of 11 active pairs (BTC_5m, BTC_15m, BTC_1h, ETH_5m,
SOL_5m, SOL_1h). Changing magnitude_gate from 0.08 through 0.0 has no effect. The root cause
is that only 3-9% of bars have resolved outcomes, making pair formation statistically near-
impossible. This is a dataset/window issue, not a parameter issue.

**Pairs with confirmed pair formation (potentially improvable):**
| Pair | Matched% | PairCost | Status |
|------|----------|----------|--------|
| ETH_1h | 2.0% | 0.594 | ACTIVE, pace series stalled on thin data |
| XRP_15m | 0.72% | 0.950 | ACTIVE, pair formation too thin for pace testing |
| XRP_1h | 4.2% | 0.812 | ACTIVE, pace floor hit, onesided to test |
| SOL_15m | 0.3% | 0.567 | FROZEN (correct_side < 50%) |
| ETH_15m | 0% | 0.000 | gate=0.0 baseline pending |

**Pairs with confirmed structural dead-ends (zero formation, gate exhausted):**
BTC_5m, BTC_15m, BTC_1h, ETH_5m, SOL_5m, SOL_1h — ESCALATED TO AUDITOR.

**Parameter patterns across rotation 3:**
- pace_urgency_lo: Effective only when matched_ratio > ~2%. Below that threshold, the parameter
  has zero statistical power. Do not test pace on thin pairs.
- magnitude_gate: Confirmed irrelevant as pair formation lever. Gate only matters for 1h TF
  pairs (ETH_1h, XRP_1h, XRP_15m) where bar moves exceed typical thresholds.
- max_onesided_cost: Untested in this rotation. Queued for XRP_1h in rotation 4.
- pace_urgency_lo=0.30 collapse on XRP_1h: likely due to urgency firing before matched pair
  can complete in thin 1h market. Collapse threshold pair-specific.

**Asset patterns:**
- BTC pairs: All three timeframes are outcome-sparsity blocked. BTC Polymarket contracts
  may have a fundamental resolution timing mismatch with the backtest window.
- ETH pairs: 5m blocked; 15m near-blocked (pending gate=0.0 baseline); 1h active.
- SOL pairs: 5m and 1h blocked; 15m frozen on signal quality.
- XRP pairs: 5m permanently frozen; 15m thin but active; 1h active (best performer class).

**Implication for rotation 4:**
- Focus all rotation 4 efforts on the 3 active pairs: ETH_1h, XRP_15m, XRP_1h.
- ETH_15m gate=0.0 baseline (quick check to formally exhaust or recover).
- HOLD all 6 sparsity-blocked pairs pending auditor escalation.

---

## trader_a Benchmark Comparison (after rotation 3, iter 36)

| Pair | PairCost | Target | Gap | AvgProfit | MaxDD% | Status |
|------|----------|--------|-----|-----------|--------|--------|
| BTC_5m | 0.000 | < 0.85 | N/A | -$0.031/bar | 23.4% | HOLD — 4x gate exhaustion, auditor escalated |
| BTC_15m | 0.000 | < 0.85 | N/A | -$0.019/bar | 12.4% | HOLD — 3x gate exhaustion, auditor escalated |
| BTC_1h | 0.000 | < 0.85 | N/A | -$0.032/bar | 3.9% | HOLD — 3x gate exhaustion, auditor escalated |
| ETH_5m | 0.000 | < 0.85 | N/A | -$0.091/bar | 28.7% | HOLD + DD WARNING — auditor escalated |
| ETH_15m | 0.000 | < 0.85 | N/A | +$0.120/bar | 7.1% | gate=0.0 baseline pending (formal confirmation) |
| ETH_1h | 0.594 | < 0.85 | -0.256 | -$0.050/bar | 13.8% | ACTIVE — run baseline at pace=0.35 |
| SOL_5m | 0.000 | < 0.85 | N/A | +$0.135/bar | 23.2% | HOLD — 3x gate exhaustion, auditor escalated |
| SOL_15m | 0.567 | < 0.85 | -0.283 | -$0.270/bar | 19.8% | FROZEN (correct_side=45.5%) |
| SOL_1h | 0.000 | < 0.85 | N/A | -$0.110/bar | 8.3% | HOLD — 3x gate exhaustion, auditor escalated |
| XRP_5m | N/A | < 0.85 | N/A | N/A | N/A | FROZEN (permanent) |
| XRP_15m | 0.950 | < 0.85 | +0.100 | -$0.229/bar | 19.3% | ACTIVE — run gate=0.0 baseline |
| XRP_1h | 0.812 | < 0.85 | -0.038 | +$0.099/bar | 8.0% | ACTIVE — run baseline at onesided=5.0 |

Best performers (forming pairs, trending toward benchmark):
- ETH_1h: pair_cost=0.594 (already BELOW 0.85 target — BENCHMARK ACHIEVED on pair cost)
- XRP_1h: pair_cost=0.812 (gap to target = 0.038 — closest to benchmark among active)

Pre-RESET reference (expected recovery targets):
BTC_5m=0.922, BTC_15m=0.933, BTC_1h=0.799, ETH_5m=0.633, ETH_15m=0.560,
ETH_1h=0.706, SOL_5m=0.676, SOL_15m=0.696, SOL_1h=0.655, XRP_15m=0.638, XRP_1h=0.674

---

## Rotation 4 Execution Plan (priority order)

1. **ETH_15m** — gate=0.0 BASELINE (formal confirmation run)
2. **ETH_1h** — BASELINE at current knobs (pace=0.35, gate=0.04, onesided=2.0)
3. **XRP_15m** — gate=0.0 BASELINE (first formal gate=0.0 test for XRP_15m)
4. **XRP_1h** — BASELINE at current knobs (onesided=5.0, gate=0.04, pace=0.35)
5. **All 6 HOLD pairs** — SKIP until auditor clears escalation
6. **SOL_15m** — SKIP (frozen)
7. **XRP_5m** — SKIP (permanent freeze)

Knobs fixes to apply BEFORE running (researcher must apply before first experiment):
- ETH_5m: add magnitude_gate=0.0 key (currently absent)
- SOL_1h: add magnitude_gate=0.0 key (currently absent)
- XRP_1h: current knobs at onesided=5.0 — this is the baseline state, do NOT change before baseline run

---

## Blacklist Summary

### Per-pair blacklists

- BTC_5m: gate=0.0/0.02/0.04/0.08 (all collapse), skip 0.45/0.55, onesided 2.0->1.5 (COLLAPSE)
- BTC_15m: gate=0.04 (collapse), skip=0.45 (3x collapse), bar_budget 400
- BTC_1h: gate=0.04 (collapse), risk_ceil 0.10/0.20, skip 0.50, onesided 5->3
- ETH_5m: gate=0.04 (collapse), skip 0.60, onesided 1.5->1.0 (COLLAPSE), DD risk at 28.7%
- ETH_15m: skip above 0.50, onesided above 1.5 or below 1.5 (COLLAPSE at 1.0), gate=0.04
- ETH_1h: onesided above 5, skip 0.40, risk_ceil 0.20, bar_budget 250/300
- SOL_5m: skip 0.55, onesided 2.0->1.5 (COLLAPSE), gate=0.04
- SOL_15m: skip 0.40 (COLLAPSE), onesided below 5.0 (COLLAPSE), bar_budget 400
- SOL_1h: skip 0.35 (COLLAPSE), skip 0.40, risk_ceil 0.20
- XRP_5m: ALL (FROZEN permanent)
- XRP_15m: skip 0.40 (COLLAPSE), bar_budget 300, risk_ceil 0.20
- XRP_1h: skip 0.45/0.55, bar_budget 300, risk_ceil 0.20, pace_urgency_lo 0.30 (COLLAPSE iter 35), pace_urgency_lo 0.45 (D pre-RESET)

### Global Blacklist

- conviction_market_start: GLOBALLY BLACKLISTED — fails across ALL tested pairs. DO NOT TEST.
- magnitude_gate=0.08: confirmed too aggressive for 11/12 pairs.
- magnitude_gate=0.04: collapses BTC_5m, BTC_15m, BTC_1h, ETH_5m, ETH_15m, SOL_5m, SOL_1h.
- magnitude_gate=0.0: does NOT restore pair formation for any sparsity-blocked pair.
  Gate parameter is exhausted as a pair-formation lever for 7 pairs.
- pace_urgency_lo experiments: INEFFECTIVE when matched_ratio < ~2% (insufficient statistical power).
  Do not test pace changes on pairs with <2% matched_ratio.
