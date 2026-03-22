# Dutch Strategy
Updated: after iteration 46 (2026-03-22T22:55:00Z) — STRATEGIST analysis

## Summary

Second full rotation complete on V7.3 baselines (iters 21-46). Overall KEEP rate: 4/12 = 33%.
Key findings from this rotation:

1. **Lowering conviction_buy_skip to 0.45 works on 1h TFs and XRP_15m** — ETH_1h improved
   pair_cost 25.9% (0.9528->0.7058), XRP_15m improved 18.6% (0.9558->0.7780). Both KEEP.
2. **Raising conviction_buy_skip (to 0.55-0.60) consistently fails** — 3/3 DISCARDs for ETH_5m,
   ETH_15m, SOL_5m. Filtering more aggressively hurts all metrics. Do NOT raise skip threshold.
3. **BTC_5m anomaly**: Lowering skip to 0.45 was DISCARD (max_dd doubled). Different from 1h/XRP
   behavior. BTC_5m needs different approach.
4. **bar_budget increase fails**: BTC_1h 200->400 DISCARD — reduces fill quality. Budget floor
   should stay at 200 until throughput issue is better understood.
5. **3 benchmark-beating pairs now confirmed**: SOL_1h (0.6967), XRP_1h (0.7157), XRP_15m (0.7780),
   ETH_1h (0.7058) — 4 pairs now below 0.85 target.

---

## BTC_5m (pair_cost=0.948, KEEP rate 0/1=0%, max_dd=24%)
V7.3 baseline profitable: avg_profit=+$0.055/bar, correct_side=56%, matched_ratio=11%.
Lowering conviction_buy_skip to 0.45 was DISCARD (avg_profit went negative, max_dd doubled to 54%).
BTC_5m is sensitive to skip direction in opposite way from 1h pairs.

Priority queue:
1. conviction_buy_skip 0.50->0.55 — since 0.45 failed, try tighter filter. 56% correct_side means
   high-confidence signals are better-than-average directional. Expect lower throughput but better
   pair quality. Watch matched_ratio doesn't collapse below 5%.
2. bar_budget 200->300 — if conviction 0.55 stabilizes pair_cost, test budget scaling carefully.
   Use 300 (not 400) to avoid the fill quality degradation seen on BTC_1h at 400.
3. cheap_threshold 0.10->0.12 — slightly more liberal entry to increase matched pairs. Note: prior
   test (iter 17) showed tightening to 0.07 failed; try loosening direction.

Blacklists (BTC_5m): unmatched_ratio tightening, sell_loss_start tightening,
conviction_buy_skip 0.45 (DISCARD iter 33).

---

## BTC_15m (pair_cost=0.933, KEEP rate 0/1=0%, max_dd=23%)
V7.3 baseline profitable: avg_profit=+$0.498/bar, correct_side=63%, matched_ratio=12%.
Best correct_side across all pairs. Iter 35 was a re-run DISCARD (dataset variance, not real experiment).
No real conviction_buy_skip test done yet on V7.3 baseline.

Priority queue:
1. conviction_buy_skip 0.50->0.45 — 63% correct_side is highest in system. Lower threshold should
   add trades that are net positive while maintaining direction advantage. Note: this is NOT tested on
   V7.3 baseline yet (iter 35 was a re-run, not a skip change). Expect pair_cost improvement.
2. bar_budget 200->300 — if conv skip 0.45 works, scale capital modestly.
3. cheap_threshold 0.10->0.12 — slightly looser entry threshold for more pair formation.

Blacklists (BTC_15m): unmatched_ratio tightening, max_marginal_pair_cost below 1.01,
cheap_threshold tightening to 0.07.

---

## BTC_1h (pair_cost=0.938, KEEP rate 0/1=0%, max_dd=6%)
V7.3 baseline profitable: avg_profit=+$0.827/bar, correct_side=52%, matched_ratio=12%.
bar_budget 200->400 DISCARD (iter 36): pair_cost worsened, avg_profit cut 38%.
Budget increase hurts fill quality. Need different lever.

Priority queue:
1. conviction_buy_skip 0.50->0.45 — analogous to ETH_1h which KEEPed with 0.45 (pair_cost 0.9528->
   0.7058). 1h bars give more time for selective pair formation; lower skip should help throughput.
   52% correct_side is marginal but positive at 1h resolution.
2. risk_ceil 0.15->0.20 — with only 6% max_dd, room to increase per-bar risk allocation slightly.
   Prior test tightened to 0.10 (DISCARD iter 5) — try loosening to 0.20 instead.
3. cheap_threshold 0.10->0.12 — more liberal entry to increase matched pairs.

Blacklists (BTC_1h): risk_ceil tightening to 0.10, sell_loss_start tightening to 0.60,
pace_urgency_hi loosening to 2.5, bar_budget increase to 400.

---

## ETH_5m (pair_cost=0.909, KEEP rate 0/1=0%, max_dd=84%)
V7.3 baseline unprofitable: avg_profit=-$0.517/bar, correct_side=41%, matched_ratio=13%.
CRITICAL: correct_side=41% is anti-predictive. Raising conviction_buy_skip to 0.60 failed (iter 37):
all metrics worsened. Neither filtering direction works for ETH_5m.

Priority queue:
1. max_onesided_cost 5.0->2.0 — aggressive cap on directional exposure. With anti-predictive model,
   the core problem is taking large wrong-side positions. Cap at $2 per directional event to stop DD.
2. conviction_size_floor 0.30->0.50 — force minimum order size higher so only the most confident
   signals deploy capital. Combined with skip=0.50, should reduce total wrong-side exposure.
3. [HOLD AGGRESSIVE] If max_onesided_cost and size_floor still yield correct_side < 0.45, consider
   flagging ETH_5m for DISABLE in live deployment. Anti-predictive model cannot be fixed by tuning.

Blacklists (ETH_5m): unmatched_ratio tightening, conviction_buy_skip any direction (both 0.45
hypothesis untested here, but raising to 0.60 definitively failed — iter 37).

---

## ETH_15m (pair_cost=0.922, KEEP rate 0/1=0%, max_dd=48%)
V7.3 baseline unprofitable: avg_profit=-$0.803/bar, correct_side=46%, matched_ratio=9%.
Raising conviction_buy_skip to 0.55 failed (iter 38): improved pair_cost but worsened correct_side
(45.7%->34.7%), avg_profit negative, max_dd rose. Filtering more does not help.

Priority queue:
1. conviction_buy_skip 0.50->0.45 — since raising failed, try LOWERING. Analogous to ETH_1h/XRP_15m
   pattern where 0.45 improved metrics. ETH_15m has 46% correct — may be near inflection point where
   adding volume tips positive. Watch pair_cost carefully.
2. max_onesided_cost 5.0->3.0 — cap directional losses to reduce DD from 48%.
3. pace_urgency_lo 0.35->0.45 — later entry timing may improve fill prices on ETH_15m. Researcher_ack
   flagged this as next hypothesis.

Blacklists (ETH_15m): unmatched_ratio tightening, conviction_buy_skip raising to 0.55.

---

## ETH_1h (pair_cost=0.706, KEEP rate 2/2=100%, max_dd=17%)
V7.3 + 2 KEEPs: pair_cost dramatically improved 0.9528->0.7058, avg_profit=-$0.49/bar (marginal).
Best KEEP rate in system (100%). conviction_buy_skip=0.45 confirmed as better than 0.50.
pair_cost=0.706 now BEATS trader_a benchmark of 0.85.

Priority queue:
1. conviction_buy_skip 0.45->0.40 — ETH_1h has shown each reduction in skip improves cost. Test
   whether going to 0.40 continues the trend. Watch: correct_side was already 43.3% at 0.45 and
   declining — a further drop below 40% would be concerning.
2. bar_budget 200->300 — pair_cost now benchmark-beating. Safe to deploy more capital to this pair.
3. max_onesided_cost 5.0->7.0 — max_dd=17%, room to allow higher per-event exposure.

Note: Be cautious — correct_side 46.7% (V7.3) -> 43.3% (skip=0.45). Each skip reduction lets in
more marginal trades. If 0.40 drops correct_side below 40%, revert to 0.45 and stop skip testing.

---

## SOL_5m (pair_cost=0.946, KEEP rate 0/1=0%, max_dd=32%)
V7.3 baseline unprofitable: avg_profit=-$0.205/bar, correct_side=46%, matched_ratio=9%.
Raising conviction_buy_skip to 0.55 was DISCARD (iter 41): pair_cost worsened, max_dd tripled (32->108%).
Consistent with ETH_5m and ETH_15m — raising skip does not help.

Priority queue:
1. conviction_buy_skip 0.50->0.45 — since raising failed, test lowering. correct_side=46% is near
   breakeven; more trades may tip positive if matched_ratio improves selectively.
2. max_onesided_cost 5.0->3.0 — reduce per-directional-event exposure to control max_dd.
3. fill_ticks 10->15 — 69% fill rate is below system average. More patience for limit fills on SOL_5m.

Blacklists (SOL_5m): conviction_buy_skip raising to 0.55.

---

## SOL_15m (pair_cost=0.935, KEEP rate 0/1=0%, max_dd=15%)
V7.3 baseline near-breakeven: avg_profit=-$0.245/bar, correct_side=50%, matched_ratio=6%.
min_unmatched_shares 10->5 DISCARD (iter 42): worsened pair_cost vs fresh baseline.
50% correct_side = coin flip. Very low throughput (6%).

Priority queue:
1. conviction_buy_skip 0.50->0.45 — at 50% correct_side, more throughput may tip marginal positive.
   SOL_15m matches the XRP_15m profile that responded well to 0.45 skip (KEEP iter 46).
2. bar_budget 200->300 — if skip 0.45 works, scale capital on this low-DD pair.
3. pace_urgency_lo 0.35->0.30 — earlier entry timing to capture better prices at bar start.

Blacklists (SOL_15m): min_unmatched_shares tightening.

---

## SOL_1h (pair_cost=0.697, KEEP rate 1/1=100%, max_dd=9%)
V7.3 + 1 KEEP: pair_cost improved to 0.6967, avg_profit=+$0.817/bar on 32 bars.
EXCELLENT: Best pair_cost in system. Beats trader_a benchmark by 22%.

Priority queue:
1. conviction_buy_skip 0.50->0.45 — replicating ETH_1h/XRP_15m success pattern. SOL_1h has 57%
   correct_side and excellent pair_cost — test whether lower skip adds profitable throughput.
2. bar_budget 200->400 — lowest DD (9%) and best avg_profit ($0.817). Deserves maximum capital.
   BTC_1h showed 200->400 DISCARD, but SOL_1h has much lower matched_ratio (5%), so budget headroom
   is not the binding constraint here — test carefully.
3. min_unmatched_shares 10->15 — allow more unmatched accumulation to build pairs on this low-volume
   1h timeframe.

---

## XRP_5m (pair_cost=0.909, KEEP rate 1/1=100%, max_dd=69%)
V7.3 + 1 KEEP (re-eval): pair_cost improved 8.9% (0.9973->0.9085) on extended dataset.
Still unprofitable: avg_profit=-$0.323/bar, correct_side=45%, fill_rate=54% (worst in system).

Priority queue:
1. conviction_buy_skip 0.50->0.45 — XRP_15m showed 0.45 dramatically improved both pair_cost and
   avg_profit. Test same direction for XRP_5m despite lower fill rate.
2. fill_ticks 15 (already set) — knobs confirm fill_ticks=15 already applied. Check if this is
   helping; if fill_rate still 54%, test fill_ticks=20.
3. max_onesided_cost 5.0->3.0 — reduce max_dd from 69%.

Note: XRP_5m has fill_ticks=15 already in current knobs (vs 10 for other pairs). fill_rate at 54%
suggests the XRP_5m market structure makes limit fills harder. This may be a structural constraint.

---

## XRP_15m (pair_cost=0.778, KEEP rate 1/2=50%, max_dd=17%)
V7.3 + 1 KEEP: conviction_buy_skip 0.50->0.45 dramatically improved pair_cost 18.6% (0.9558->0.7780),
avg_profit turned positive (+$0.010/bar). BEATS trader_a benchmark.

Priority queue:
1. conviction_buy_skip 0.45->0.40 — continue the skip reduction series that worked. Monitor whether
   correct_side (33.3% at 0.45) drops further below 30% — inflection risk.
2. bar_budget 200->300 — pair_cost benchmark-beating, avg_profit positive. Safe to scale.
3. pace_urgency_lo 0.35->0.30 — earlier entry timing to improve fill prices.

Note: correct_side dropped sharply from 52% (baseline) to 33.3% (skip=0.45). More skip reduction
risks further correct_side degradation. The avg_profit +$0.010 is very marginal. If 0.40 drops
correct_side below 28%, halt skip reduction for XRP_15m and investigate.

---

## XRP_1h (pair_cost=0.716, KEEP rate N/A, max_dd=6%)
V7.3 baseline profitable: avg_profit=+$0.512/bar, correct_side=57%, matched_ratio=3%.
BEST pair_cost in system (0.716). No experiments done yet beyond baseline.

Priority queue:
1. conviction_buy_skip 0.50->0.45 — following the 1h pattern that works across ETH_1h and XRP_15m.
   XRP_1h has 57% correct (best 1h signal quality). Expect strong improvement from lower skip.
2. bar_budget 200->500 — lowest pair_cost + highest correct_side (1h tier). Maximum capital justified
   if throughput improves with lower skip.
3. min_unmatched_shares 10->15 — 1h timeframes benefit from more accumulation patience.

---

## Cross-Pair Observations

**Confirmed working across 1h TFs and XRP_15m: conviction_buy_skip 0.45**
- ETH_1h: pair_cost 0.9528->0.7058 (KEEP, iter 40)
- XRP_15m: pair_cost 0.9558->0.7780 (KEEP, iter 46)
- Pattern: Slower bars (1h, 15m) with reasonable correct_side (33-47%) respond well to lower skip.
  More trades at 45-50% confidence still contribute positively when bar timing is forgiving.

**Definitively failed: raising conviction_buy_skip above 0.50**
- ETH_5m 0.60 DISCARD, ETH_15m 0.55 DISCARD, SOL_5m 0.55 DISCARD.
- Pattern: Filtering more aggressively on anti-predictive/near-50% pairs does NOT help.
  The surviving high-confidence signals are not materially better than average.

**Mixed: conviction_buy_skip 0.45 on 5m TFs**
- BTC_5m 0.45 DISCARD (max_dd doubled, avg_profit negative).
- XRP_5m 0.45 not yet tested. SOL_5m 0.45 not yet tested.
- Hypothesis for 5m: Faster bars mean more directional exposure from lower-confidence trades
  compounds faster into drawdown. 5m pairs may need 0.50 or slightly above.

**bar_budget increase fails**: BTC_1h 200->400 DISCARD. Keep at 200 for now.

**Asset patterns confirmed:**
- 1h TFs: Consistently best pair_cost (0.70-0.94). Low DD (6-17%). Respond to skip=0.45.
- BTC pairs: Best correct_side (52-63%). Scale-up is the right direction.
- ETH/SOL 5m: Anti-predictive to near-coin-flip. Hard to tune. Focus on cost control.
- XRP: Volatile fill behavior (XRP_5m has 54% fill rate vs 80%+ for others).

---

## trader_a Benchmark Comparison (post-iter-46 best_knobs)
| Pair | PairCost | Target | Gap | AvgProfit | MaxDD% | Trend |
|------|----------|--------|-----|-----------|--------|-------|
| BTC_5m | 0.948 | < 0.85 | +0.098 | +$0.06 | 24% | stagnant — need new lever |
| BTC_15m | 0.933 | < 0.85 | +0.083 | +$0.50 | 23% | skip=0.45 untested, high potential |
| BTC_1h | 0.938 | < 0.85 | +0.088 | +$0.83 | 6% | skip=0.45 next (ETH_1h analog) |
| ETH_5m | 0.909 | < 0.85 | +0.059 | -$0.52 | 84% | anti-predictive, cost cap needed |
| ETH_15m | 0.922 | < 0.85 | +0.072 | -$0.80 | 48% | try skip=0.45, onesided cap |
| ETH_1h | 0.706 | < 0.85 | -0.144 | -$0.49 | 17% | BEATS benchmark, marginal profit |
| SOL_5m | 0.946 | < 0.85 | +0.096 | -$0.21 | 32% | try skip=0.45 |
| SOL_15m | 0.935 | < 0.85 | +0.085 | -$0.25 | 15% | try skip=0.45 (XRP_15m analog) |
| SOL_1h | 0.697 | < 0.85 | -0.153 | +$0.82 | 9% | BEATS benchmark, scale up |
| XRP_5m | 0.909 | < 0.85 | +0.059 | -$0.32 | 69% | fill_ticks=15 set; try skip=0.45 |
| XRP_15m | 0.778 | < 0.85 | -0.072 | +$0.01 | 17% | BEATS benchmark, skip=0.40 next |
| XRP_1h | 0.716 | < 0.85 | -0.134 | +$0.51 | 6% | BEATS benchmark, skip=0.45 priority |

**4 pairs now beating trader_a pair_cost benchmark**: SOL_1h, XRP_1h, ETH_1h, XRP_15m.
Next rotation should focus on replicating the skip=0.45 win on remaining 1h pairs (BTC_1h) and
testing skip=0.45 on all untested pairs.

---

## Blacklist (per-pair)

- BTC_5m: unmatched_ratio tightening, sell_loss_start tightening, conviction_buy_skip 0.45
- BTC_15m: unmatched_ratio tightening, max_marginal_pair_cost below 1.01, cheap_threshold to 0.07
- BTC_1h: risk_ceil tightening, sell_loss_start tightening, pace_urgency_hi loosening, bar_budget to 400
- ETH_5m: unmatched_ratio tightening, conviction_buy_skip raising (any direction — both 0.45 untested,
  0.60 definitively failed)
- ETH_15m: unmatched_ratio tightening, conviction_buy_skip raising to 0.55
- SOL_5m: conviction_buy_skip raising to 0.55
- SOL_15m: min_unmatched_shares tightening

## Global Blacklist
- unmatched_ratio tightening: 3/3 DISCARDs across BTC_5m, ETH_5m, ETH_15m
- sell_loss_start tightening: 2/2 DISCARDs (BTC_5m, BTC_1h)
- max_marginal_pair_cost tightening below 1.01: collapses matched_ratio
- pace_urgency_hi loosening: zero effect
- conviction_buy_skip RAISING above 0.50: 3/3 DISCARDs (ETH_5m, ETH_15m, SOL_5m)
- bar_budget doubling (200->400): 1/1 DISCARD (BTC_1h), reduces fill quality

## Priority Order for Next Rotation

High confidence (replicate known win pattern: skip=0.45):
1. BTC_1h: conviction_buy_skip 0.50->0.45 (ETH_1h analog — same TF, similar structure)
2. XRP_1h: conviction_buy_skip 0.50->0.45 (best pair_cost, needs throughput)
3. SOL_1h: conviction_buy_skip 0.50->0.45 (benchmark-beating pair, extend gains)
4. BTC_15m: conviction_buy_skip 0.50->0.45 (63% correct, high potential, untested on V7.3)
5. SOL_15m: conviction_buy_skip 0.50->0.45 (XRP_15m analog — near-breakeven 15m)

Medium confidence (new territory):
6. ETH_15m: conviction_buy_skip 0.50->0.45 (since raising 0.55 failed, try other direction)
7. XRP_15m: conviction_buy_skip 0.45->0.40 (continue series on benchmark-beating pair)
8. ETH_1h: conviction_buy_skip 0.45->0.40 (continue series, watch correct_side floor)

Cost control for struggling pairs:
9. ETH_5m: max_onesided_cost 5.0->2.0 (stop DD on anti-predictive pair)
10. XRP_5m: conviction_buy_skip 0.50->0.45 (test if XRP responds like XRP_15m)
11. BTC_5m: conviction_buy_skip 0.50->0.55 (opposite direction since 0.45 failed)
12. SOL_5m: conviction_buy_skip 0.50->0.45 (test direction reversal from 0.55 DISCARD)

## Researcher Compliance

researcher_ack (iter 45) indicated next hypothesis for XRP_15m was conviction_buy_skip 0.50->0.45.
This was executed correctly (iter 46, KEEP). Researcher is compliant with priority queue.

For next rotation, researcher should start with BTC_5m (pair_index=0) and follow the priority
order above for each pair encountered. The skip=0.45 hypothesis should be tested first on all
pairs where it has NOT been tested yet on V7.3 baseline.
