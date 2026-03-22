# Dutch Strategy
Updated: after iteration 10 (2026-03-22T07:45:00Z)

## Summary

10 iterations complete: 6 baselines + 4 experiments across BTC pairs + ETH baselines.
Overall KEEP rate: 0/4 non-baseline experiments = 0%.
ETH pair baselines now collected; SOL/XRP baselines pending (researcher at SOL_5m).

Critical systemic observations:
1. **sell_ratio=0.0 across ALL 10 iterations** — no sell events ever fire. Sell mechanism structurally inactive.
2. **BTC_1h pacing confirmed unhelpful**: 2 DISCARDs on different param categories (risk_ceil, pace_urgency_hi) — BTC_1h is already near its structural baseline floor.
3. **ETH_5m has lowest pair_cost baseline (0.9236)** but also lowest matched_ratio (0.4551) — asymmetry between fill quality and pair formation.
4. **unmatched_ratio=0.35 pre-staged** on ETH_5m and ETH_15m knobs — hypothesis ready to test.
5. **No KEEP experiments yet** — all experiments have worsened or matched baseline. Hypothesis quality must improve.

---

## BTC_5m (pair_cost=0.9676 baseline, KEEP rate 0/1=0%, max_dd=482.47%)

Current knobs: max_marginal_pair_cost=0.99, sell_loss_start=0.70, unmatched_ratio=0.50 (default)

**BLACKLIST for BTC_5m:**
- sell_loss_start — tightening (0.80->0.70) raised pair_cost +0.035 and max_dd +7.3%; premature exits blocked pair matching

**Priority queue (next experiments in order):**
1. `unmatched_ratio` 0.50->0.35 — matched_ratio=0.679 is below target. Tightening unmatched cap forces
   more pair completions. ETH_5m baseline with unmatched_ratio=0.35 already staged; BTC_5m should follow
   if ETH experiment shows improvement. NOTE: ETH_5m is running this first (cross-pair test).
2. `pace_urgency_lo` 0.5->0.35 — lower base pacing threshold to open orders earlier when prices are
   more favorable. 5m window is very tight; earlier ordering = better fill prices.
3. `conviction_market_start` 0.30->0.20 — lower conviction threshold to allow weaker-signal orders.
   Combined with unmatched_ratio tightening, should increase matched pair count.
4. `sweep_threshold` 0.01->0.005 — aggressive sweeping at cheap prices improves pair cost structurally.
   Only test after matched_ratio improves (currently 67.9% — not enough pairs to see sweep effect clearly).
5. `fill_ticks` 10->15 — more fill attempts per tick cycle; 5m bar leaves little time for retries.

Reasoning: BTC_5m's max_dd=482% is extremely high (all-time loss accumulation in backtest). The main
levers are pair formation (unmatched_ratio, conviction) and execution quality (sweep, fill_ticks).
Sell mechanism not firing means capital not recycling — once matched_ratio improves, sells may activate.

---

## BTC_15m (pair_cost=0.9631 baseline, KEEP rate 0/1=0%, max_dd=167.63%)

Current knobs: max_marginal_pair_cost=1.03, cheap_threshold=0.07, unmatched_ratio=0.50 (default)

**BLACKLIST for BTC_15m:**
- max_marginal_pair_cost < 1.01 — tightening to 0.99 collapsed matched_ratio 61%->8%; pair formation
  is highly sensitive. Step changes of <=0.01 only, never below 1.01 until matched_ratio >0.65 confirmed.

**Priority queue (next experiments in order):**
1. `pace_urgency_lo` 0.5->0.35 — 15m bars have more time than 5m; earlier pacing allows better price
   discovery. This is untested across all pairs; BTC_15m is good candidate for first test.
2. `unmatched_ratio` 0.50->0.40 — gentler reduction than ETH (0.35); BTC_15m's max_marginal_pair_cost
   is already at 1.03 (permissive), so pair formation is not blocked by cost guard. Moderate tightening
   of unmatched cap may improve without collapsing matched_ratio.
3. `cheap_threshold` 0.07->0.10 — current knob is tighter than default. Reverting allows more orders
   to qualify; verify this wasn't an intentional experiment result (may be researcher drift from V6).
4. `bar_budget` 200->175 — limit capital deployment per bar to reduce max_dd (currently 167.63%).
5. `max_marginal_pair_cost` 1.03->1.01 — ONLY after matched_ratio stable >0.65 for 3+ experiments.

Reasoning: BTC_15m monitor shows improvement (avg_pair_cost last 10 bars = 0.9505, improving vs 0.9631
baseline). Pacing and unmatched tuning are the next levers to test.

---

## BTC_1h (pair_cost=0.9382 baseline, KEEP rate 0/2=0%, max_dd=27.30%)

Current knobs: max_marginal_pair_cost=1.03, sell_loss_start=0.60, risk_ceil=0.15 (reverted from DISCARD)

**BLACKLIST for BTC_1h:**
- risk_ceil — reducing 0.15->0.10 worsened pair_cost (0.9382->0.9588) and raised max_dd 27.3->29.8%
- pace_urgency_hi — raising 2.0->2.5 produced zero improvement (pair_cost identical, profit still negative)

**Priority queue (next experiments in order):**
1. `unmatched_ratio` 0.50->0.40 — matched_ratio=0.674 at baseline. BTC_1h is the strongest pair; adding
   unmatched pressure should improve matching without destabilizing. Gentler than ETH's 0.35 test.
2. `max_marginal_pair_cost` 1.03->1.01 — BTC_1h has the best baseline pair_cost (0.9382). Tightening
   the marginal cost guard could improve average pair_cost. Test only if unmatched_ratio experiment passes.
3. `pace_urgency_lo` 0.5->0.35 — untested. 1h bars provide ample time; earlier pacing could improve
   fill price distribution across the bar.
4. `conviction_market_start` 0.30->0.25 — slight threshold reduction to allow marginal-signal orders.
   1h bars can absorb more attempts safely.

NOTE: sell_loss_start=0.60 already applied to BTC_1h knobs (pre-staged from iter 5 strategy). The
prior strategy suggested this as step 3; it was applied without an experiment. The next researcher run on
BTC_1h should either validate this is neutral/positive or roll back to 0.70.

Reasoning: BTC_1h is the healthiest pair (pair_cost 0.9382, max_dd 27.3%). Protect by making small
conservative changes. Both tested levers (risk_ceil, pace_urgency_hi) failed — risk and pacing are
not the constraint here. Pair formation quality is.

---

## ETH_5m (pair_cost=0.9236 BEST baseline, KEEP rate N/A — baseline only, max_dd=431.42%)

Current knobs: unmatched_ratio=0.35 (PRE-STAGED for next experiment), max_marginal_pair_cost=1.03

**Priority queue (next experiments in order):**
1. **EXPERIMENT NOW**: `unmatched_ratio` 0.50->0.35 — ALREADY STAGED in knobs_ETH_5m. This is the
   cross-pair hypothesis. ETH_5m's matched_ratio=0.4551 is the worst of all pairs — unmatched cap
   tightening is the highest-leverage intervention. Target: matched_ratio >0.55.
   If KEEP: apply same change to BTC_5m. If DISCARD: revert and try pace_urgency_lo first.
2. `pace_urgency_lo` 0.5->0.35 — if unmatched_ratio fails, earlier pacing in 5m window.
3. `conviction_market_start` 0.30->0.20 — lower bar for order qualification.

NOTE: ETH_5m has the BEST pair_cost baseline (0.9236) despite worst matched_ratio. This may indicate
the fill_simulator is performing well at cheap prices for ETH, but pair formation (both sides) is the
bottleneck. unmatched_ratio reduction directly addresses this.

---

## ETH_15m (pair_cost=0.9569 baseline, KEEP rate N/A — baseline only, max_dd=284.48%)

Current knobs: unmatched_ratio=0.35 (PRE-STAGED), max_marginal_pair_cost=1.03

Baseline metrics: matched_ratio=0.5602, fill_rate=0.8280, correct_side_pct=0.0556 (very low), sell_ratio=0.0

**Priority queue (next experiments in order):**
1. **EXPERIMENT NOW**: `unmatched_ratio` 0.50->0.35 — ALREADY STAGED in knobs_ETH_15m. Same hypothesis
   as ETH_5m. matched_ratio=0.5602 suggests there is room to push pair matching higher.
2. `pace_urgency_lo` 0.5->0.35 — if unmatched_ratio fails.
3. `conviction_market_start` 0.30->0.20 — lower conviction to allow more orders.

NOTE: correct_side_pct=0.0556 for ETH_15m is the lowest of all pairs (nearly random). This may indicate
the Pulse model for ETH_15m has very low directional accuracy in the backtest period. This is a model
quality issue, not a Dutch parameter issue. Flag for researcher to note — Dutch optimization cannot fix
poor model signal.

---

## ETH_1h (pair_cost=0.9626 baseline, KEEP rate N/A — baseline only, max_dd=102.03%)

Current knobs: unmatched_ratio=0.50 (default), max_marginal_pair_cost=1.03, sell_loss_start=0.70

Baseline metrics: matched_ratio=0.5611, avg_profit=-$8.50, correct_side_pct=0.0833, sell_ratio=0.0

**Priority queue (next experiments in order):**
1. `unmatched_ratio` 0.50->0.35 — researcher_ack confirms this is the pending hypothesis for ETH_1h.
   matched_ratio=0.5611. Apply and test.
2. `pace_urgency_lo` 0.5->0.35 — 1h bars; earlier ordering may improve fill distribution.
3. `conviction_market_start` 0.30->0.25 — slight reduction; 1h bars are safer for marginal orders.

NOTE: ETH_1h has the highest pair_cost (0.9626) of all ETH timeframes and worst avg_profit (-$8.50/bar).
This pair is the most challenging in the ETH group. The correct_side_pct=0.0833 is concerning (nearly
random directional accuracy). Priority: get baselines for SOL/XRP first, then return to ETH_1h
optimization once cross-pair patterns from unmatched_ratio test are clear.

---

## SOL_5m, SOL_15m, SOL_1h, XRP_5m, XRP_15m, XRP_1h

No data yet. Researcher is currently at SOL_5m (pair_index=6).

**Directive: Run BASELINES for all 6 remaining pairs in rotation order before any experiments.**

Expected baseline pattern (based on BTC/ETH learnings):
- sell_ratio=0.0 expected (systemic, not pair-specific)
- matched_ratio likely in 0.45-0.65 range
- pair_cost likely in 0.92-0.97 range (higher TF = lower pair_cost)
- correct_side_pct likely low (0.10-0.20) — consistent with BTC/ETH

After all 12 baselines complete, run full cross-pair unmatched_ratio=0.35 experiment batch.

---

## Cross-Pair Observations

1. **sell_ratio=0.0 is systemic** — 10 iterations, 0 sell events across all pairs and experiments.
   Root cause candidates: (a) sell_loss_start=0.70/0.60 is above market price range, (b) profit_protect_min_pairs=5
   is blocking sells (matched pairs below threshold), (c) sell mechanism requires higher matched_ratio first.
   ACTION: After matched_ratio improves via unmatched_ratio experiments, re-examine sell firing rates.

2. **max_marginal_pair_cost is an on/off switch** — BTC_15m DISCARD proved 1.03->0.99 is catastrophic.
   This param must move in <=0.01 increments. Only reduce when matched_ratio >0.65 for 3+ consecutive bars.

3. **Pacing params (urgency_hi) are ineffective** — BTC_1h test showed pace_urgency_hi 2.0->2.5 = zero
   effect. Likely because the engine already fills within bar window; urgency is not the binding constraint.
   Lower priority for all pairs; deprioritize in favor of structural pair-formation params.

4. **unmatched_ratio is the primary hypothesis** — all low matched_ratios (0.45-0.68) across pairs
   suggest the engine has too much latitude to hold single-side positions. Tightening to 0.35 forces more
   completions. Pre-staged on ETH_5m and ETH_15m; researcher should run these ASAP.

5. **ETH_5m anomaly** — best pair_cost (0.9236) despite worst matched_ratio (0.4551). Hypothesis:
   when pairs DO form on ETH_5m, they form at favorable prices; the issue is frequency, not quality.
   unmatched_ratio reduction should increase frequency without sacrificing price quality.

6. **BTC_1h structural floor** — 2 experiments, 0 KEEPs, both on different categories. BTC_1h may be
   at its structural optimization floor for current param space. Focus researcher effort on ETH/SOL/XRP.

7. **correct_side_pct is consistently low** (0.07-0.18 across all pairs) — well below the trader_a target
   of 0.55. This reflects the Pulse model's directional accuracy, not Dutch param quality. Dutch
   optimization cannot fix poor model predictions; this is a hard ceiling on performance.

---

## trader_a Benchmark Comparison

| Pair      | PairCost | Target  | Gap    | AvgProfit | MaxDD%   | Trend           |
|-----------|----------|---------|--------|-----------|----------|-----------------|
| BTC_5m    | 0.9676   | < 0.85  | +0.118 | -$5.63    | 482.47%  | baseline only   |
| BTC_15m   | 0.9631   | < 0.85  | +0.113 | -$5.88    | 167.63%  | improving (mon) |
| BTC_1h    | 0.9382   | < 0.85  | +0.088 | -$3.42    | 27.30%   | floor reached?  |
| ETH_5m    | 0.9236   | < 0.85  | +0.074 | -$4.79    | 431.42%  | best baseline   |
| ETH_15m   | 0.9569   | < 0.85  | +0.107 | -$6.25    | 284.48%  | baseline only   |
| ETH_1h    | 0.9626   | < 0.85  | +0.113 | -$8.50    | 102.03%  | baseline only   |
| SOL_5m    | N/A      | < 0.85  | N/A    | N/A       | N/A      | no data         |
| SOL_15m   | N/A      | < 0.85  | N/A    | N/A       | N/A      | no data         |
| SOL_1h    | N/A      | < 0.85  | N/A    | N/A       | N/A      | no data         |
| XRP_5m    | N/A      | < 0.85  | N/A    | N/A       | N/A      | no data         |
| XRP_15m   | N/A      | < 0.85  | N/A    | N/A       | N/A      | no data         |
| XRP_1h    | N/A      | < 0.85  | N/A    | N/A       | N/A      | no data         |

All 6 measured pairs are well above the 0.85 pair_cost target. Gap range: 0.074 (ETH_5m) to 0.118 (BTC_5m).
All pairs unprofitable at baseline. correct_side_pct far below 0.55 target on all pairs — structural model
quality ceiling. Zero pairs achieve any trader_a benchmark metric except max_dd on BTC_1h (27.3% < 30%).

---

## Blacklist (per-pair)

- **BTC_5m**: sell_loss_start (tightening raises pair_cost and dd; premature exits hurt matching)
- **BTC_15m**: max_marginal_pair_cost < 1.01 (destroys pair formation; matched_ratio collapses to 8%)
- **BTC_1h**: risk_ceil reduction (0.15->0.10 worsened pair_cost and max_dd); pace_urgency_hi increase (zero effect)
- **ETH_5m**: None yet
- **ETH_15m**: None yet
- **ETH_1h**: None yet
- **SOL/XRP**: None yet (no experiments)

## Global Blacklist

- **pace_urgency_hi increase** — confirmed ineffective on BTC_1h (zero delta vs baseline). Deprioritize
  across all pairs until structural pair formation improves.
- No other global blacklist candidates yet — need more cross-pair experiment data.

## Researcher Compliance

- researcher_ack iter=9 confirms ETH_1h BASELINE with next hypothesis: unmatched_ratio 0.50->0.35.
  This aligns with ETH_1h priority queue item #1. COMPLIANCE: PASS.
- ETH_5m and ETH_15m knobs pre-staged with unmatched_ratio=0.35 — researcher proactively applied the
  cross-pair hypothesis. This is ALIGNED with strategy (BTC learnings cross-applied). COMPLIANCE: PASS.
- BTC_1h has sell_loss_start=0.60 in current knobs (was suggested in iter 5 strategy as step 3).
  This was applied without running an isolated experiment. Acceptable as a pre-stage, but the researcher
  should run an explicit BTC_1h experiment to validate sell_loss_start=0.60 vs baseline 0.70.

## Next Actions (ordered by priority)

1. **SOL_5m BASELINE** — researcher is here now (pair_index=6). Run baseline, no knob changes.
2. **SOL_15m BASELINE** — next in rotation.
3. **SOL_1h BASELINE** — next.
4. **XRP_5m/15m/1h BASELINES** — complete the rotation.
5. **ETH_5m unmatched_ratio experiment** — STAGED, run immediately after reaching ETH_5m in rotation.
6. **ETH_15m unmatched_ratio experiment** — STAGED, run immediately after reaching ETH_15m in rotation.
7. **ETH_1h unmatched_ratio experiment** — run, researcher_ack confirms hypothesis.
8. After SOL/XRP baselines complete, update strategy for those pairs.
