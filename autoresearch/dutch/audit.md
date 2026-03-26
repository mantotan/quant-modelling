# Dutch Audit Report
After iteration 60 (2026-03-27T19:00:00Z)

## Directives

- FREEZE XRP_5m — PERMANENT (maintained): structural fill_rate=15.6% floor, zero pairs at all tested gates
- FREEZE SOL_15m — MAINTAINED: correct_side=45.5%/47.7% both measurements below 50%; directionally wrong
- FREEZE XRP_15m — MAINTAINED: correct_side declined monotonically 53.7%->50.0%->49.2%; gate exhausted; confirmed degrading
- FREEZE BTC_5m — CONFIRMED PERMANENT (diagnostic iter 60 proves fill mechanics, not outcomes, are the barrier): P(both sides fill)=5.6% structural floor; no parameter lever can fix this
- FREEZE BTC_15m — MAINTAINED: 3 consecutive zero-pair baselines; outcome sparsity structural (7.9%)
- FREEZE BTC_1h — MAINTAINED: extreme sparsity (2.9%); gate series exhausted
- FREEZE ETH_5m — MAINTAINED: DD=28.7% near kill threshold; fill mechanics structural (P≈5.8%); do NOT run
- FREEZE ETH_15m — MAINTAINED: gate series exhausted R4; outcome sparsity (9.9%)
- FREEZE SOL_5m — MAINTAINED: 3 consecutive zero-pair runs; fill mechanics structural (P≈4.2%)
- FREEZE SOL_1h — MAINTAINED: 3 consecutive zero-pair baselines; outcome sparsity (8.6%)
- PRIORITIZE ETH_1h — HIGHEST PRIORITY: pair_cost=0.594 beats target, profit=+$0.08/bar positive; next lever fill_ticks=2 (stage before running)
- CONTINUE XRP_1h — SECOND ACTIVE PAIR: pair_cost=0.812 meets target, profit=-$0.14/bar negative; next lever fill_ticks=2 (stage before running)

**RESET CONTEXT**: This audit follows a fresh reset with TF-specific fill simulator params. The reset exit note specifies:
- 5m pairs: chase=0.02/offset=0.02/max_chase=4 (not yet applied to knobs — irrelevant since 5m pairs are FROZEN PERMANENT)
- 15m pairs: chase=0.025/offset=0.015/max_chase=3 (not yet applied to knobs — irrelevant since all 15m pairs are FROZEN)
- The reset does NOT change the status of any frozen pair. All freezes are maintained.
- The reset's new fill simulator params should be staged in knobs files when/if those pairs are ever unfrozen.

## Per-Pair Assessment

| Pair | Best PairCost | MatchedRatio | CorrectSide | MaxDD% | KEEP Rate | Trajectory | Action |
|------|--------------|--------------|-------------|--------|-----------|------------|--------|
| BTC_5m | 0.000 (all 4 gates fail) | 0% | 62.9% | 23.4% | 0% (5 total incl. diag) | BLOCKED PERMANENT — fill mechanics (P≈5.6%) | FREEZE PERMANENT |
| BTC_15m | 0.000 (3 gates fail) | 0% | 60.7% | 12.4% | 0% (3 baselines) | BLOCKED — outcome sparsity (7.9%) | FREEZE |
| BTC_1h | 0.000 (3 gates fail) | 0% | 70.0% | 3.9% | 0% (3 baselines) | BLOCKED — extreme sparsity (2.9%) | FREEZE |
| ETH_5m | 0.000 (3 gates fail) | 0% | 52.9% | 28.7% | 0% + DD WARNING | BLOCKED PERMANENT — fill mechanics (P≈5.8%) + DD risk | FREEZE |
| ETH_15m | 0.000 (3 gates fail) | 0% | 71.2% | 7.1% | 0% (3 baselines) | BLOCKED — outcome sparsity (9.9%); strong latent signal | FREEZE |
| ETH_1h | 0.594 (stable 3 measurements) | 2.0% | 65.5% | 7.6% | 0 KEEPs (2 DISCARDs + 2 baselines) | IMPROVING: DD 13.8%->7.6%, profit -$0.06->+$0.08/bar | PRIORITIZE |
| SOL_5m | 0.000 (3 gate fails) | 0% | 56.2% | 23.2% | 0% | BLOCKED PERMANENT — fill mechanics (P≈4.2%) + elevated DD | FREEZE |
| SOL_15m | 0.567* (near-zero pairs) | 0.3% | 45.5% | 19.8% | 0% (frozen) | FROZEN — directionally wrong | FREEZE |
| SOL_1h | 0.000 (3 gates fail) | 0% | 54.5% | 8.3% | 0% | BLOCKED — outcome sparsity (8.6%) | FREEZE |
| XRP_5m | N/A | 0% | 57.8% | 13.4% | N/A | PERMANENT FREEZE | FREEZE PERMANENT |
| XRP_15m | 0.950 (2 measurements identical) | 0.7% | 49.2% | 20.5% | 0% (R3+R4+R5) | DEGRADING — correct_side declining | FREEZE |
| XRP_1h | 0.812 (stable 2 measurements) | 4.1% | 66.7% | 9.8% | 0 KEEPs (2 DISCARDs + 2 baselines) | STABLE cost, VOLATILE profit (+$0.10->-$0.14/bar swing) | CONTINUE |

*SOL_15m: artificially low pair_cost (near-zero pairs, only 0.3% matched_ratio)

## trader_a Gap Analysis

| Pair | PairCost | Target | Cost Gap | Profit/bar | DD | Status | ETA |
|------|----------|--------|----------|------------|-----|--------|-----|
| ETH_1h | 0.594 | <0.85 | -0.256 (BEATS by 30%) | +$0.08 | 7.6% | ACTIVE — approaching profitable | 2-3 rotations to validate |
| XRP_1h | 0.812 | <0.85 | -0.038 (BEATS by 4.5%) | -$0.14 | 9.8% | ACTIVE — cost meets target, profit negative | 3-5 rotations to fix profit |
| ETH_15m | 0.000 | <0.85 | N/A (blocked) | +$0.16 unmatched | 7.1% | FROZEN — strong latent signal wasted | Unblockable without engineering |
| BTC_1h | 0.000 | <0.85 | N/A (blocked) | N/A | 3.9% | FROZEN — extreme sparsity | Unblockable without engineering |
| All others | 0.000 or N/A | <0.85 | N/A | N/A | various | FROZEN — structural | Unblockable without engineering |

## Trajectory Analysis (Rotations 1-5 + Diagnostic, 60 iterations)

### ETH_1h — Improving (PRIORITIZE maintained)
- Iter 6 (R1): cost=0.000, zero pairs at gate=0.08
- Iter 18 (R2 baseline): cost=0.594, 2.0%, profit=-$0.06/bar, DD=13.8%
- Iter 29 (R3 pace=0.25): DISCARD — identical (thin dataset, pace inert)
- Iter 41 (R4 baseline pace=0.35): cost=0.594, 2.0%, profit=+$0.08/bar, DD=7.6%
- Iter 53 (R5 pace=0.30): DISCARD — identical (pace lever DEAD on thin data, confirmed twice)

**Assessment**: pair_cost locked at 0.594 across 3 independent measurements — this is a stable floor, not noise. Profit improved $0.14/bar between R2 and R4 baselines without any parameter change (dataset growth effect). DD improved 6.2 pct. The next untested lever is fill_ticks (fill simulator parameter, not pace constraint). This is the correct direction: fill_ticks=2 increases order persistence without touching the spending mechanism.

**Pattern**: The 2 DISCARDs confirm the dataset is too thin for pace lever detection (<5 outcomes). Fill_ticks operates at the order-fill level and may improve matched_ratio rather than pair_cost — a different mechanism worth testing.

### XRP_1h — Stable cost, volatile profit (CONTINUE maintained)
- Iter 12 (R1 baseline): cost=0.855, 3.6%, profit=N/A, DD=3.1%
- Iter 23 (R2 baseline): cost=0.812, 4.2%, profit=+$0.10/bar, DD=8.0%
- Iter 35 (R3 pace=0.30): DISCARD — COLLAPSE (0% matched); pace floor confirmed at 0.35
- Iter 47 (R4 baseline onesided=5.0): cost=0.812, 4.1%, profit=-$0.14/bar, DD=9.8%
- Iter 59 (R5 onesided=2.0): DISCARD — COLLAPSE (0% matched); onesided floor confirmed at 5.0

**Assessment**: pair_cost is stable at 0.812 (confirmed across 2 independent measurements with identical gate). The profit regression (+$0.10 in iter23 to -$0.14 in iter47) is concerning but may reflect dataset window evolution as live data accumulates — both measurements used the same structural params. The two COLLAPSE events reveal XRP_1h is highly sensitive to spending constraints: any constraint that caps spending below $3-5/pair before pair formation completes triggers complete failure. fill_ticks is NOT a spending constraint — it extends order persistence, so it should not trigger collapse.

**Risk**: XRP_1h has now produced 2 COLLAPSEs in 2 experiment attempts. If fill_ticks also fails (any mechanism), we will have 3 consecutive DISCARDs. Strategy.md specifies that 3 consecutive DISCARDs should escalate to auditor — that threshold will be reached at rotation 6 end if fill_ticks DISCARDs.

### All 10 Frozen Pairs — Structural Barriers Confirmed
- **5m pairs (BTC_5m, ETH_5m, SOL_5m, XRP_5m)**: Permanent fill mechanics barrier. P(both sides fill in 5m bar) = 2-6%. The iter 60 diagnostic conclusively proved even 100% outcome resolution (spot outcomes) cannot unblock 5m pairs. Engineering fix: market orders or multi-bar accumulation window. Not addressable by parameter tuning.
- **15m pairs (BTC_15m, ETH_15m, SOL_15m, XRP_15m)**: Dual barriers — outcome sparsity AND fill mechanics (P≈9-20%). Plus SOL_15m and XRP_15m have correct_side below 50%. No viable experiments remain without structural changes.
- **1h sparse pairs (BTC_1h, SOL_1h)**: Outcome sparsity structural. Resolution rates 2.9-8.6%. Gate series exhausted.

## Risk Flags

1. **0% cumulative KEEP rate (0/60 iterations)**: Six rotations with zero KEEPs is the strongest evidence that the parameter search space for the Dutch strategy is structurally constrained by the data source (live-log outcomes) and fill mechanics. Parameter tuning cannot overcome these structural barriers.

2. **XRP_1h sensitivity risk**: Two consecutive COLLAPSEs mean any further spending constraint tightening must be avoided. fill_ticks is the only safe experiment category remaining. If fill_ticks DISCARDs, XRP_1h has no remaining levers and should be assessed for structural floor status.

3. **ETH_1h profit volatility at thin dataset**: With only 4-5 live-log outcomes in 34-35 bars, any single outcome flip can swing avg_profit by $0.05-0.10/bar. The +$0.08/bar result is based on very few actual matched pairs. Statistical confidence is low but improving as dataset grows organically.

4. **ETH_15m wasted signal**: correct_side=71.2% (3 consistent measurements) is the strongest model signal in the system. Yet this pair is frozen by fill mechanics. This represents the largest latent opportunity — if a 15m fill mechanics fix were deployed (fill_ticks increase, spread_offset widening, or market orders), ETH_15m would likely be the most productive pair.

5. **Reset TF-specific params not staged**: The dispatch reset included new fill sim params (5m: chase=0.02/offset=0.02/max_chase=4; 15m: chase=0.025/offset=0.015/max_chase=3) but these are NOT reflected in any current knobs files. Since all 5m/15m pairs are frozen, this is not immediately critical, but when (if) these pairs are unfrozen, the new params must be staged before running.

6. **Concentration in 2 active pairs only**: If both ETH_1h and XRP_1h hit structural floors in rotation 6, the Dutch autoresearch system has no productive pairs and must suspend pending engineering changes.

## Researcher Compliance Assessment — Rotation 5 (iters 49-60)

Compliance: EXCELLENT — 100%.
- Correctly SKIPped all 10 frozen pairs (iters 49-58)
- Correctly ran ETH_1h pace=0.30 experiment (iter 53) per audit Tier 1 item 1
- Correctly ran XRP_1h onesided=2.0 experiment (iter 59) per audit Tier 1 item 2
- Correctly ran BTC_5m DIAGNOSTIC task (iter 60) per auditor mandate from prior report
- Correctly documented root cause revision (fill mechanics, not outcomes) in researcher_ack.txt
- Correctly advanced rotation to BTC_15m after diagnostic
- Correctly staged fill_ticks=2 as next lever in strategy.md rotation 6 plan
- No experiments run on frozen pairs

Compliance rate: 12/12 = 100%

## Recommendations for Rotation 6 (iters 61-72)

### CRITICAL: What this audit changes

The prior audit (iter 48) issued a structural investigation mandate (Diagnostic Tasks A and B). Those tasks are COMPLETE (iter 60 diagnostic). The findings:
1. Outcome sparsity is NOT the primary bottleneck for 5m pairs — fill mechanics are. CONFIRMED.
2. 5m pairs are permanently frozen regardless of outcome source. CONFIRMED.
3. 1h pairs (ETH_1h, XRP_1h) remain the only viable optimization targets. CONFIRMED.

No new structural investigation is needed. Rotation 6 should focus exclusively on fill_ticks experiments for the 2 active pairs.

### Tier 1 — Active pair experiments (MANDATORY)

**1. ETH_1h — fill_ticks 1->2 experiment**
- Action required before running: stage `fill_simulator.fill_ticks=2` in knobs_ETH_1h.json
- Baseline ref: pair_cost=0.594, profit=+$0.08/bar, DD=7.6%, matched=2.0%
- KEEP criteria (ANY improvement): matched_ratio > 2.0% OR avg_profit > +$0.08/bar
- DISCARD if: pair_cost increases above 0.65 OR DD exceeds 12% OR matched_ratio drops below 1.5%
- If KEEP: update best_knobs_ETH_1h.json with fill_ticks=2
- If DISCARD: restore fill_ticks=1; next lever = chase_threshold 0.03->0.05

**2. XRP_1h — fill_ticks 1->2 experiment**
- Action required before running: stage `fill_simulator.fill_ticks=2` in knobs_XRP_1h.json
- Baseline ref: pair_cost=0.812, profit=-$0.14/bar, DD=9.8%, matched=4.1%
- KEEP criteria (ANY improvement): pair_cost < 0.812 OR avg_profit > -$0.14/bar
- DISCARD if: matched_ratio drops below 2.0% OR DD exceeds 15%
- Note: fill_ticks is NOT a spending constraint — should NOT trigger collapse mechanism
- If KEEP: update best_knobs_XRP_1h.json with fill_ticks=2
- If DISCARD: restore fill_ticks=1; next lever = onesided intermediate (3.5) OR pace_urgency_hi 2.0->1.5

### Tier 2 — Contingency plan if both fill_ticks experiments DISCARD

If rotation 6 produces 0 KEEPs on fill_ticks (both ETH_1h and XRP_1h DISCARD):
- **XRP_1h escalation**: 3 consecutive DISCARDs → assess structural floor status
  - Try onesided=3.5 (intermediate between confirmed floor=5.0 and collapse=2.0)
  - If collapse again: XRP_1h is at structural floor, consider FREEZE pending profit engineering
- **ETH_1h contingency**: chase_threshold 0.03->0.05 (wider chase window, different fill mechanism)
- **System-level**: If both active pairs hit floors, suspend autoresearch and escalate to engineering for:
  1. Fill mechanics fix (multi-bar accumulation, spread_offset widening)
  2. Outcome resolution for frozen 1h pairs (BTC_1h, SOL_1h) — could add 2 more active pairs
  3. TF-specific fill params already prepped in dispatch reset — apply to knobs files when pairs unfreeze

### Tier 3 — Do NOT run in rotation 6

- All 10 frozen pairs: maintained frozen
- Specifically: do NOT attempt 15m fill_ticks experiments even though TF-specific params are now specified in the reset — the fill_rate math still applies (P≈9-20% for 15m pairs), and outcome sparsity compounds the issue
- Exception: if ETH_15m correct_side data improves (not expected without new live data), revisit

### Required knobs actions for rotation 6

| Pair | File | Change Required | When |
|------|------|-----------------|------|
| ETH_1h | knobs_ETH_1h.json | fill_simulator.fill_ticks: 1->2 | Before running ETH_1h experiment |
| XRP_1h | knobs_XRP_1h.json | fill_simulator.fill_ticks: 1->2 | Before running XRP_1h experiment |
| All frozen pairs | any knobs | No changes | Maintain current state |

**Note on TF-specific reset params**: The dispatch reset specifies new fill sim params for 5m/15m pairs. These should be applied to the relevant knobs files ONLY when those pairs are unfrozen. Do NOT apply them now as it would create inconsistency with frozen state.

## System-Level Assessment

**Cumulative KEEP rate by rotation:**
- Rotation 1 (iters 1-12): 0/12 = 0% (all baselines)
- Rotation 2 (iters 13-24): 0/12 = 0% (baselines + first experiments, all collapse or identical)
- Rotation 3 (iters 25-36): 0/12 = 0% (experiments all fail; gate exhaustion confirmed)
- Rotation 4 (iters 37-48): 0/12 = 0% (5 SKIPs, baselines, 2 DISCARDs; ETH_1h improves but reference only)
- Rotation 5 (iters 49-60): 0/12 = 0% (10 SKIPs, 2 DISCARDs + diagnostic)
- **Cumulative: 0/60 = 0%**

This 0% KEEP rate is consistent with the structural analysis: 10 of 12 pairs are blocked by fill mechanics or outcome sparsity (not by parameters), and the 2 active pairs have not yet found a lever that measurably improves their thin-dataset results. fill_ticks is the most promising untested lever because it operates at a different layer (order persistence) than all previously tested knobs (spending constraints, gate thresholds, pacing).

**Prognosis:**
- Optimistic: fill_ticks=2 produces first KEEP on ETH_1h or XRP_1h, validating that fill mechanics tuning is productive and opening a new lever category (chase_threshold, max_chase, spread_offset)
- Neutral: fill_ticks=2 DISCARDs (identical to fill_ticks=1 due to thin dataset statistical power), but no harm done — continue with chase_threshold and max_chase variants
- Pessimistic: fill_ticks=2 causes regression (lower matched_ratio or higher DD), suggesting 1h fill mechanics are already near-optimal at fill_ticks=1; no remaining levers; suspend autoresearch pending engineering

**Given the ETH_1h improving trend (profit improved $0.14/bar between R2 and R4 baselines without parameter changes), organic dataset growth is also a positive factor.** As more live bars accumulate and more outcomes resolve, the statistical power of each experiment increases. The system may naturally reach KEEP-tier performance without needing aggressive parameter changes.
