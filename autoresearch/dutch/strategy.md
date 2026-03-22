# Dutch Strategy
Updated: after iteration 71 (2026-03-23T17:10:00Z) — STRATEGIST analysis

## Summary

Fourth full rotation complete on V7.3 (iters 59-71). KEEP rate this rotation: 6/13 = 46%.
Overall V7.3 KEEP rate (iters 33-71): 17/38 = 45%.

Key findings from rotation 4:
1. **skip=0.40 series shows diminishing returns**: BTC_1h KEEP (8.3% improvement, iter 64), but ETH_1h
   DISCARD (iter 69, +2.2% regression). XRP_15m DISCARD (iter 60, collapsed pair formation). Pattern:
   skip=0.40 works for BTC_1h (59% correct_side at skip=0.45), fails for ETH_1h (already at floor),
   fails for XRP_15m (collapse). Skip series exhausted on most 15m/1h pairs.
2. **SOL_5m breakthrough**: Both re-eval (KEEP, iter 70, 6%) and skip=0.45 (KEEP, iter 71, 8.4%)
   succeeded. SOL_5m now at 0.814 pair_cost — approaching benchmark. avg_profit turned positive.
3. **ETH_5m recovers**: Re-eval (KEEP, iter 65) + skip=0.45 (KEEP, iter 66). ETH_5m now at 0.782,
   but correct_side=37.3% is dangerously near anti-predictive threshold.
4. **ETH_15m max_onesided_cost fix**: Halved max_dd from 54.5%->32.5%, improved pair_cost 6.3% (KEEP,
   iter 68). Critical DD intervention successful.
5. **XRP_1h skip=0.55 DISCARD**: Confirmed XRP_1h optimum is at skip=0.50. Both directions exhausted.
6. **BTC_5m cheap_threshold 0.12 DISCARD**: Only 0.38% improvement, max_dd still exceeded threshold.
   BTC_5m remains at skip=0.50, both skip directions and cheap_threshold exhausted.

Current state (post-iter-71 best_knobs):
- 10/12 pairs now at skip=0.45 or better (BTC_5m and XRP_1h remain at skip=0.50)
- BTC_1h now at skip=0.40 (pair_cost=0.799)
- SOL_5m at skip=0.45 (pair_cost=0.814)
- ETH_5m at skip=0.45 (pair_cost=0.782)

---

## BTC_5m (pair_cost=0.948, KEEP rate 0/5=0%, max_dd=24%)
V7.3 best: avg_profit=+$0.055/bar, correct_side=56%, matched_ratio=11%.
BOTH skip directions exhausted (0.45 DISCARD iter 33, 0.55 DISCARD iter 50).
cheap_threshold 0.12 DISCARD (iter 62) — minimal gain, DD exceeds 30%.
cheap_threshold 0.07 DISCARD (iter 17) — also failed in pre-V7.3.

Priority queue:
1. risk_ceil 0.15->0.20 — max_dd only 24%, still below 30%. Increasing per-bar capital allocation
   on a directionally profitable pair (56% correct_side, +$0.055/bar) may compound gains.
   This is the most logical untested lever for BTC_5m.
2. pace_urgency_lo 0.35->0.45 — later entry timing. 5m bars move fast; delaying the urgency
   gate may improve fill prices on this fast-moving asset.
3. max_onesided_cost 5.0->3.0 — cap directional exposure to reduce DD risk if risk_ceil test
   triggers DD increase. Combine if needed.

Blacklists (BTC_5m): unmatched_ratio tightening, sell_loss_start tightening,
conviction_buy_skip 0.45 (D iter 33), conviction_buy_skip 0.55 (D iter 50),
cheap_threshold 0.07 (D iter 17), cheap_threshold 0.12 (D iter 62).
NOTE: BOTH skip directions and BOTH cheap_threshold directions exhausted.

---

## BTC_15m (pair_cost=0.933, KEEP rate 0/3=0%, max_dd=23%)
V7.3 best: avg_profit=+$0.498/bar, correct_side=63%, matched_ratio=12%.
skip=0.45 marginal (DD=37.9%, DISCARD iter 51). bar_budget=300 worsened pair_cost (DISCARD iter 63).
cheap_threshold 0.07 DISCARD (iter 17). No re-eval on enlarged dataset yet.

Priority queue:
1. Re-evaluate V7.3 baseline on enlarged dataset (now ~130+ bars) — last clean baseline was iter 22
   at 97 bars. Dataset growth may have improved metrics naturally (as seen in BTC_1h, ETH_5m, SOL_5m).
   If re-eval shows >5% improvement, KEEP and unlock further experiments.
2. conviction_buy_skip 0.50->0.45 WITH max_onesided_cost 5.0->3.0 — compound change to get cost
   improvement without the DD penalty seen at iter 51. The cost gain (1.4%) was real; the DD was
   the problem. Combining with onesided cap may contain DD.
3. risk_ceil 0.15->0.20 — 23% max_dd provides headroom. BTC_15m at 63% correct_side is strongest
   directional pair; more capital per bar may tip total_profit higher.

Blacklists (BTC_15m): unmatched_ratio tightening, max_marginal_pair_cost below 1.01,
cheap_threshold to 0.07, bar_budget 300 (iter 63 regression), conviction_buy_skip 0.45 alone (DD 37.9%).

---

## BTC_1h (pair_cost=0.799, KEEP rate 2/4=50%, max_dd=9%)
V7.3 + 2 KEEPs: skip=0.45 KEEP (iter 52, 5.8%), skip=0.40 KEEP (iter 64, 8.3%).
Current: pair_cost=0.799, avg_profit=-$0.33/bar, max_dd=9%, correct_side=61%.
Near 0.85 benchmark — now 6% below. Skip series active.

Priority queue:
1. conviction_buy_skip 0.40->0.35 — continue series. BTC_1h at 0.40 gives 61% correct_side
   (highest in system at this skip level). If skip=0.35 collapses like SOL_1h (iter 57) or
   XRP_15m (iter 60), halt. Watch matched_ratio (1.2% at 0.40 is very thin).
   RISK: matched_ratio already critically low at 1.2% — may collapse at 0.35.
2. risk_ceil 0.15->0.20 — max_dd only 9%. Enormous DD headroom. More capital per bar improves
   avg_profit on this directionally strong pair.
3. max_onesided_cost 5.0->3.0 — pre-emptive DD containment before risk_ceil test. Low priority
   unless skip=0.35 increases DD.

Blacklists (BTC_1h): risk_ceil tightening, sell_loss_start tightening, pace_urgency_hi loosening,
bar_budget to 400, conviction_buy_skip raising above 0.50, bar_budget 300 (untested but 400 failed).

---

## ETH_5m (pair_cost=0.782, KEEP rate 2/3=67%, max_dd=47%)
V7.3 + 2 KEEPs (rotation 4): re-eval (iter 65, +6.8%) + skip=0.45 (iter 66, +7.7%).
Current: pair_cost=0.782, avg_profit=-$0.21/bar, max_dd=47%, correct_side=37.3%.
WARNING: correct_side=37.3% is critically near the anti-predictive floor (35%).
Pair is now below 0.85 benchmark. avg_profit still negative but improving.

Priority queue:
1. max_onesided_cost 5.0->2.0 — ETH_15m analog confirms onesided cap halves max_dd on 15m bars
   (iter 68: 54.5%->32.5%). ETH_5m at 47% max_dd urgently needs DD control.
2. conviction_buy_skip 0.45->0.40 — only attempt if correct_side at 0.45 stabilizes above 37%.
   Currently too risky: if 0.45 pushed correct_side from 44.6%->37.3%, the 0.40 step may cross
   into anti-predictive territory. Hold until max_dd resolved.
3. [FLAG DISCARD condition] If max_onesided_cost=2.0 still leaves max_dd>40%, ETH_5m may need
   DISABLE flag. correct_side<35% at any future step = structural anti-predictive pair.

Blacklists (ETH_5m): unmatched_ratio tightening, conviction_buy_skip raising above 0.50,
conviction_buy_skip 0.45->0.40 (hold until DD resolved).

---

## ETH_15m (pair_cost=0.703, KEEP rate 3/4=75%, max_dd=33%)
V7.3 + 3 KEEPs: re-eval (iter 53, +10.5%), skip=0.45 (iter 54, +9.1%), onesided_cost=2.0 (iter 68, +6.3%).
Current: pair_cost=0.703, avg_profit=-$0.32/bar, max_dd=32.5%, correct_side=35.1%.
Beats trader_a benchmark. max_dd now near 30% threshold but controlled. BEST 15m pair.

Priority queue:
1. max_onesided_cost 2.0->1.5 — test further reduction. max_dd at 32.5% still marginally above 30%.
   If 1.5 cuts DD below 30% without worsening pair_cost, this pair achieves all benchmark targets.
   Risk: too tight a cap may reduce matched_ratio further from already-low 1.5%.
2. conviction_buy_skip 0.45->0.40 — only after DD confirmed below 30%. correct_side=35.1% is very
   low; skip=0.40 risks entering anti-predictive zone. Hold until onesided_cost experiment resolves.
3. bar_budget 200->300 — once DD is controlled, scale capital on this benchmark-beating pair.

Blacklists (ETH_15m): unmatched_ratio tightening, conviction_buy_skip raising to 0.55,
max_onesided_cost increasing (no-op test already done), skip=0.40 before DD is resolved.

---

## ETH_1h (pair_cost=0.706, KEEP rate 2/3=67%, max_dd=17%)
V7.3 + 2 KEEPs: re-eval (iter 39, +19.7%), skip=0.45 (iter 40, +7.7%).
skip=0.40 DISCARD (iter 69): pair_cost worsened 0.7058->0.7212. Skip=0.45 is optimum.
Current: pair_cost=0.706, avg_profit=-$0.49/bar, max_dd=17%, correct_side=43.3%.
CONFIRMED FLOOR: Like XRP_1h, ETH_1h skip=0.45 is the structural optimum.

Priority queue:
1. risk_ceil 0.15->0.20 — max_dd=17%, safe headroom. More exposure per bar may tip avg_profit
   positive. ETH_1h has 43% correct_side which is below 50% — more capital could swing total_profit.
2. bar_budget 200->300 — benchmark-beating pair_cost. Moderate capital scale-up.
3. pace_urgency_lo 0.35->0.45 — later entry timing. Test fill price improvement.

Blacklists (ETH_1h): max_onesided_cost increasing (zero effect — cap never hit on 1h bars),
conviction_buy_skip 0.40 (D iter 69 — worsens cost), conviction_buy_skip 0.55 (untested but
XRP_1h analog shows tighter filter fails on already-optimized pairs).
NOTE: skip series exhausted — do not test further skip changes on ETH_1h.

---

## SOL_5m (pair_cost=0.814, KEEP rate 2/3=67%, max_dd=31%)
V7.3 + 2 KEEPs (rotation 4): re-eval (iter 70, +6.0%), skip=0.45 (iter 71, +8.4%).
Current: pair_cost=0.814, avg_profit=+$0.0007/bar (near-zero positive), max_dd=31.1%.
avg_profit turned positive. max_dd at 31.1% is marginally above 30% threshold.
Approaching benchmark. IMPROVED pair this rotation.

Priority queue:
1. max_onesided_cost 5.0->2.0 — max_dd at 31.1% is above 30% threshold. ETH_15m analog (iter 68)
   shows onesided cap effectively halves max_dd on 5m+ bars. Highest priority for SOL_5m.
2. conviction_buy_skip 0.45->0.40 — only after DD resolved. avg_profit barely positive;
   skip=0.40 risk of collapse same as XRP_15m (iter 60). Hold.
3. risk_ceil 0.15->0.10 (REDUCE) — IF max_dd remains above 30% after onesided cap, reducing
   risk allocation may contain DD. Inverse lever for DD-constrained pairs.

Blacklists (SOL_5m): conviction_buy_skip raising to 0.55 (D iter 41), conviction_buy_skip 0.40
(too risky before DD resolved — collapse risk).

---

## SOL_15m (pair_cost=0.796, KEEP rate 1/2=50%, max_dd=14%)
V7.3 + 1 KEEP: skip=0.45 KEEP (iter 56, +14.9%).
skip=0.40 not yet tested (XRP_15m at 0.40 collapsed — need to verify SOL_15m behaves differently).
Current: pair_cost=0.796, avg_profit=-$0.08/bar, max_dd=14%, correct_side=38.4%.
Beats trader_a benchmark. Low DD. avg_profit near-zero.

Priority queue:
1. conviction_buy_skip 0.45->0.40 — test carefully. XRP_15m collapsed at 0.40 (iter 60); SOL_1h
   collapsed at 0.35 (iter 57). SOL_15m may have a different collapse threshold. Watch matched_ratio:
   if drops to 0% (like XRP_15m), immediately DISCARD. Look for SOL_15m showing same resilience as
   BTC_1h (which handled 0.40 without collapse, iter 64).
2. bar_budget 200->300 — benchmark-beating pair_cost with excellent DD (14%). Safe to scale.
3. max_onesided_cost 5.0->2.0 — pre-emptive if skip=0.40 test increases DD.

Blacklists (SOL_15m): min_unmatched_shares tightening, conviction_buy_skip raising above 0.50.

---

## SOL_1h (pair_cost=0.661, KEEP rate 2/3=67%, max_dd=9%)
V7.3 + 2 KEEPs: re-eval (iter 43, +10.3%), skip=0.45 (iter 58, +5.2%).
skip=0.35 collapsed (iter 57). skip=0.40 not yet tested on SOL_1h.
Current: pair_cost=0.661, avg_profit=+$0.54/bar, max_dd=9%.
BEST pair: profitable, lowest DD, benchmark-beating by 33%.

Priority queue:
1. conviction_buy_skip 0.45->0.40 — SOL_1h is the strongest pair. BTC_1h succeeded at 0.40 (iter 64,
   8.3% gain). SOL_1h has room given 9% DD and positive avg_profit. Watch matched_ratio (3.1% at 0.45
   is thin; collapse risk if drops to 0%).
   Prior: skip=0.35 collapsed (matched_ratio=0%). Test 0.40 carefully.
2. bar_budget 200->400 — lowest DD (9%), positive avg_profit. Prior DISCARD on BTC_1h (iter 36) at
   400 — use 300 as intermediate step instead.
   Revised: bar_budget 200->300 (safer increment than 400).
3. risk_ceil 0.15->0.20 — with 9% DD headroom, safe to increase per-bar allocation.

Blacklists (SOL_1h): conviction_buy_skip 0.35 (iter 57 collapsed), bar_budget 400 (BTC_1h analog
showed pacing degradation — use 300 as max).

---

## XRP_5m (pair_cost=0.909, KEEP rate 1/1=100%, max_dd=69%)
V7.3 + 1 KEEP (re-eval only, iter 44): pair_cost=0.909, avg_profit=-$0.32/bar, max_dd=69%.
fill_ticks=15 DISCARD (iter 59): structural XRP_5m microstructure fill limit (54% fill rate).
conviction_buy_skip 0.50->0.45 not yet tested on V7.3.

Priority queue:
1. conviction_buy_skip 0.50->0.45 — test the direction confirmed on XRP_15m and SOL_5m.
   SOL_5m at skip=0.45 improved 8.4% (iter 71). XRP_5m has similar profile.
   If fails: max_dd=69% makes this the most dangerous pair in system.
2. max_onesided_cost 5.0->2.0 — CRITICAL. max_dd=69% is highest in system. If skip=0.45 fails,
   apply onesided cap immediately. Even a partial DD reduction is valuable.
3. fill_ticks 15->20 — after prior fill_ticks test showed fill_rate stuck at 54% with ticks=15,
   test further patience increase. If still 54%, confirm microstructure structural limit.

Blacklists (XRP_5m): fill_ticks 10->15 (only 0.96% gain, structural limit — try 20 as last test),
conviction_buy_skip raising above 0.50.

---

## XRP_15m (pair_cost=0.778, KEEP rate 1/3=33%, max_dd=17%)
V7.3 + 1 KEEP: skip=0.45 KEEP (iter 46, +18.6%).
skip=0.40 DISCARD (iter 60, collapsed pair formation to 0%). Skip series exhausted at 0.45.
Current: pair_cost=0.778, avg_profit=+$0.01/bar (marginally positive), max_dd=17%.
Beats trader_a benchmark. CONFIRMED FLOOR at skip=0.45.

Priority queue:
1. bar_budget 200->300 — benchmark-beating pair_cost, marginal positive avg_profit.
   Low DD (17%) and positive profit justify modest scale-up. Safe first test.
2. risk_ceil 0.15->0.20 — max_dd=17%, ample headroom. More per-bar capital may amplify
   the marginally positive avg_profit.
3. pace_urgency_lo 0.35->0.30 — earlier entry timing to improve fill prices on this pair.

Blacklists (XRP_15m): conviction_buy_skip 0.40 (DISCARD iter 60 — collapsed pair formation),
conviction_buy_skip raising above 0.50.
NOTE: skip series exhausted. Do NOT test further skip changes on XRP_15m.

---

## XRP_1h (pair_cost=0.674, KEEP rate 1/3=33%, max_dd=6%)
V7.3 + 1 KEEP: re-eval (iter 47, +5.87%).
skip=0.45 DISCARD (iter 48). skip=0.55 DISCARD (iter 61, +17.7% regression, correct_side dropped to 47%).
BOTH skip directions exhausted. Like ETH_1h, XRP_1h optimum is at skip=0.50.
Current: pair_cost=0.674, avg_profit=+$1.08/bar, max_dd=6%, correct_side=57%.
2ND BEST pair: profitable, lowest DD (6%), strong correct_side.

Priority queue:
1. bar_budget 200->300 — 2nd best pair_cost, positive avg_profit (+$1.08/bar), max_dd only 6%.
   Scale capital up. Prior 400 tested on BTC_1h (failed pacing); use 300 as the step.
2. risk_ceil 0.15->0.20 — 6% max_dd is lowest in system. Significant room for more per-bar
   capital. XRP_1h at 57% correct_side should benefit from increased allocation.
3. conviction_market_start 0.30->0.25 — lower the market_start threshold to qualify more
   predictions. XRP_1h is already highly selective (matched_ratio=3.4%); cautious reduction
   in market entry bar may increase volume without hurting pair quality.

Blacklists (XRP_1h): conviction_buy_skip 0.45 (D iter 48), conviction_buy_skip 0.55 (D iter 61).
NOTE: BOTH skip directions exhausted. Do NOT test further skip changes on XRP_1h.

---

## Cross-Pair Observations

**Skip series status update (post-rotation-4):**
- skip=0.45 confirmed: ETH_1h (0.50->0.45), XRP_15m (0.50->0.45), BTC_1h (0.50->0.45),
  ETH_15m (0.50->0.45), SOL_15m (0.50->0.45), SOL_1h (0.50->0.45), ETH_5m (0.50->0.45),
  SOL_5m (0.50->0.45) = 8/10 attempted = 80% KEEP
- skip=0.40 tested: BTC_1h KEEP (iter 64), ETH_1h DISCARD (iter 69), XRP_15m DISCARD/collapse
  (iter 60) = 1/3 = 33% KEEP. Pattern: skip=0.40 only works where correct_side is high (>55%).
- skip series EXHAUSTED pairs: BTC_5m (both directions), XRP_1h (both directions), ETH_1h
  (floor at 0.45), XRP_15m (floor at 0.45 — 0.40 collapsed)

**New insight: DD intervention priority**
- max_onesided_cost=2.0 confirmed effective on 15m bars (ETH_15m iter 68: halved DD).
- 5m pairs with max_dd>30% (ETH_5m at 47%, SOL_5m at 31%, XRP_5m at 69%) should test onesided_cap next.
- 1h pairs: cap is never triggered at $5 (confirmed ETH_1h iter 55). Do not test on 1h TFs.

**BTC pairs uniquely resilient to DD**: BTC_5m 24%, BTC_15m 23%, BTC_1h 9% — no DD crisis.
**5m pairs structurally high-DD**: ETH_5m 47%, SOL_5m 31%, XRP_5m 69% — need onesided_cap.

**Capital scaling now appropriate**: 7/12 pairs beat trader_a benchmark. SOL_1h, XRP_1h, XRP_15m,
ETH_1h, ETH_15m, SOL_15m, BTC_1h all below 0.85. These pairs can handle bar_budget scale-up.

**Dataset growth effect**: 3 pairs received KEEP from re-eval alone (ETH_5m, SOL_5m = iter 65/70).
Remaining pairs not re-eval'd on new data: BTC_15m (last 126 bars), XRP_5m (last 373 bars, no change).

---

## trader_a Benchmark Comparison (post-iter-71 best_knobs)
| Pair | PairCost | Target | Gap | AvgProfit | MaxDD% | Trend |
|------|----------|--------|-----|-----------|--------|-------|
| BTC_5m | 0.948 | < 0.85 | +0.098 | +$0.06 | 24% | stagnant — try risk_ceil increase |
| BTC_15m | 0.933 | < 0.85 | +0.083 | +$0.50 | 23% | try re-eval + compound change |
| BTC_1h | 0.799 | < 0.85 | -0.051 | -$0.33 | 9% | BEATS benchmark — skip=0.35 next |
| ETH_5m | 0.782 | < 0.85 | -0.068 | -$0.21 | 47% | BEATS benchmark, DD critical |
| ETH_15m | 0.703 | < 0.85 | -0.147 | -$0.32 | 33% | BEATS benchmark, DD near 30% |
| ETH_1h | 0.706 | < 0.85 | -0.144 | -$0.49 | 17% | BEATS benchmark — skip exhausted, try risk_ceil |
| SOL_5m | 0.814 | < 0.85 | -0.036 | +$0.00 | 31% | BEATS benchmark, DD slight excess |
| SOL_15m | 0.796 | < 0.85 | -0.054 | -$0.08 | 14% | BEATS benchmark — skip=0.40 test |
| SOL_1h | 0.661 | < 0.85 | -0.189 | +$0.54 | 9% | BEST pair — skip=0.40 + budget scale |
| XRP_5m | 0.909 | < 0.85 | +0.059 | -$0.32 | 69% | try skip=0.45 + DD urgent |
| XRP_15m | 0.778 | < 0.85 | -0.072 | +$0.01 | 17% | BEATS benchmark — skip exhausted, scale budget |
| XRP_1h | 0.674 | < 0.85 | -0.134 | +$1.08 | 6% | BEATS benchmark — skip exhausted, scale budget |

**9 pairs now beating trader_a pair_cost benchmark**: ETH_1h, SOL_1h, XRP_1h, XRP_15m, ETH_15m,
SOL_15m, BTC_1h, ETH_5m, SOL_5m.
Progress: 7 pairs last rotation -> 9 pairs this rotation (+2).
Remaining above benchmark: BTC_5m, BTC_15m, XRP_5m.

---

## Blacklist (per-pair)

- BTC_5m: unmatched_ratio tightening, sell_loss_start tightening, conviction_buy_skip 0.45 (D iter 33),
  conviction_buy_skip 0.55 (D iter 50), cheap_threshold 0.07 (D iter 17), cheap_threshold 0.12 (D iter 62).
  BOTH skip directions and BOTH cheap_threshold directions EXHAUSTED.
- BTC_15m: unmatched_ratio tightening, max_marginal_pair_cost below 1.01, cheap_threshold to 0.07,
  bar_budget 300 (D iter 63), conviction_buy_skip 0.45 alone (DD 37.9%)
- BTC_1h: risk_ceil tightening, sell_loss_start tightening, pace_urgency_hi loosening, bar_budget 400,
  conviction_buy_skip raising above 0.50
- ETH_5m: unmatched_ratio tightening, conviction_buy_skip raising above 0.50,
  conviction_buy_skip 0.45->0.40 (hold until DD resolved)
- ETH_15m: unmatched_ratio tightening, conviction_buy_skip raising to 0.55,
  max_onesided_cost increasing, conviction_buy_skip 0.45->0.40 (hold until DD resolved)
- ETH_1h: max_onesided_cost increasing (zero effect — cap never hit on 1h bars),
  conviction_buy_skip 0.40 (D iter 69), conviction_buy_skip 0.55 (XRP_1h analog). SKIP EXHAUSTED.
- SOL_5m: conviction_buy_skip raising to 0.55 (D iter 41),
  conviction_buy_skip 0.45->0.40 (hold until DD resolved)
- SOL_15m: min_unmatched_shares tightening, conviction_buy_skip raising above 0.50
- SOL_1h: conviction_buy_skip 0.35 (iter 57 collapsed), bar_budget 400 (use 300 max)
- XRP_5m: fill_ticks 10->15 as final test (structural limit), conviction_buy_skip raising above 0.50
- XRP_15m: conviction_buy_skip 0.40 (DISCARD iter 60 — collapsed), conviction_buy_skip raising.
  SKIP SERIES EXHAUSTED.
- XRP_1h: conviction_buy_skip 0.45 (D iter 48), conviction_buy_skip 0.55 (D iter 61).
  BOTH SKIP DIRECTIONS EXHAUSTED.

## Global Blacklist
- unmatched_ratio tightening: 3/3 DISCARDs (BTC_5m, ETH_5m, ETH_15m)
- sell_loss_start tightening: 2/2 DISCARDs (BTC_5m, BTC_1h)
- max_marginal_pair_cost tightening below 1.01: collapses matched_ratio
- pace_urgency_hi loosening: zero effect (BTC_1h 1/1 D)
- conviction_buy_skip RAISING above 0.50: 0/4 KEEP (ETH_5m, ETH_15m, SOL_5m, BTC_5m)
- bar_budget doubling (200->400): 1/1 DISCARD (BTC_1h), reduces fill quality — use 300 max
- max_onesided_cost increasing on 1h TFs: zero effect (ETH_1h 0/1 — cap never triggered at $5)
- conviction_buy_skip below 0.40 (except BTC_1h): collapses pair formation
- fill_ticks 10->15 (XRP_5m): structural microstructure limit at 54%

---

## Priority Order for Next Rotation

**DD repair (urgent — prevent benchmark failures from DD excess):**
1. ETH_5m: max_onesided_cost 5.0->2.0 (max_dd=47%, ETH_15m analog shows halving effect)
2. SOL_5m: max_onesided_cost 5.0->2.0 (max_dd=31%, just above 30% threshold)
3. XRP_5m: conviction_buy_skip 0.50->0.45 FIRST (then onesided_cost if skip fails)

**Capital scaling (safe pairs with good metrics):**
4. SOL_1h: conviction_buy_skip 0.45->0.40 (best pair, 9% DD, positive profit)
5. XRP_1h: bar_budget 200->300 (2nd best pair, 6% DD, +$1.08/bar, skip exhausted)
6. XRP_15m: bar_budget 200->300 (benchmark-beating, skip exhausted, positive profit)

**Skip series continuation (where not exhausted):**
7. SOL_15m: conviction_buy_skip 0.45->0.40 (14% DD, test collapse risk carefully)
8. BTC_1h: conviction_buy_skip 0.40->0.35 (9% DD, test collapse risk — thin matched_ratio)

**Re-evaluation + new levers for stagnant pairs:**
9. BTC_15m: re-eval on enlarged dataset (last clean baseline at 97 bars, now ~130+)
10. ETH_1h: risk_ceil 0.15->0.20 (skip exhausted, try capital lever)
11. ETH_15m: max_onesided_cost 2.0->1.5 (refine DD control below 30%)
12. BTC_5m: risk_ceil 0.15->0.20 (all skip+cheap_threshold levers exhausted)

## Researcher Compliance

researcher_ack (iter 70-71) was accurate: correctly ran re-eval on SOL_5m (KEEP) then tested
skip=0.45 (KEEP). Full compliance with iter-58 strategy.md priority queue #7 (SOL_5m skip=0.45).

For next rotation, researcher should start with SOL_15m (pair_index=7, current pair) and follow
priority order above. The DD repair experiments and capital scaling are the dominant themes.
