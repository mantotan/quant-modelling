# Dutch Audit Report
After iteration 48 (2026-03-27T16:00:00Z)

## Directives

- FREEZE XRP_5m — PERMANENT (maintained from all prior audits): structural microstructure dead-end
- FREEZE SOL_15m — MAINTAINED: correct_side=45.5% at gate=0.04 (iter 20), 47.7% at gate=0.08 (iter 8), both below 50%; model directionally wrong; do NOT run experiments
- FREEZE XRP_15m — NEW: correct_side dropped to 49.2% at gate=0.0 (iter 46), below 50% threshold; matches SOL_15m signal degradation pattern; gate series fully exhausted (iter 22 gate=0.04, iter 46 gate=0.0 identical cost=0.950); no viable experiments remain; FREEZE pending signal quality investigation
- FREEZE BTC_5m — MAINTAINED: 4 consecutive zero-pair baselines (gate=0.08/0.04/0.02/0.0 all fail); outcome sparsity structural (40/420 = 9.5%); all parameter levers exhausted; FREEZE pending structural resolution
- FREEZE BTC_15m — NEW: 3 consecutive zero-pair baselines (gate=0.08/0.04/0.0 all fail, iters 2/14/25); outcome sparsity structural (11/139 = 7.9%); gate and onesided experiments both exhausted; no viable experiments remain within current outcome window; FREEZE pending structural resolution
- FREEZE BTC_1h — NEW: 3 consecutive zero-pair baselines (gate=0.08/0.04/0.0 all fail, iters 3/15/26); outcome sparsity extreme (1/34 = 2.9%); virtually impossible to form pairs; FREEZE pending structural resolution
- FREEZE ETH_5m — NEW: 3 consecutive zero-pair baselines (gate=0.08/0.04/0.0 all fail, iters 4/16/27); outcome sparsity structural (36/414 = 8.7%); max_dd=28.7% dangerously close to 30% kill threshold from unmatched inventory accumulation; FREEZE to prevent DD blowup; resume only with outcome window fix
- FREEZE ETH_15m — NEW: 3 consecutive zero-pair baselines (gate=0.08/0.04/0.0 all fail, iters 5/17/40); outcome sparsity structural (14/142 = 9.9%); gate series formally exhausted in rotation 4; FREEZE pending structural resolution
- FREEZE SOL_5m — NEW: 3 consecutive zero-pair runs (gate=0.08/0.04/0.04+pace all fail, iters 7/19/30); outcome sparsity structural (28/417 = 6.7%); max_dd=23.2% elevated; FREEZE pending structural resolution
- FREEZE SOL_1h — NEW: 3 consecutive zero-pair baselines (gate=0.08/0.04/0.0 all fail, iters 9/21/32); outcome sparsity structural (3/35 = 8.6%); FREEZE pending structural resolution
- PRIORITIZE ETH_1h — highest priority active pair; pair_cost=0.594 already beats trader_a target; DD improved 13.8%->7.6% over rotation 4; profit improving to +$0.08/bar; next lever: pace_urgency_lo 0.35->0.30 (knobs already staged)
- CONTINUE XRP_1h — second active pair; pair_cost=0.812, closest to trader_a target among non-ETH_1h; onesided=2.0 experiment is the pending next step (knobs pre-staged); pace floor confirmed at 0.35

## Critical Structural Finding: Outcome Sparsity Universal Bottleneck

**All 7 HOLD/FREEZE pairs share the same root cause.** In the backtest window, only 3-10% of bars have resolved outcomes from the live-log source. Pair formation requires BOTH sides to have resolved outcomes within the same evaluation window. With 3-10% resolution, the probability of two matching outcomes = (0.03-0.10)^2 ≈ 0.09-1% per bar, explaining near-zero matched_ratio across all these pairs.

This is NOT a parameter problem. No combination of magnitude_gate, pace_urgency, max_onesided_cost, or other knobs can fix outcome sparsity. The bottleneck is the data source feeding resolved outcomes into the backtest.

**Structural resolution options (auditor directive for researcher):**
1. OUTCOME_SOURCE_CHANGE: Investigate whether the backtest can use OHLC-based outcome resolution (e.g., bar close above/below mid-price at open) rather than live-log events. This would give 100% outcome resolution and is the most likely path to unblocking 7 frozen pairs.
2. WINDOW_EXPANSION: If live-log must be used, determine whether extending the backtest window to include a longer historical period with more live-log data would materially increase resolution rate above 10%.
3. DECLARE_DEAD_END: If OHLC resolution is incompatible with Dutch strategy design, formally declare BTC_5m/15m/1h, ETH_5m/15m, SOL_5m/1h as structural dead-ends and focus all future research on ETH_1h and XRP_1h exclusively.

**For rotation 5 the researcher must NOT run any experiments on the 10 frozen pairs.** The only active pairs requiring experiments are ETH_1h and XRP_1h. The structural question above should be investigated by the researcher as a diagnostic task BEFORE running ETH_1h/XRP_1h experiments if possible.

## Per-Pair Assessment

| Pair | Best Post-RESET Cost | R4 Cost | MatchedRatio | CorrectSide | MaxDD% | KEEP Rate | Trajectory | Action |
|------|---------------------|---------|--------------|-------------|--------|-----------|------------|--------|
| BTC_5m | 0.000 (gate=0.0 all fail) | 0.000 | 0% | 62.9% | 23.4% | 0% (4 baselines) | BLOCKED — 4x gate exhaustion | FREEZE |
| BTC_15m | 0.000 (gate=0.0 iter25) | 0.000 | 0% | 60.7% | 12.4% | 0% (3 baselines) | BLOCKED — gate+onesided exhausted | FREEZE |
| BTC_1h | 0.000 (gate=0.0 iter26) | 0.000 | 0% | 70.0% | 3.9% | 0% (3 baselines) | BLOCKED — extreme sparsity (2.9%) | FREEZE |
| ETH_5m | 0.000 (gate=0.0 iter27) | 0.000 | 0% | 52.9% | 28.7% | 0% (3 baselines) | BLOCKED + DD WARNING | FREEZE |
| ETH_15m | 0.000 (gate=0.0 iter40) | 0.000 | 0% | 71.2% | 7.1% | 0% (3 baselines) | BLOCKED — gate formally exhausted R4 | FREEZE |
| ETH_1h | 0.594 (gate=0.04 iter18/41) | 0.594 | 2.0% | 65.5% | 7.6% | 1/4 valid | IMPROVING — DD down, profit up | PRIORITIZE |
| SOL_5m | 0.000 (3x gate fail) | 0.000 | 0% | 56.2% | 23.2% | 0% (3 runs) | BLOCKED | FREEZE |
| SOL_15m | 0.567 (few pairs) | FROZEN | 0.3% | 45.5% | 19.8% | 0% (freeze) | FROZEN — correct_side below 50% | FREEZE |
| SOL_1h | 0.000 (3x gate fail) | 0.000 | 0% | 54.5% | 8.3% | 0% (3 baselines) | BLOCKED | FREEZE |
| XRP_5m | FROZEN | N/A | 0% | 57.8% | 13.4% | N/A (frozen) | PERMANENT FREEZE | FREEZE |
| XRP_15m | 0.950 (iters 22/46) | 0.950 | 0.7% | 49.2% | 20.5% | 0% R3+R4 | DEGRADING — correct_side < 50% | FREEZE |
| XRP_1h | 0.812 (iters 23/47) | 0.812 | 4.1% | 66.7% | 9.8% | 0% R3+R4 | STABLE — onesided=2.0 untested | CONTINUE |

## trader_a Gap Analysis

| Pair | R4 Cost | Pre-RESET Best | Target | Cost Gap | Profit | DD | Status |
|------|---------|----------------|--------|----------|--------|----|--------|
| ETH_1h | 0.594 | 0.706 | <0.85 | -30% (BEATS) | +$0.08/bar | 7.6% | ACTIVE, approaching profitability |
| XRP_1h | 0.812 | 0.674 | <0.85 | -4.5% (BEATS) | -$0.14/bar | 9.8% | ACTIVE, cost meets target, profit negative |
| XRP_15m | 0.950 | 0.638 | <0.85 | +11.8% (FAILS) | -$0.24/bar | 20.5% | FREEZE — correct_side degraded |
| SOL_15m | 0.567* | 0.696 | <0.85 | N/A (misleading) | -$0.27/bar | 19.8% | FREEZE — correct_side degraded |
| All others | N/A | varies | <0.85 | N/A | N/A | N/A | FREEZE — outcome sparsity |

*SOL_15m: artificially low (0.3% matched_ratio — near-zero pairs)

**System status: Only ETH_1h meets pair_cost target AND has improving profit/DD. XRP_1h meets pair_cost target but profit is negative.**

## Trajectory Analysis (rotations 1-4)

### ETH_1h — Improving
- Iter 6 (R1 baseline): cost=0.000, zero pairs at gate=0.08
- Iter 18 (R2 baseline): cost=0.594, 2.0% matched, profit=-$0.06, DD=13.8%
- Iter 29 (R3 pace=0.25): DISCARD — identical to baseline (thin dataset)
- Iter 41 (R4 baseline pace=0.35): cost=0.594, 2.0% matched, profit=+$0.08, DD=7.6%

Trajectory: STABLE cost, IMPROVING profit (+$0.14/bar swing), IMPROVING DD (-6.2%). The pace experiment in R3 was correctly discarded. The R4 baseline confirmed pace=0.35 is a solid floor. Next pace=0.30 experiment is the right move.

### XRP_1h — Stable but profit negative
- Iter 12 (R1 baseline): cost=0.855, 3.6% matched, profit N/A, DD=3.1%
- Iter 23 (R2 baseline): cost=0.812, 4.2% matched, profit=+$0.10, DD=8.0%
- Iter 35 (R3 pace=0.30): DISCARD — complete collapse (0% matched vs 4.2%)
- Iter 47 (R4 baseline onesided=5.0): cost=0.812, 4.1% matched, profit=-$0.14, DD=9.8%

Trajectory: STABLE cost (0.812 confirmed across 2 measurements), WORSENING profit (iter23=+$0.10 → iter47=-$0.14). The profit regression is concerning. The onesided=5.0 vs 2.0 question is still open — iter47 used onesided=5.0 in knobs and iter23 used onesided=2.0 (best_knobs at that time was 5.0, but knobs file showed 2.0 per strategy notes). This needs to be resolved: current knobs_XRP_1h.json shows max_onesided_cost=2.0 (already staged!), which is correct for the next experiment.

### XRP_15m — Degrading (new FREEZE)
- Iter 11 (R1 baseline): cost=0.000, 0% matched, correct_side=53.7%
- Iter 22 (R2 baseline): cost=0.950, 0.72% matched, correct_side=50.0%
- Iter 34 (R3 pace=0.25): DISCARD — identical (pace undetectable at 0.72%)
- Iter 46 (R4 gate=0.0): cost=0.950, 0.70% matched, correct_side=49.2%

Three measurements: correct_side 53.7% → 50.0% → 49.2% — a monotonic decline across every rotation. This mirrors the SOL_15m pattern exactly. FREEZE is the correct action.

## Risk Flags

- **ETH_5m max_dd=28.7%**: With magnitude_gate=0.0 in knobs and zero pairs, the unmatched inventory continues to accumulate. If run again, DD may exceed 30% kill threshold. FREEZE prevents this risk.

- **XRP_15m correct_side declining monotonically**: 53.7% → 50.0% → 49.2% across 3 rotations. Same pattern as SOL_15m (47.7% → 45.5%). Both pairs have the model predicting directionally wrong more than right when pairs form. The Pulse model quality on 15m timeframes may be degrading or was never reliable.

- **10 of 12 pairs now frozen**: Only ETH_1h and XRP_1h are active. This is a concentration risk — if either pair deteriorates, the Dutch autoresearch system has no productive pairs. The structural outcome sparsity issue must be investigated urgently.

- **XRP_1h profit regression**: From +$0.10/bar (iter23) to -$0.14/bar (iter47). Both measurements used identical gate=0.04 and similar matched_ratio (~4%). The profit decline may be due to different bar windows being sampled (dataset is expanding as more live data comes in). Monitor carefully — if the next experiment (onesided=2.0) also shows negative profit, investigate whether the backtest window has changed.

- **Knobs state issue in ETH_1h**: knobs_ETH_1h.json has pace_urgency_lo=0.30 (staged for next experiment) while best_knobs_ETH_1h.json has 0.35. This is correct staging — the next experiment IS pace=0.30. No fix needed. But the researcher must NOT restore best_knobs after this experiment if it is a KEEP.

- **SOL_15m knobs stale**: risk_ceil=0.2 (should be 0.15), max_onesided_cost=5.0 (vs best_knobs 5.0 — OK), pace=0.30 (pre-staged). Since frozen, these stale values are harmless but should be fixed when freeze lifts.

## Researcher Compliance Assessment — Rotation 4 (iters 37-48)

Rotation 4 compliance: EXCELLENT.
- Correctly executed all HOLDs for 6 escalated pairs (BTC_15m/1h, ETH_5m/15m, SOL_5m/1h)
- Correctly ran ETH_15m gate=0.0 baseline per rotation-4 plan (iter 40)
- Correctly ran ETH_1h baseline at pace=0.35 per rotation-4 plan (iter 41)
- Correctly ran XRP_15m gate=0.0 baseline per rotation-4 plan (iter 46)
- Correctly ran XRP_1h baseline at onesided=5.0 per rotation-4 plan (iter 47)
- Applied knobs fixes (ETH_5m magnitude_gate=0.0, SOL_1h magnitude_gate=0.0) per strategy directives
- Maintained SOL_15m and XRP_5m FREEZE
- Correctly identified iters_since_auditor=24 and flagged auditor due

One correction needed: iter 37 ran BTC_15m as a SKIP (correct), but the pair rotation in dispatch_state.json shows current_pair=BTC_15m for rotation 5. This is fine — the rotation advanced correctly.

Compliance rate: 12/12 = 100% for rotation 4.

## Recommendations for Rotation 5 (iters 49-60)

### IMMEDIATE ACTION: Structural Investigation (must precede or run alongside experiments)

The researcher must investigate the outcome resolution mechanism as a DIAGNOSTIC task:

**Diagnostic Task A** — Check outcome source statistics:
- How many live-log resolved outcomes exist in the backtest data window across all pairs?
- What is the outcome resolution rate if OHLC close is used instead of live-log?
- Document findings in researcher_ack.txt before running experiments.

**Diagnostic Task B** — If OHLC-based outcomes are feasible:
- Test BTC_5m with OHLC outcomes (not live-log) as a NEW BASELINE
- If pair_cost improves significantly and matched_ratio exceeds 5%, this unlocks 7 frozen pairs
- Report result — auditor will reassess all frozen pairs if this works

### Tier 1 — Active pair optimization (run regardless of diagnostic results)

1. **ETH_1h** — pace_urgency_lo 0.35->0.30 experiment
   - Knobs already staged at pace=0.30 in knobs_ETH_1h.json
   - Baseline: pair_cost=0.594, profit=+$0.08/bar, DD=7.6%, matched=2.0%
   - Accept KEEP if: pair_cost <= 0.594 AND avg_profit >= -$0.02/bar AND max_dd <= 10%
   - DISCARD if: pair_cost increases OR matched_ratio drops below 1.0% OR DD exceeds 12%

2. **XRP_1h** — max_onesided_cost 5.0->2.0 experiment
   - Knobs already staged at onesided=2.0 in knobs_XRP_1h.json
   - Baseline: pair_cost=0.812, profit=-$0.14/bar, DD=9.8%, matched=4.1%
   - Accept KEEP if: pair_cost < 0.812 OR avg_profit > -$0.14/bar (any improvement on either metric)
   - DISCARD if: matched_ratio drops below 2.0% OR DD exceeds 15%
   - Note: iter23 was at onesided=2.0 and showed profit=+$0.10 — if this result is reproducible, KEEP is likely

### Tier 2 — If OHLC outcome resolution works (diagnostic-dependent)

3. **BTC_5m** — OHLC-based NEW BASELINE (highest priority among frozen pairs)
   - Only attempt if Diagnostic Task B confirms OHLC outcomes are feasible
   - Expected: matched_ratio should approach historical matched_ratio from pre-RESET
   - Pre-RESET reference: pair_cost=0.922

4. **ETH_15m** — OHLC-based NEW BASELINE (second priority; correct_side=71.2% very strong)
   - Only attempt after BTC_5m OHLC baseline shows positive results
   - Pre-RESET reference: pair_cost=0.560

### Tier 3 — Do NOT attempt in rotation 5

- All other frozen pairs: BTC_15m, BTC_1h, ETH_5m, SOL_5m, SOL_1h
  - Only unfreeze if OHLC outcome resolution is confirmed working
- SOL_15m: FROZEN — correct_side must recover above 50% before any experiment
- XRP_15m: FROZEN (new) — correct_side below 50% confirmed
- XRP_5m: PERMANENT FREEZE

### Required knobs state for rotation 5

| Pair | File | Current Value | Required | Action |
|------|------|---------------|----------|--------|
| ETH_1h | knobs_ETH_1h.json | pace_urgency_lo=0.30 | pace_urgency_lo=0.30 | CORRECT — no change needed |
| ETH_1h | best_knobs_ETH_1h.json | pace_urgency_lo=0.35 | pace_urgency_lo=0.35 | CORRECT — reference baseline |
| XRP_1h | knobs_XRP_1h.json | max_onesided_cost=2.0 | max_onesided_cost=2.0 | CORRECT — already staged |
| XRP_1h | best_knobs_XRP_1h.json | max_onesided_cost=5.0 | max_onesided_cost=5.0 | CORRECT — reference baseline |
| SOL_15m | knobs_SOL_15m.json | risk_ceil=0.2 | risk_ceil=0.15 | FIX when freeze lifts |

All other knobs files are in correct state for their frozen status.

## System-Level Assessment

**Overall KEEP rate (all rotations):**
- Rotation 1 (iters 1-12): 0/12 = 0% (all baselines, no experiments)
- Rotation 2 (iters 13-24): 0/11 = 0% (baselines and first experiments, all fail or DISCARD)
- Rotation 3 (iters 25-36): 0/10 = 0% (experiments all fail; 2 SKIPs)
- Rotation 4 (iters 37-48): 0/7 = 0% (5 SKIPs, 1 BASELINE, 2 DISCARDs; ETH_1h baseline improved but is reference not KEEP)
- Cumulative KEEP rate: 0/48 = 0%

This 0% KEEP rate across 48 iterations is the strongest evidence that the current experiment space (parameter knobs) is exhausted for most pairs, and the structural bottleneck is the outcome resolution mechanism. The autoresearch system cannot make progress until the outcome sparsity is resolved.

**The two genuinely productive pairs (ETH_1h, XRP_1h) have never produced a KEEP** — they have been in baseline-establishment and DISCARD mode. The next rotation must attempt true optimization experiments on these pairs and must produce at least one KEEP to validate that the system can make progress.

**If rotation 5 produces 0 KEEPs on ETH_1h and XRP_1h**, the auditor recommends suspending autoresearch and focusing engineering effort on fixing the outcome resolution mechanism before continuing.
