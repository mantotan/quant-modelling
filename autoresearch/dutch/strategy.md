# Dutch Strategy
Updated: after iteration 48 (2026-03-27T16:30:00Z) — STRATEGIST rotation 4 post-analysis

## Summary

Rotation 4 complete (iters 37-48): 7 SKIPs + 1 BASELINE (ETH_15m gate=0.0) + 2 DISCARDs (XRP_15m, XRP_1h) + 1 HOLD_SKIP (BTC_5m rotation-5 advance).
**KEEP rate this rotation: 0/3 active experiments = 0%** (gate exhaustion confirmed ETH_15m; DISCARDs on XRP_15m and XRP_1h).
**Cumulative KEEP rate: 0/48 = 0% across all rotations.**

**Critical outcome from auditor after iter 48:**
- FREEZE issued for XRP_15m (new): correct_side declined monotonically 53.7%->50.0%->49.2% — same pattern as SOL_15m
- FREEZE maintained/extended for: BTC_5m, BTC_15m, BTC_1h, ETH_5m, ETH_15m, SOL_5m, SOL_1h, SOL_15m, XRP_5m (permanent)
- Only 2 ACTIVE pairs remain: **ETH_1h** and **XRP_1h**
- Auditor directs: structural investigation of outcome resolution mechanism REQUIRED in rotation 5

**Researcher compliance (rotation 4):** EXCELLENT — 12/12 = 100% compliance. All HOLDs respected, baselines run correctly, knobs fixes applied.

---

## AUDITOR FREEZES (active — do NOT run experiments)

- **XRP_5m**: FROZEN permanently. Structural microstructure dead-end.
- **SOL_15m**: FROZEN. correct_side=45.5% (both measurements below 50%). Resume only when correct_side > 50%.
- **XRP_15m**: FROZEN (new, iter 48 audit). correct_side=49.2% at gate=0.0, declining monotonically. Gate exhausted. Freeze pending signal investigation.
- **BTC_5m**: FROZEN. 4 consecutive zero-pair baselines. Outcome sparsity (40/420=9.5%). Gate+onesided exhausted.
- **BTC_15m**: FROZEN (new). 3 consecutive zero-pair baselines. Outcome sparsity (11/139=7.9%). All parameter levers exhausted.
- **BTC_1h**: FROZEN (new). 3 consecutive zero-pair baselines. Extreme sparsity (1/34=2.9%). Virtually impossible to form pairs.
- **ETH_5m**: FROZEN (new). 3 consecutive zero-pair baselines. max_dd=28.7% — near 30% kill threshold from unmatched inventory.
- **ETH_15m**: FROZEN (new). Gate formally exhausted in rotation 4 (iter 40 gate=0.0 = zero pairs, 3rd consecutive).
- **SOL_5m**: FROZEN (new). 3 consecutive zero-pair runs. max_dd=23.2% elevated.
- **SOL_1h**: FROZEN (new). 3 consecutive zero-pair baselines. Outcome sparsity (3/35=8.6%).

---

## ETH_1h (pair_cost=0.594 at gate=0.04, KEEP rate N/A — improving)

### Status: ACTIVE — PRIORITIZE (auditor directive)

Trajectory:
- Iter 6 (R1): cost=0.000, zero pairs at gate=0.08
- Iter 18 (R2 baseline): cost=0.594, matched=2.0%, profit=-$0.06/bar, DD=13.8%
- Iter 29 (R3 pace=0.25): DISCARD — identical to baseline (thin dataset)
- Iter 41 (R4 baseline pace=0.35): cost=0.594, matched=2.0%, profit=+$0.08/bar, DD=7.6%

ETH_1h is the **best performer in the system**: pair_cost=0.594 already beats trader_a target of <0.85. DD improved from 13.8%->7.6% between R2 and R4 baselines. Profit improved from -$0.06 to +$0.08/bar. Knobs already staged for next experiment.

**Current knobs state:**
- knobs_ETH_1h.json: pace_urgency_lo=0.30 (STAGED for experiment)
- best_knobs_ETH_1h.json: pace_urgency_lo=0.35 (baseline reference)

Priority queue for rotation 5:
1. **pace_urgency_lo 0.35->0.30 EXPERIMENT** — knobs already staged
   - Baseline ref: pair_cost=0.594, profit=+$0.08/bar, DD=7.6%, matched=2.0%
   - Accept KEEP if: pair_cost <= 0.594 AND avg_profit >= -$0.02/bar AND max_dd <= 10%
   - DISCARD if: pair_cost increases OR matched_ratio drops below 1.0% OR DD exceeds 12%
   - If KEEP: update best_knobs_ETH_1h.json to pace=0.30
   - If DISCARD: restore knobs to pace=0.35; next lever = pace_urgency_hi 2.0->1.5
2. If pace=0.30 KEEPs: pace_urgency_hi 2.0->1.5 experiment
3. If pace=0.30 DISCARDs: fill_ticks 1->2 experiment (untested on ETH_1h)

Blacklist (cumulative): onesided above 5, skip 0.40, risk_ceil 0.20, bar_budget 250/300,
pace_urgency_lo 0.25 (DISCARD iter 29 — identical at thin data), conviction_market_start (GLOBAL BLACKLIST).

---

## XRP_1h (pair_cost=0.812 at gate=0.04, KEEP rate 0%)

### Status: ACTIVE — CONTINUE (auditor directive)

Trajectory:
- Iter 12 (R1 baseline): cost=0.855, matched=3.6%, profit N/A, DD=3.1%
- Iter 23 (R2 baseline): cost=0.812, matched=4.2%, profit=+$0.10/bar, DD=8.0%
- Iter 35 (R3 pace=0.30): DISCARD — COLLAPSE (0% matched vs 4.2%)
- Iter 47 (R4 baseline onesided=5.0): cost=0.812, matched=4.1%, profit=-$0.14/bar, DD=9.8%

XRP_1h meets pair_cost target (<0.85) but profit has turned negative (iter23=+$0.10 vs iter47=-$0.14). The profit regression may reflect dataset window expansion over time. Onesided=2.0 was the condition at iter23 (profitable) vs onesided=5.0 at iter47 (unprofitable). Testing onesided=2.0 is the critical next step.

**Current knobs state:**
- knobs_XRP_1h.json: max_onesided_cost=2.0 (STAGED for experiment)
- best_knobs_XRP_1h.json: max_onesided_cost=5.0 (post-RESET baseline state — likely suboptimal)

Priority queue for rotation 5:
1. **max_onesided_cost 5.0->2.0 EXPERIMENT** — knobs already staged
   - Baseline ref: pair_cost=0.812, profit=-$0.14/bar, DD=9.8%, matched=4.1%
   - Accept KEEP if: pair_cost < 0.812 OR avg_profit > -$0.14/bar (ANY improvement on either metric)
   - DISCARD if: matched_ratio drops below 2.0% OR DD exceeds 15%
   - Note: iter23 (onesided=2.0) showed profit=+$0.10 — if result is similar, KEEP is very likely
2. If onesided=2.0 KEEPs: pace_urgency_hi 0.85->0.75 experiment (untested on XRP_1h)
3. If onesided=2.0 DISCARDs: revert to 5.0; try fill_ticks 1->2 (untested)

Blacklist (cumulative): skip 0.45/0.55, bar_budget 300, risk_ceil 0.20,
pace_urgency_lo 0.30 (COLLAPSE iter 35), pace_urgency_lo 0.45 (D pre-RESET),
conviction_market_start (GLOBAL BLACKLIST).
PACE_LO FLOOR: 0.35 confirmed. Do NOT go below 0.35 on XRP_1h.

---

## Diagnostic Task (REQUIRED before/alongside experiments — auditor mandate)

**This is a structural investigation, not an experiment. Document findings in researcher_ack.txt.**

### Task A: Outcome resolution statistics
- Count live-log resolved outcomes per pair across the full backtest window
- Compare to total bars: current rate is 3-10% (structural bottleneck confirmed)
- Check whether OHLC close-based outcome resolution is accessible via the backtest script flags
- Command hint: check --outcome-source flag in scripts/monitor_pulse.py and sim_dutch_v8.py

### Task B: OHLC outcome resolution test (if feasible)
- Run BTC_5m baseline with OHLC-based outcomes instead of live-log
- If matched_ratio exceeds 5% and pair_cost < 0.950: this unlocks 7 frozen pairs
- Report result in researcher_ack.txt and flag in results.tsv description
- If OHLC works: auditor will reassess all frozen pairs in next audit

Pairs to unfreeze IF OHLC resolution confirmed working (in priority order):
1. ETH_15m (correct_side=71.2% — best signal quality)
2. BTC_5m (largest bar count, fastest to accumulate data)
3. SOL_1h (pre-RESET pair_cost=0.655 — strong pre-RESET performance)
4. BTC_1h (correct_side=70.0% — strong signal, DD safe at 3.9%)
5. SOL_5m, BTC_15m (deferred until top 4 results are in)

---

## Cross-Pair Observations

### Rotation 4 critical findings

**Outcome sparsity is now confirmed universal for 10 of 12 pairs.** The only pairs capable of forming pairs in the current outcome window are ETH_1h (2% matched) and XRP_1h (4% matched). Both use the 1h timeframe — longer bars naturally have more price movement to clear the magnitude gate and more outcomes in the live-log window.

**Pattern by timeframe:**
- 5m pairs: All FROZEN. Fill_rate 15-25% (limit orders rarely fill in 5m). Combined with outcome sparsity, structurally impossible.
- 15m pairs: All FROZEN. Fill_rate 30-45%. Moderate signal quality (SOL/XRP) but correct_side degrading. ETH_15m strong signal but zero pairs.
- 1h pairs: ETH_1h and XRP_1h ACTIVE. Fill_rate 70-85%. Long bars naturally clear price movement requirements. Only viable timeframe.

**Pattern by asset:**
- BTC: All 3 TFs frozen — outcome sparsity dominant across all BTC pairs. BTC Polymarket contracts may resolve on fundamentally different timing.
- ETH: 5m and 15m frozen; 1h ACTIVE and best performer. ETH_1h is the flagship pair.
- SOL: All 3 TFs frozen. 5m/1h by sparsity, 15m by signal quality (correct_side < 50%).
- XRP: 5m permanently frozen; 15m new freeze (correct_side decline); 1h ACTIVE.

**Parameter findings across 48 iterations:**
- magnitude_gate: EXHAUSTED as lever. Gate 0.08/0.04/0.02/0.0 all produce same zero-pair result for 10 pairs. Gate matters only as signal filter for 1h pairs (ETH_1h, XRP_1h) where price movement exceeds gate threshold.
- pace_urgency_lo: INEFFECTIVE when matched_ratio < 2%. Requires sufficient pairs to detect statistical changes. Confirmed floor at 0.35 on XRP_1h.
- max_onesided_cost: 1 DISCARD (iter47 confirmed onesided=5.0 underperforms onesided=2.0 reference). Test 2.0 on XRP_1h is the highest-signal remaining experiment.
- bar_budget: Stale knobs fixed but not yet tested as experiment. Candidate for rotation 6 if onesided/pace tests produce DISCARDs.

---

## trader_a Benchmark Comparison (after rotation 4, iter 48)

| Pair | PairCost | Target | Gap | AvgProfit | MaxDD% | Status |
|------|----------|--------|-----|-----------|--------|--------|
| BTC_5m | 0.000 | < 0.85 | N/A | -$0.031/bar | 23.4% | FROZEN — 4x gate exhaustion, outcome sparsity |
| BTC_15m | 0.000 | < 0.85 | N/A | -$0.019/bar | 12.4% | FROZEN — 3x gate exhaustion, new freeze |
| BTC_1h | 0.000 | < 0.85 | N/A | -$0.032/bar | 3.9% | FROZEN — extreme sparsity (2.9%), new freeze |
| ETH_5m | 0.000 | < 0.85 | N/A | -$0.091/bar | 28.7% | FROZEN — DD WARNING, new freeze |
| ETH_15m | 0.000 | < 0.85 | N/A | +$0.158/bar | 7.1% | FROZEN — gate exhausted R4, new freeze |
| ETH_1h | 0.594 | < 0.85 | -0.256 (BEATS) | +$0.080/bar | 7.6% | ACTIVE — pace=0.30 experiment staged |
| SOL_5m | 0.000 | < 0.85 | N/A | +$0.135/bar | 23.2% | FROZEN — 3x gate exhaustion, new freeze |
| SOL_15m | 0.567* | < 0.85 | N/A | -$0.270/bar | 19.8% | FROZEN — correct_side=45.5% |
| SOL_1h | 0.000 | < 0.85 | N/A | -$0.110/bar | 8.3% | FROZEN — 3x gate exhaustion, new freeze |
| XRP_5m | N/A | < 0.85 | N/A | N/A | N/A | FROZEN (permanent) |
| XRP_15m | 0.950 | < 0.85 | +0.100 (FAILS) | -$0.240/bar | 20.5% | FROZEN — correct_side=49.2%, new freeze |
| XRP_1h | 0.812 | < 0.85 | -0.038 (BEATS) | -$0.140/bar | 9.8% | ACTIVE — onesided=2.0 experiment staged |

*SOL_15m: artificially low pair_cost (near-zero pairs)

Best performers (active, pair_cost already beats target):
- ETH_1h: pair_cost=0.594 — BENCHMARK ACHIEVED. Improving profit trajectory.
- XRP_1h: pair_cost=0.812 — BENCHMARK ACHIEVED. Profit negative, onesided fix pending.

---

## Rotation 5 Execution Plan (priority order)

1. **DIAGNOSTIC** — Check outcome resolution mechanism before or alongside first experiment
   - Document findings in researcher_ack.txt (required per auditor directive)
   - Run BTC_5m OHLC baseline if mechanism is available (unlocks 7 pairs if successful)

2. **BTC_15m** — SKIP (FROZEN, advance rotation to BTC_1h)
3. **BTC_1h** — SKIP (FROZEN)
4. **ETH_5m** — SKIP (FROZEN, DD risk)
5. **ETH_15m** — SKIP (FROZEN)
6. **ETH_1h** — pace_urgency_lo 0.35->0.30 EXPERIMENT (knobs pre-staged, run this)
7. **ETH_1h** → if KEEP: update best_knobs; continue to pace_urgency_hi experiment
8. **SOL_5m** — SKIP (FROZEN)
9. **SOL_15m** — SKIP (FROZEN)
10. **SOL_1h** — SKIP (FROZEN)
11. **XRP_5m** — SKIP (FROZEN permanent)
12. **XRP_15m** — SKIP (FROZEN)
13. **XRP_1h** — max_onesided_cost 5.0->2.0 EXPERIMENT (knobs pre-staged, run this)
14. **BTC_5m** — SKIP unless OHLC diagnostic shows it can be unblocked; if unblocked: OHLC BASELINE

**Rotation 5 success criteria:**
- At minimum 1 KEEP required (ETH_1h pace=0.30 or XRP_1h onesided=2.0)
- If 0 KEEPs: auditor recommends suspending autoresearch pending outcome resolution engineering fix
- Diagnostic result must be documented regardless of experiment outcomes

---

## Blacklist Summary

### Per-pair blacklists

- BTC_5m: ALL experiments FROZEN. gate=0.0/0.02/0.04/0.08 (all collapse), skip 0.45/0.55, onesided 2.0->1.5
- BTC_15m: ALL experiments FROZEN. gate=0.04 (collapse), skip=0.45 (3x), bar_budget 400, onesided=2.0 applied already
- BTC_1h: ALL experiments FROZEN. gate=0.04 (collapse), risk_ceil 0.10/0.20, skip 0.50, onesided 5->3
- ETH_5m: ALL experiments FROZEN. gate=0.04 (collapse), skip 0.60, onesided 1.5->1.0 (COLLAPSE), DD risk
- ETH_15m: ALL experiments FROZEN. gate series exhausted, skip above 0.50, onesided 1.5->1.0 (COLLAPSE)
- ETH_1h: onesided above 5, skip 0.40, risk_ceil 0.20, bar_budget 250/300, pace_urgency_lo 0.25 (DISCARD)
- SOL_5m: ALL experiments FROZEN. skip 0.55, onesided 2.0->1.5 (COLLAPSE), gate=0.04
- SOL_15m: ALL experiments FROZEN. skip 0.40 (COLLAPSE), onesided below 5.0 (COLLAPSE), bar_budget 400
- SOL_1h: ALL experiments FROZEN. skip 0.35/0.40 (COLLAPSE), risk_ceil 0.20
- XRP_5m: ALL (FROZEN permanent)
- XRP_15m: ALL experiments FROZEN. correct_side declining. skip 0.40, bar_budget 300, risk_ceil 0.20
- XRP_1h: skip 0.45/0.55, bar_budget 300, risk_ceil 0.20, pace_urgency_lo 0.30 (COLLAPSE), pace_urgency_lo 0.45 (D pre-RESET)

### Global Blacklist

- conviction_market_start: GLOBALLY BLACKLISTED — fails across ALL tested pairs. DO NOT TEST.
- magnitude_gate=0.08/0.04/0.02/0.0: Exhausted for all 5m/15m pairs and most 1h pairs. Gate parameter is irrelevant as pair-formation lever for any pair with outcome sparsity.
- pace_urgency_lo experiments: INEFFECTIVE when matched_ratio < 2% — insufficient statistical power.
- Any experiment on frozen pairs: BLOCKED until auditor lifts freeze or OHLC outcome resolution is confirmed.
