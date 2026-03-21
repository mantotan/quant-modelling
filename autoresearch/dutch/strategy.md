# Dutch Strategy
Updated: after iteration 5 (2026-03-22T06:35:00Z)

## Summary

Early-stage optimization — 5 iterations total (3 baselines + 2 experiments), all on BTC pairs.
Zero experiments on ETH/SOL/XRP. Overall KEEP rate: 0/2 non-baseline = 0%.

Critical systemic observation: **sell_ratio=0.0 across all 5 experiments**. No sell events
are triggering in any pair. This may be by design (sell_loss_start=0.70 is conservative
threshold) but warrants investigation — if sells never fire, capital recycling is absent
and matched_ratio may be limited by one-sided accumulation.

---

## BTC_5m (pair_cost=0.9676 baseline, KEEP rate 0%, max_dd_pct=482.47)

Current knobs_BTC_5m: max_marginal_pair_cost=0.99, sell_loss_start=0.70

**BLACKLIST for BTC_5m:**
- sell_loss_start — tightening from 0.80->0.70 raised pair_cost (+0.035) and dd (+7.3%); premature exits prevented pair matching

**Priority queue (next experiments in order):**
1. `unmatched_ratio` 0.50->0.35 — matched_ratio is only 0.679; tightening unmatched cap forces
   engine to match more pairs rather than hold unmatched single-side positions. Target: matched_ratio >0.75.
2. `pace_urgency_hi` 2.0->2.5 — more aggressive pacing in the late bar window to fill the second
   side of open pairs before bar closes. 5m bars are short; urgency needs to be higher.
3. `conviction_market_start` 0.30->0.20 — lower conviction threshold to allow more orders from
   weaker signals. This paired with unmatched_ratio tightening could increase matched pairs.
4. `fill_ticks` 10->15 — allow more fill attempts per tick cycle; 5m bar window is tight.
5. `sweep_threshold` 0.01->0.005 — lower sweep threshold lets engine sweep more aggressively at
   cheap prices, improving pair cost.

Reasoning: BTC_5m's main problem is low matched_ratio (0.679) and pair_cost near 0.97. With
sell_ratio=0.0, the engine is never recycling capital. Pair formation is the bottleneck.

---

## BTC_15m (pair_cost=0.9631 baseline, KEEP rate 0%, max_dd_pct=167.63)

Current knobs_BTC_15m: max_marginal_pair_cost=1.03, cheap_threshold=0.07

**BLACKLIST for BTC_15m:**
- max_marginal_pair_cost tightening below 1.01 — lowering to 0.99 collapsed matched_ratio from
  61% to 8%; pair formation is extremely sensitive to this guard. Do NOT go below 1.01.

**Priority queue (next experiments in order):**
1. `cheap_threshold` 0.07->0.10 — current knob is already at 0.07 (tighter than default 0.10).
   Reverting to 0.10 allows slightly more orders; cross-check if it was changed experimentally
   or is default. NOTE: knobs_BTC_15m shows 0.07 but baseline knob showed 0.10 — verify
   whether this was researcher intent or file drift.
2. `pace_urgency_lo` 0.5->0.35 — reduce base pacing threshold to let engine place orders earlier
   in the bar when prices may be more favorable (lower pair cost).
3. `risk_ceil` 0.15->0.12 — moderate risk cap reduction; 15m bars have more time to match but
   drawdown (167.63) is elevated. Conservative risk ceiling may reduce per-bar risk.
4. `bar_budget` 200->175 — reduce total capital per bar to limit downside per cycle.
5. `max_marginal_pair_cost` 1.03->1.01 — only attempt AFTER matched_ratio is stable at >0.60.
   Current 1.03 is necessary minimum; tighten only when match rate is healthy.

Reasoning: BTC_15m baseline pair_cost=0.9631 is the second-best of BTC pairs. The backtest
environment (monitor report) shows avg=0.951 improving, but paper is stuck at 1.028. Focus on
pacing and budget to improve paper performance.

---

## BTC_1h (pair_cost=0.9382 baseline, KEEP rate N/A — only baseline, max_dd_pct=27.30%)

Current knobs_BTC_1h: max_marginal_pair_cost=1.03, risk_ceil=0.10 (already lowered from 0.15)

**BLACKLIST for BTC_1h:** None yet (only baseline run).

**Priority queue (next experiments in order):**
1. `risk_ceil` 0.15->0.10 — per researcher_ack, this is the pending hypothesis. BTC_1h max_dd
   is 27.3% (near 30% threshold). Lowering risk_ceil should reduce per-prediction exposure.
   NOTE: knobs_BTC_1h already shows risk_ceil=0.10, suggesting this may already be applied.
   Researcher should verify knobs_BTC_1h reflects current live params vs baseline snapshot.
2. `pace_urgency_hi` 2.0->2.5 — 1h bars have much more time; aggressive urgency at end ensures
   open pairs get matched before bar expires.
3. `sell_loss_start` 0.70->0.60 — unlike 5m, 1h bars give more time for pairs to develop.
   An earlier sell trigger on losing pairs may free capital for new positions. Try cautiously.
4. `max_marginal_pair_cost` 1.03->1.01 — BTC_1h has the best baseline pair cost (0.9382).
   If matched_ratio stays stable (0.674), tightening marginal cost may further reduce pair cost.
5. `conviction_market_start` 0.30->0.25 — lower conviction threshold slightly to allow more
   orders; 1h bars can absorb more attempts safely.

Reasoning: BTC_1h is the strongest baseline (pair_cost=0.9382, max_dd=27.3%). Protect this
pair's gains while experimenting conservatively. Risk_ceil reduction is highest priority.

---

## ETH_5m (no data — baseline pending)

Current knobs: default V7 params (pair_index=3, not yet reached in rotation).

**Priority queue:**
1. Run BASELINE first — no data available.
2. After baseline: same priority as BTC_5m unmatched_ratio test (cross-pair hypothesis).

---

## ETH_15m, ETH_1h, SOL_5m, SOL_15m, SOL_1h, XRP_5m, XRP_15m, XRP_1h

All pairs beyond ETH_5m have no experimental data. Run BASELINES in rotation order.
Once 2+ baselines per non-BTC asset are complete, revisit strategy for those pairs.

---

## Cross-Pair Observations

1. **sell_ratio=0.0 across all pairs**: No sell events have triggered on any pair. The
   sell_loss_start=0.70 threshold and sell_dump_start=0.90 may be too high for current market
   conditions, OR the sell mechanism requires a minimum number of pairs before activating
   (profit_protect_min_pairs=5). With matched_ratio at 0.60-0.68, there may not be enough
   matched pairs to trigger sells. Focus on increasing matched_ratio first.

2. **max_marginal_pair_cost is highly sensitive**: The 15m DISCARD proved that even 1.03->0.99
   destroys pair formation (matched_ratio 61%->8%). This param should be changed in steps of
   <=0.01 and never below 1.01 until matched_ratio is confirmed stable at >0.65.

3. **Paper vs backtest gap**: Monitor shows 15m paper avg_pair_cost=1.028 vs backtest=0.951.
   This suggests fill_simulator params are not well-calibrated to paper market conditions.
   Experiments changing fill_sim params (fill_ticks, sweep_threshold, chase_threshold) are
   high priority once baseline rotation completes.

4. **BTC_1h is the strongest performer**: pair_cost=0.9382, max_dd=27.3%. Shorter bars (5m)
   struggle more with pair formation in the available time window. Time pressure on 5m is a
   structural constraint — pace_urgency and fill_ticks are key levers there.

5. **Pacing params untested**: pace_urgency_lo/hi have not been varied yet. Given that unmatched
   ratios are low (0.60-0.68) and the 5m bar window is tight, urgency tuning is the next
   highest-potential lever after unmatched_ratio.

---

## trader_a Benchmark Comparison

| Pair     | PairCost | Target  | Gap    | AvgProfit | MaxDD%   | Trend         |
|----------|----------|---------|--------|-----------|----------|---------------|
| BTC_5m   | 0.9676   | < 0.85  | +0.118 | -$5.63    | 482.47   | baseline only |
| BTC_15m  | 0.9631   | < 0.85  | +0.113 | -$5.88    | 167.63   | baseline only |
| BTC_1h   | 0.9382   | < 0.85  | +0.088 | -$3.42    | 27.30%   | baseline only |
| ETH_*    | N/A      | < 0.85  | N/A    | N/A       | N/A      | no data       |
| SOL_*    | N/A      | < 0.85  | N/A    | N/A       | N/A      | no data       |
| XRP_*    | N/A      | < 0.85  | N/A    | N/A       | N/A      | no data       |

All BTC pairs are well above the 0.85 pair_cost target. The gap is largest for 5m/15m.
BTC_1h has the smallest gap (0.088). All pairs are unprofitable at baseline — expected,
as V7 defaults are starting points, not optimized for each pair.

---

## Blacklist (per-pair)

- **BTC_5m**: sell_loss_start (tightening raises pair_cost and dd; premature exits hurt matching)
- **BTC_15m**: max_marginal_pair_cost < 1.01 (destroys pair formation; matched_ratio collapses to 8%)
- **BTC_1h**: None yet
- **ETH/SOL/XRP**: None yet (no experiments)

## Global Blacklist

- None established yet (only 2 non-baseline experiments, each on different pairs).
  Once more data accumulates, cross-pair global blacklist will be populated.

## Researcher Compliance

- researcher_ack confirms iter=4 BTC_1h BASELINE with pending hypothesis: risk_ceil 0.15->0.10.
  This is aligned with BTC_1h priority queue item #1 above. Compliance: PASS.
- No previous strategy.md existed — this is the first strategist run. No compliance gap to check.
