# Dutch Strategy
Updated: after iteration 33 (2026-03-22T17:15:00Z) — STRATEGIST analysis

## Summary

V7.3 reset completed. All 12 pairs re-baselined with conviction-skip/sizing + one-sided cap config.
6/12 pairs profitable. Research now enters per-pair tuning phase on V7.3 baselines.

Key constraint: budget_util is 2-6% across all pairs (extremely low). The conviction filter is
doing its job (filtering bad trades) but also heavily suppressing capital deployment. The next
priority is understanding whether higher throughput is achievable without sacrificing pair quality.

---

## BTC_5m (pair_cost=0.948, KEEP rate N/A, max_dd=24%)
V7.3 baseline profitable: avg_profit=+$0.055/bar, correct_side=56%, matched_ratio=11%.

Priority queue:
1. conviction_buy_skip 0.50->0.45 — slightly lower threshold to capture more 45-50% confidence
   trades while keeping direction filter active. Expect matched_ratio increase; watch pair_cost.
2. bar_budget 200->300 — deploy more capital per bar if pair_cost stays under 0.95. BTC_5m has
   best correct%, safe to scale.
3. max_onesided_cost 5.0->7.0 — if conviction 0.45 causes more directional exposure, test if
   higher tail cap can absorb extra bars without blowing DD.

Blacklists (BTC_5m): unmatched_ratio tightening (DISCARD iter 16), sell_loss_start tightening
(DISCARD iter 1).

---

## BTC_15m (pair_cost=0.933, KEEP rate N/A, max_dd=23%)
V7.3 baseline profitable: avg_profit=+$0.498/bar, correct_side=63%, matched_ratio=12%.
Best correct_side across all pairs. Strong foundation.

Priority queue:
1. conviction_buy_skip 0.50->0.45 — 63% correct_side means even 45% confidence bets are likely
   directionally correct. Expect throughput gains with minimal pair_cost degradation.
2. bar_budget 200->300 — highest avg_profit per bar; deserves more capital deployment.
3. cheap_threshold 0.10->0.12 — slightly more liberal entry to increase matched pairs. Prior
   test (iter 17) showed 0.10->0.07 was a DISCARD; going looser in opposite direction.

Blacklists (BTC_15m): unmatched_ratio tightening, max_marginal_pair_cost below 1.01 (DISCARD
iter 3), cheap_threshold tightening to 0.07 (DISCARD iter 17).

---

## BTC_1h (pair_cost=0.938, KEEP rate N/A, max_dd=6%)
V7.3 baseline profitable: avg_profit=+$0.827/bar, correct_side=52%, matched_ratio=12%.
Lowest max_dd across all non-1h pairs. Excellent risk/reward.

Priority queue:
1. bar_budget 200->400 — lowest DD, highest profit/bar among BTC. Can afford to deploy more.
2. conviction_buy_skip 0.50->0.45 — 52% correct_side is marginal but positive; more throughput
   with slightly lower skip threshold should improve absolute profit.
3. risk_ceil 0.15->0.20 — already at 6% DD, room to increase per-bar risk allocation. Test
   whether fill rate improves with slightly looser risk ceiling.

Blacklists (BTC_1h): risk_ceil tightening to 0.10 (DISCARD iter 5), sell_loss_start tightening
to 0.60 (DISCARD iter 18), pace_urgency_hi loosening to 2.5 (no effect, iter 6).

---

## ETH_5m (pair_cost=0.909, KEEP rate N/A, max_dd=84%)
V7.3 baseline unprofitable: avg_profit=-$0.517/bar, correct_side=41%, matched_ratio=13%.
CRITICAL: correct_side_pct=41% is BELOW 50% — model is anti-predictive on this pair.

Priority queue:
1. conviction_buy_skip 0.50->0.60 — since model is anti-predictive at low confidence, skip more
   aggressively. Hypothesis: at 60% threshold, only high-confidence bets survive, which may be
   the rare cases where ETH_5m model is right.
2. max_onesided_cost 5.0->3.0 — tight cap since directional bets frequently wrong. Reduce tail
   exposure.
3. [HOLD] Do not invest further if conviction_buy_skip 0.60 still yields <0.47 correct_side.
   Pair may need to be disabled for live deployment.

Blacklists (ETH_5m): unmatched_ratio tightening (DISCARD iter 19).

---

## ETH_15m (pair_cost=0.922, KEEP rate N/A, max_dd=48%)
V7.3 baseline unprofitable: avg_profit=-$0.803/bar, correct_side=46%, matched_ratio=9%.
Near anti-predictive (46%). High DD suggests wrong-side accumulation still occurring.

Priority queue:
1. conviction_buy_skip 0.50->0.55 — lift threshold moderately; filter more 45-55% confidence
   bets where ETH_15m model is weakest.
2. max_onesided_cost 5.0->3.0 — reduce tail losses per directional event.
3. pace_urgency_lo 0.35->0.45 — researcher_ack noted this as next hypothesis. Later entry
   timing may improve fill prices on ETH_15m where market tends to move faster.

Note: researcher_ack suggested pace_urgency_lo for ETH_15m. This is 3rd priority; conviction
filter is more impactful given the directional accuracy problem.

Blacklists (ETH_15m): unmatched_ratio tightening (DISCARD iter 20).

---

## ETH_1h (pair_cost=0.953, KEEP rate N/A, max_dd=12%)
V7.3 baseline profitable: avg_profit=+$0.358/bar, correct_side=54%, matched_ratio=17%.
Highest matched_ratio among all pairs (17%) — most capital deployed per bar.

Priority queue:
1. conviction_buy_skip 0.50->0.45 — 54% correct and already highest throughput. Lower threshold
   to capture more 45-50% bets could increase absolute profit significantly.
2. max_onesided_cost 5.0->7.0 — DD only 12%, room to absorb higher per-event exposure.
3. bar_budget 200->300 — if conviction_buy_skip 0.45 tests positive, scale up budget.

---

## SOL_5m (pair_cost=0.946, KEEP rate N/A, max_dd=32%)
V7.3 baseline unprofitable: avg_profit=-$0.205/bar, correct_side=46%, matched_ratio=9%.
Near anti-predictive. Low fill rate (69%) adds friction.

Priority queue:
1. conviction_buy_skip 0.50->0.55 — filter more low-confidence SOL_5m bets.
2. max_onesided_cost 5.0->3.0 — reduce per-directional-event exposure.
3. fill_simulator.fill_ticks 10->15 — increase patience for SOL_5m fills; 69% fill rate
   suggests orders are expiring too quickly on this faster market.

---

## SOL_15m (pair_cost=0.935, KEEP rate N/A, max_dd=15%)
V7.3 baseline near-breakeven: avg_profit=-$0.245/bar, correct_side=50%, matched_ratio=6%.
50% correct_side = coin flip. Very low matched_ratio (6%) — throughput problem.

Priority queue:
1. conviction_buy_skip 0.50->0.40 — at exactly 50% correct_side, lower threshold will deploy
   more capital and may tip breakeven to positive (bilateral symmetry favors lower skip here).
2. min_unmatched_shares 10->5 — allow more unmatched accumulation to improve pair formation
   when prediction confidence is marginal.
3. bar_budget 200->300 — if throughput improves with lower skip, scale capital.

---

## SOL_1h (pair_cost=0.777, KEEP rate N/A, max_dd=9%)
V7.3 baseline profitable: avg_profit=+$0.084/bar, correct_side=54%, matched_ratio=2%.
EXCELLENT pair_cost=0.777 — best cost efficiency in the system. But matched_ratio=2% is
extremely low; almost no capital deployed per bar.

Priority queue:
1. conviction_buy_skip 0.50->0.35 — very low throughput, great cost. Aggressively lower
   threshold to deploy more capital while monitoring pair_cost stays under 0.85.
2. bar_budget 200->500 — if throughput increases, deploy much more capital; lowest DD and
   best cost justify it.
3. min_unmatched_shares 10->15 — allow more unmatched to build up pairs on this low-volume
   timeframe.

---

## XRP_5m (pair_cost=0.997, KEEP rate N/A, max_dd=67%)
V7.3 baseline unprofitable: avg_profit=-$0.398/bar, correct_side=43%, matched_ratio=4%.
CRITICAL: pair_cost=0.997 is dangerously close to max_marginal_pair_cost=1.01. Fill rate
only 58% — worst in system. Model anti-predictive (43%).

Priority queue:
1. fill_simulator.fill_ticks 10->15 — improve fill rate; 58% is far below 80%+ seen on other
   pairs. XRP_5m may need more patience for limit orders to fill.
2. conviction_buy_skip 0.50->0.60 — model at 43% correct is anti-predictive. Extreme skip
   threshold to only trade very high confidence signals.
3. max_onesided_cost 5.0->3.0 — cap losses tightly given poor model accuracy.

WARNING: If fill_ticks and conviction_buy_skip still show pair_cost near 1.0 and negative
avg_profit, XRP_5m may not be viable for live deployment.

---

## XRP_15m (pair_cost=0.956, KEEP rate N/A, max_dd=21%)
V7.3 baseline near-breakeven: avg_profit=-$0.146/bar, correct_side=52%, matched_ratio=14%.
52% correct_side is marginally positive. 14% matched_ratio is reasonable.

Priority queue:
1. conviction_buy_skip 0.50->0.45 — 52% correct means more trades could be profitable.
   Lower skip threshold to improve throughput on this marginal-but-positive signal.
2. max_onesided_cost 5.0->4.0 — mild reduction to control DD while testing throughput.
3. pace_urgency_lo 0.35->0.30 — even earlier entry may capture better prices on XRP_15m.

---

## XRP_1h (pair_cost=0.716, KEEP rate N/A, max_dd=6%)
V7.3 baseline profitable: avg_profit=+$0.512/bar, correct_side=57%, matched_ratio=3%.
BEST pair_cost in system (0.716). Low DD (6%). But very low throughput (3%).

Priority queue:
1. conviction_buy_skip 0.50->0.35 — same logic as SOL_1h: excellent cost and accuracy,
   need much more capital deployed.
2. bar_budget 200->500 — lowest pair_cost + second best correct_side = worthy of maximum
   capital deployment.
3. min_unmatched_shares 10->15 — allow more unmatched accumulation for this pair-starved TF.

---

## Cross-Pair Observations

**Parameters that work across ALL pairs (V7.3 baseline effects):**
- conviction_buy_skip=0.50 + conviction_size_floor=0.30 are the core value driver. Every
  profitable pair shows pair_cost below 0.96. Pre-V7.3 no pair achieved this.
- max_marginal_pair_cost=1.01 is critical — BTC_15m experiment showed tightening to 0.99
  collapsed matched_ratio 61->8%. This value must not move.
- spread_offset=0.00 (place at bid) consistently better than 0.01.

**Parameters to avoid across ALL pairs (global blacklists from pre-V7.3 experiments):**
- unmatched_ratio tightening (0.50->0.35): 3/3 DISCARDs, worsened pair_cost and doubled DD.
- sell_loss_start tightening (0.70->0.60): 2/2 DISCARDs, disrupted pair formation.
- pace_urgency_hi loosening: no effect even when tried.

**Asset-specific patterns:**
- BTC pairs: Best directional signal quality (52-63% correct). Scale up is safe.
- 1h pairs: Consistently lowest DD (6-12%) and best pair_cost (0.72-0.95). 1h bars give
  more time for pairs to form and prices to mean-revert.
- 5m pairs: Highest noise. ETH/XRP/SOL 5m all anti-predictive (<47% correct). BTC_5m is
  the exception (56% correct).
- ETH pairs: Weakest model signal. ETH_5m at 41% is worst in system.

**Throughput is now the binding constraint for profitable pairs.** All profitable pairs have
budget_util of 2-6% — severely under-deploying capital. The conviction filter is working but
too aggressively for the best pairs. Priority is to lower conviction_buy_skip on profitable
pairs (to 0.40-0.45) and increase bar_budget on confirmed performers (BTC, 1h TFs).

---

## trader_a Benchmark Comparison
| Pair | PairCost | Target | Gap | AvgProfit | MaxDD% | Trend |
|------|----------|--------|-----|-----------|--------|-------|
| BTC_5m | 0.948 | < 0.85 | +0.098 | +$0.06 | 24% | profitable, needs scale |
| BTC_15m | 0.933 | < 0.85 | +0.083 | +$0.50 | 23% | best overall |
| BTC_1h | 0.938 | < 0.85 | +0.088 | +$0.83 | 6% | best profit/bar |
| ETH_5m | 0.909 | < 0.85 | +0.059 | -$0.52 | 84% | anti-predictive model |
| ETH_15m | 0.922 | < 0.85 | +0.072 | -$0.80 | 48% | weak signal |
| ETH_1h | 0.953 | < 0.85 | +0.103 | +$0.36 | 12% | profitable, needs scale |
| SOL_5m | 0.946 | < 0.85 | +0.096 | -$0.21 | 32% | weak signal |
| SOL_15m | 0.935 | < 0.85 | +0.085 | -$0.25 | 15% | near-breakeven |
| SOL_1h | 0.777 | < 0.85 | -0.073 | +$0.08 | 9% | BEATS benchmark cost! |
| XRP_5m | 0.997 | < 0.85 | +0.147 | -$0.40 | 67% | worst cost, anti-pred |
| XRP_15m | 0.956 | < 0.85 | +0.106 | -$0.15 | 21% | near-breakeven |
| XRP_1h | 0.716 | < 0.85 | -0.134 | +$0.51 | 6% | BEATS benchmark cost! |

SOL_1h and XRP_1h are the ONLY pairs beating the trader_a pair_cost benchmark of <0.85.
These should be scaled aggressively. All other pairs are above the benchmark but the 1h TFs
and BTC pairs are improving. ETH/XRP 5m remain structurally challenged.

---

## Blacklist (per-pair)

- BTC_5m: unmatched_ratio tightening, sell_loss_start tightening
- BTC_15m: unmatched_ratio tightening, max_marginal_pair_cost below 1.01, cheap_threshold tightening
- BTC_1h: risk_ceil tightening, sell_loss_start tightening, pace_urgency_hi loosening
- ETH_5m: unmatched_ratio tightening
- ETH_15m: unmatched_ratio tightening
- All others: no pair-specific blacklists yet (new on V7.3)

## Global Blacklist
- unmatched_ratio tightening: 3/3 DISCARDs across BTC_5m, ETH_5m, ETH_15m
- sell_loss_start tightening: 2/2 DISCARDs across BTC_5m, BTC_1h
- max_marginal_pair_cost tightening below 1.01: 1/1 DISCARD, collapses matched_ratio
- pace_urgency_hi loosening: zero effect observed

## Researcher Compliance
researcher_ack (iter 20) noted pace_urgency_lo as next hypothesis for ETH_15m. This is
acceptable as 3rd priority for ETH_15m but conviction_buy_skip 0.55 should come first
given the directional accuracy problem. Researcher should follow the per-pair priority queue
above for the next rotation starting with BTC_5m.
