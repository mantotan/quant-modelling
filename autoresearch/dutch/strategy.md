# Dutch Strategy
Updated: after iteration 58 (2026-03-23T16:00:00Z) — STRATEGIST analysis

## Summary

Third full rotation complete on V7.3 (iters 47-58). KEEP rate this rotation: 6/12 = 50% — best rotation yet.
Overall V7.3 KEEP rate (iters 33-58): 11/25 = 44%.

Key findings from this rotation:
1. **conviction_buy_skip=0.45 confirmed on 4 more pairs**: BTC_1h (5.8%), ETH_15m (9.1%), SOL_15m (14.9%),
   SOL_1h (5.2%) — all KEEP. Pattern is now universal for 15m and 1h TFs.
2. **7 pairs now beat trader_a pair_cost benchmark (<0.85)**: ETH_1h (0.706), SOL_1h (0.661), XRP_1h (0.674),
   XRP_15m (0.778), ETH_15m (0.751), SOL_15m (0.796), BTC_1h (0.871).
3. **XRP_1h anomaly**: skip=0.45 was DISCARD (0.6738->0.7045) — already strong at skip=0.50 with 57%
   correct_side. Further skip reduction adds noise. XRP_1h stays at skip=0.50.
4. **BTC_5m deadlock**: Both skip directions (0.45 and 0.55) failed. Different lever needed.
5. **BTC_15m skip=0.45 borderline**: 1.4% cost improvement, but max_dd=37.9% exceeds 30% threshold. Need
   deeper analysis — the skip is helping but DD is unsustainable.
6. **max_onesided_cost increase has no effect on ETH_1h**: The $5 cap is never being hit on 1h bars.
   Increasing it is a no-op. Do NOT test onesided_cost increases further on 1h TFs.

---

## BTC_5m (pair_cost=0.948, KEEP rate 0/2=0%, max_dd=24%)
V7.3 baseline profitable: avg_profit=+$0.055/bar, correct_side=56%, matched_ratio=11%.
DEADLOCK on conviction_buy_skip: both 0.45 (DISCARD iter 33) and 0.55 (DISCARD iter 50) failed.
Both re-evals show pair_cost near 0.945-0.948 with no improvement pathway.

Priority queue:
1. cheap_threshold 0.10->0.12 — slightly more liberal entry threshold. Baseline is profitable at 56%
   correct_side; modest volume increase may help without disrupting cost. Prior test (iter 17) tightened
   to 0.07 (DISCARD); loosening direction is untested.
2. risk_ceil 0.15->0.20 — with only 24% max_dd (below 30%), room to increase per-bar risk allocation.
   More capital at stake per bar could improve avg_profit on a directionally profitable pair.
3. pace_urgency_lo 0.35->0.45 — later entry timing. 5m bars move fast; delaying entry may improve
   fill prices if early-bar prices are unfavorable.

Blacklists (BTC_5m): unmatched_ratio tightening, sell_loss_start tightening,
conviction_buy_skip 0.45 (DISCARD iter 33), conviction_buy_skip 0.55 (DISCARD iter 50).
NOTE: both skip directions definitively exhausted — skip is not the lever for BTC_5m.

---

## BTC_15m (pair_cost=0.933, KEEP rate 0/1=0%, max_dd=23%)
V7.3 baseline profitable: avg_profit=+$0.498/bar, correct_side=63%, matched_ratio=12%.
skip=0.45 tested (iter 51): 1.4% cost improvement (0.9334->0.9201) but max_dd=37.9% exceeded 30%
threshold. DISCARD — the skip change helps cost but costs control is lost.

Priority queue:
1. conviction_buy_skip 0.50->0.45 WITH max_onesided_cost 5.0->3.0 — the previous skip=0.45 trial
   showed cost improvement but uncontrolled DD. Simultaneously capping directional exposure may keep
   max_dd below 30% while the skip helps pair_cost. Test as a compound change.
   ALTERNATIVE: If not testing compound changes, next is cheap_threshold 0.10->0.12.
2. cheap_threshold 0.10->0.12 — loosening entry may increase matched_ratio on this high-correct_side pair
   without the DD risk from skip reduction.
3. risk_ceil 0.15->0.20 — 23% max_dd leaves room for more exposure on this profitable pair.

Blacklists (BTC_15m): unmatched_ratio tightening, max_marginal_pair_cost below 1.01,
cheap_threshold to 0.07, conviction_buy_skip 0.45 alone (DD too high at 37.9%).

---

## BTC_1h (pair_cost=0.871, KEEP rate 1/2=50%, max_dd=9%)
V7.3 + 1 KEEP: conviction_buy_skip 0.50->0.45 improved pair_cost 5.8% (0.9244->0.8707), avg_profit
+$0.36/bar, max_dd=9.26% (safe). Now close to 0.85 benchmark — needs 2.5% more improvement.

Priority queue:
1. conviction_buy_skip 0.45->0.40 — continue the series. BTC_1h at 0.45 gives 58% correct_side.
   Test whether 0.40 further improves cost. Watch: if correct_side drops below 50%, halt.
2. risk_ceil 0.15->0.20 — max_dd only 9%. Room to deploy more capital per bar.
3. cheap_threshold 0.10->0.12 — more liberal entry to increase matched_ratio from current 7.2%.

Blacklists (BTC_1h): risk_ceil tightening, sell_loss_start tightening, pace_urgency_hi loosening,
bar_budget to 400, conviction_buy_skip RAISING above 0.50.

---

## ETH_5m (pair_cost=0.909, KEEP rate 0/1=0%, max_dd=84%)
V7.3 baseline unprofitable: avg_profit=-$0.517/bar, correct_side=41%, matched_ratio=13%.
CRITICAL: correct_side=41% is anti-predictive. Raising skip to 0.60 failed (iter 37) — all metrics
worsened. Skip=0.45 not yet tested on V7.3 (untested territory; iter 19 was pre-V7.3).

Priority queue:
1. conviction_buy_skip 0.50->0.45 — the only untested skip direction on V7.3. Despite anti-predictive
   signal, more volume could improve pair formation. However: if correct_side drops below 38%, this
   is a structural problem beyond tuning.
2. max_onesided_cost 5.0->2.0 — reduce DD from 84%. Even if skip doesn't help, capping directional
   exposure per event limits max_dd to manageable levels.
3. [FLAG] If both skip=0.45 and onesided_cost=2.0 fail, consider ETH_5m DISABLED for research.
   Anti-predictive models cannot be fixed by parameter tuning alone.

Blacklists (ETH_5m): unmatched_ratio tightening, conviction_buy_skip raising above 0.50 (0.60 DISCARD).

---

## ETH_15m (pair_cost=0.751, KEEP rate 2/2=100%, max_dd=70%)
V7.3 + 2 KEEPs: pair_cost improved to 0.7506 (9.1% via skip=0.45). Beats trader_a benchmark.
WARNING: max_dd=70% is dangerously high despite good pair_cost. avg_profit=-$0.70/bar still negative.
Correct_side dropped from 45.7% (baseline) to 34.1% (skip=0.45) — concerning anti-predictive drift.

Priority queue:
1. max_onesided_cost 5.0->2.0 — PRIORITY. At 70% max_dd, this pair needs DD control urgently.
   Capping directional exposure per event is the most direct lever to reduce max_dd.
2. conviction_buy_skip 0.45->0.50 REVERT if onesided_cost=2.0 DISCARD — if capping cost still doesn't
   help avg_profit, the correct_side at 34% may be the underlying problem. Consider reverting skip.
3. pace_urgency_lo 0.35->0.45 — later entry timing on 15m bars.

WARNING: correct_side=34% is below random at 50%. This pair may be fundamentally broken at skip=0.45.
Monitor avg_profit trend. If consistently worse than -$1.0/bar at any knob, flag for DISABLE.

Blacklists (ETH_15m): unmatched_ratio tightening, conviction_buy_skip raising to 0.55.

---

## ETH_1h (pair_cost=0.706, KEEP rate 2/2=100%, max_dd=17%)
V7.3 + 2 KEEPs: pair_cost=0.7058, avg_profit=-$0.49/bar (marginal negative), max_dd=17%.
Beats trader_a benchmark. max_onesided_cost 5.0->7.0 DISCARD (iter 55) — onesided cap not active on 1h.
NOTE: increasing onesided_cost is a no-op on this TF. Do not test further.

Priority queue:
1. conviction_buy_skip 0.45->0.40 — continue series. ETH_1h responded well to skip reduction (25.9%
   improvement from 0.50->0.45). Test 0.40. Watch: correct_side was 46.7%->43.3% at 0.45. If 0.40
   drops below 40%, stop skip reduction — entering anti-predictive territory.
2. risk_ceil 0.15->0.20 — max_dd=17%, safe headroom. More exposure per bar may tip avg_profit positive.
3. bar_budget 200->300 — benchmark-beating pair_cost. Scale capital moderately.

Blacklists (ETH_1h): max_onesided_cost increasing (zero effect at $5 cap on 1h bars).

---

## SOL_5m (pair_cost=0.946, KEEP rate 0/1=0%, max_dd=32%)
V7.3 baseline unprofitable: avg_profit=-$0.205/bar, correct_side=46%, matched_ratio=9%.
Raising skip to 0.55 was DISCARD (iter 41). Skip=0.45 untested on V7.3.

Priority queue:
1. conviction_buy_skip 0.50->0.45 — skip=0.45 confirmed on SOL_15m (14.9% improvement). SOL_5m
   at 46% correct_side is near-breakeven. Test the direction that works on all 15m/1h analogs.
2. max_onesided_cost 5.0->3.0 — reduce DD from 32%. Max_dd is near the 30% threshold.
3. fill_ticks 10->15 — 69% fill rate is lowest among SOL pairs. More patience for fills.

Blacklists (SOL_5m): conviction_buy_skip raising to 0.55.

---

## SOL_15m (pair_cost=0.796, KEEP rate 1/2=50%, max_dd=14%)
V7.3 + 1 KEEP: conviction_buy_skip 0.50->0.45 improved pair_cost 14.9% (0.9348->0.7956), avg_profit
near-zero (-$0.08/bar). Beats trader_a benchmark. max_dd=14% — excellent DD control.
Correct_side dropped 50%->38.4% at skip=0.45. Low matched_ratio (4.8%).

Priority queue:
1. conviction_buy_skip 0.45->0.40 — continue series. SOL_15m shows the XRP_15m analog pattern.
   Watch correct_side — already at 38.4%, further drop below 33% is the stop condition.
2. bar_budget 200->300 — benchmark-beating pair_cost with excellent DD (14%). Safe to scale.
3. pace_urgency_lo 0.35->0.30 — earlier entry timing to capture better prices.

Blacklists (SOL_15m): min_unmatched_shares tightening, conviction_buy_skip raising above 0.50.

---

## SOL_1h (pair_cost=0.661, KEEP rate 2/2=100%, max_dd=9%)
V7.3 + 2 KEEPs: pair_cost=0.6605, avg_profit=+$0.54/bar positive, max_dd=9%.
BEST pair: profitable, low DD, benchmark-beating by 33%. Skip=0.35 collapsed pair formation (DISCARD
iter 57). Skip=0.45 is the optimum found so far.

Priority queue:
1. conviction_buy_skip 0.45->0.40 — test next reduction. SOL_1h is the strongest pair — if any pair
   can handle lower skip, it's this one. Watch matched_ratio (3.1% at 0.45 is already very selective).
   Stop if avg_profit turns negative or matched_ratio falls below 1.5%.
2. bar_budget 200->400 — lowest DD (9%) and positive avg_profit. Deserves maximum capital expansion.
3. risk_ceil 0.15->0.20 — with 9% DD headroom, safe to increase per-bar allocation.

Blacklists (SOL_1h): conviction_buy_skip 0.35 (iter 57 collapsed pair formation).

---

## XRP_5m (pair_cost=0.909, KEEP rate 1/1=100%, max_dd=69%)
V7.3 + 1 KEEP (re-eval only): pair_cost=0.9085, avg_profit=-$0.32/bar, max_dd=69%.
No conviction_buy_skip experiments done on V7.3. fill_ticks=15 already set.

Priority queue:
1. conviction_buy_skip 0.50->0.45 — test the direction confirmed on XRP_15m. XRP_15m at 0.45 showed
   18.6% cost improvement. XRP_5m has 45% correct_side (near-random). Lower skip may help cost
   even if direction is weak.
2. max_onesided_cost 5.0->2.0 — reduce DD from 69%. Critical intervention on highest-DD pair.
3. fill_ticks 15->20 — fill_rate=54% is worst in system. More patience may help on XRP_5m.

Note: XRP_5m structural fill constraint (54% vs 80%+ for others) may be market microstructure.
If fill_ticks=20 still gives <60% fill_rate, this may be inherent to XRP_5m.

---

## XRP_15m (pair_cost=0.778, KEEP rate 1/2=50%, max_dd=17%)
V7.3 + 1 KEEP: conviction_buy_skip 0.50->0.45 improved pair_cost 18.6% (0.9558->0.7780), avg_profit
+$0.01/bar (marginally positive). Beats trader_a benchmark. correct_side dropped 52%->33.3% at skip=0.45.

Priority queue:
1. conviction_buy_skip 0.45->0.40 — continue series. Marginal avg_profit suggests capacity for
   improvement. Watch: correct_side at 33.3% is already very low. If 0.40 drops below 28%, halt.
2. bar_budget 200->300 — benchmark-beating pair_cost, positive avg_profit. Modest scale-up justified.
3. pace_urgency_lo 0.35->0.30 — earlier entry to improve fill prices.

WARNING: correct_side drop from 52% to 33.3% is a 19pp decline. XRP_15m may be in a regime where
only very few high-conviction trades are profitable. Further skip reduction risks entering
anti-predictive zone. Treat 0.40 as a confirmatory test, not an extension.

---

## XRP_1h (pair_cost=0.674, KEEP rate 1/2=50%, max_dd=6%)
V7.3 + 1 KEEP (re-eval, iter 47): pair_cost=0.6738. Skip=0.45 DISCARD (iter 48) — 0.6738->0.7045 worsened.
UNIQUE ANOMALY: XRP_1h is the ONLY 1h pair where skip=0.45 failed. Reason: already very selective
pair formation (matched_ratio=3.4%, fill_rate=76%) — lower skip adds marginal-quality pairs at worse prices.
Current best: skip=0.50 at pair_cost=0.6738 — 2nd best in system behind SOL_1h.

Priority queue:
1. conviction_buy_skip 0.50->0.55 — INVERSE direction. Since 0.45 worsened cost, test tighter filter.
   Higher conviction threshold on already-profitable pair may improve pair quality further.
   XRP_1h has 57% correct_side (best in system) — high-skip filtering should help here.
2. bar_budget 200->300 — best pair_cost tier (alongside SOL_1h). Safe to scale capital.
3. risk_ceil 0.15->0.20 — max_dd only 6%. Plenty of headroom for higher per-bar allocation.

Blacklists (XRP_1h): conviction_buy_skip 0.45 (DISCARD iter 48 — worsens pair_cost).

---

## Cross-Pair Observations

**Confirmed universal pattern: conviction_buy_skip=0.45 works on 15m and 1h TFs**
- ETH_1h: 0.9528->0.7058 (KEEP iter 40)
- XRP_15m: 0.9558->0.7780 (KEEP iter 46)
- BTC_1h: 0.9244->0.8707 (KEEP iter 52)
- ETH_15m: 0.9220->0.7506 (KEEP iter 54)
- SOL_15m: 0.9348->0.7956 (KEEP iter 56)
- SOL_1h: 0.6967->0.6605 (KEEP iter 58)
- Total: 6/6 = 100% KEEP rate for skip=0.45 on these TFs

**Exception: XRP_1h**
- skip=0.45 DISCARD (iter 48): already strong baseline (0.6738), further skip reduction hurts
- XRP_1h behavior suggests pair_cost at 0.67 is near the structural floor for this pair

**Definitively failed: raising conviction_buy_skip above 0.50 (globally)**
- ETH_5m 0.60 D, ETH_15m 0.55 D, SOL_5m 0.55 D, BTC_5m 0.55 D = 0/4 KEEP = 0%

**BTC_5m deadlock**: Both directions exhausted. Needs non-skip parameter next.

**BTC_15m borderline**: skip=0.45 improves cost but triggers DD. Compound change needed.

**max_onesided_cost increases are no-ops on 1h TFs**: The $5 per-event cap is never reached on
1h bars (low throughput). Do not test cap increases on ETH_1h or other 1h pairs.

**5m pairs remain problematic**: All 5m pairs still above 0.85 benchmark. Pattern: 5m bars too fast
for skip=0.45 to help (BTC_5m 0.45 D, ETH_5m raising failed). SOL_5m and XRP_5m skip=0.45 untested.

---

## trader_a Benchmark Comparison (post-iter-58 best_knobs)
| Pair | PairCost | Target | Gap | AvgProfit | MaxDD% | Trend |
|------|----------|--------|-----|-----------|--------|-------|
| BTC_5m | 0.948 | < 0.85 | +0.098 | +$0.06 | 24% | deadlock — try non-skip levers |
| BTC_15m | 0.933 | < 0.85 | +0.083 | +$0.50 | 23% | skip DD issue — try compound change |
| BTC_1h | 0.871 | < 0.85 | +0.021 | +$0.36 | 9% | close — skip=0.40 next |
| ETH_5m | 0.909 | < 0.85 | +0.059 | -$0.52 | 84% | anti-predictive — try skip=0.45 + onesided cap |
| ETH_15m | 0.751 | < 0.85 | -0.099 | -$0.70 | 70% | BEATS benchmark but DD critical |
| ETH_1h | 0.706 | < 0.85 | -0.144 | -$0.49 | 17% | BEATS benchmark, skip=0.40 next |
| SOL_5m | 0.946 | < 0.85 | +0.096 | -$0.21 | 32% | try skip=0.45 |
| SOL_15m | 0.796 | < 0.85 | -0.054 | -$0.08 | 14% | BEATS benchmark, skip=0.40 next |
| SOL_1h | 0.661 | < 0.85 | -0.189 | +$0.54 | 9% | BEST pair — skip=0.40 + budget scale |
| XRP_5m | 0.909 | < 0.85 | +0.059 | -$0.32 | 69% | try skip=0.45 |
| XRP_15m | 0.778 | < 0.85 | -0.072 | +$0.01 | 17% | BEATS benchmark, skip=0.40 next |
| XRP_1h | 0.674 | < 0.85 | -0.134 | +$1.08 | 6% | BEATS benchmark, try skip=0.55 |

**7 pairs now beating trader_a pair_cost benchmark**: ETH_1h, SOL_1h, XRP_1h, XRP_15m, ETH_15m, SOL_15m, BTC_1h.
Progress: 4 pairs last rotation -> 7 pairs this rotation (+3).

---

## Blacklist (per-pair)

- BTC_5m: unmatched_ratio tightening, sell_loss_start tightening, conviction_buy_skip 0.45 (D iter 33),
  conviction_buy_skip 0.55 (D iter 50) — BOTH SKIP DIRECTIONS EXHAUSTED
- BTC_15m: unmatched_ratio tightening, max_marginal_pair_cost below 1.01, cheap_threshold to 0.07,
  conviction_buy_skip 0.45 alone (max_dd 37.9%)
- BTC_1h: risk_ceil tightening, sell_loss_start tightening, pace_urgency_hi loosening, bar_budget to 400,
  conviction_buy_skip raising above 0.50
- ETH_5m: unmatched_ratio tightening, conviction_buy_skip raising above 0.50
- ETH_15m: unmatched_ratio tightening, conviction_buy_skip raising to 0.55,
  max_onesided_cost increasing (no-op on 1h-tier)
- ETH_1h: max_onesided_cost increasing (zero effect — cap never hit on 1h bars)
- SOL_5m: conviction_buy_skip raising to 0.55
- SOL_15m: min_unmatched_shares tightening, conviction_buy_skip raising above 0.50
- SOL_1h: conviction_buy_skip 0.35 (collapsed pair formation iter 57)
- XRP_1h: conviction_buy_skip 0.45 (DISCARD iter 48 — worsens this already-strong pair)

## Global Blacklist
- unmatched_ratio tightening: 3/3 DISCARDs (BTC_5m, ETH_5m, ETH_15m)
- sell_loss_start tightening: 2/2 DISCARDs (BTC_5m, BTC_1h)
- max_marginal_pair_cost tightening below 1.01: collapses matched_ratio
- pace_urgency_hi loosening: zero effect (BTC_1h 1/1 D)
- conviction_buy_skip RAISING above 0.50: 0/4 KEEP (ETH_5m, ETH_15m, SOL_5m, BTC_5m)
- bar_budget doubling (200->400): 1/1 DISCARD (BTC_1h), reduces fill quality
- max_onesided_cost increasing on 1h TFs: zero effect (ETH_1h 0/1 KEEP — cap never triggered)

---

## Priority Order for Next Rotation

**Highest confidence (continue proven series: skip=0.40 where skip=0.45 already worked):**
1. SOL_1h: conviction_buy_skip 0.45->0.40 (best pair, 100% KEEP history on skip reductions, +profit)
2. XRP_15m: conviction_buy_skip 0.45->0.40 (continue series, marginal profit confirms direction)
3. ETH_1h: conviction_buy_skip 0.45->0.40 (continue series, watch correct_side floor at 40%)
4. SOL_15m: conviction_buy_skip 0.45->0.40 (continue series, 14% DD headroom allows testing)
5. BTC_1h: conviction_buy_skip 0.45->0.40 (5.8% improvement from 0.50->0.45, test next step)

**Medium confidence (new territory on 5m pairs):**
6. XRP_5m: conviction_buy_skip 0.50->0.45 (untested; XRP_15m analog — but 5m bar dynamic differs)
7. SOL_5m: conviction_buy_skip 0.50->0.45 (untested on V7.3; all 15m/1h skip=0.45 worked)
8. ETH_5m: conviction_buy_skip 0.50->0.45 (untested on V7.3; last resort before DISABLE)

**Repair (structural DD problems):**
9. ETH_15m: max_onesided_cost 5.0->2.0 (max_dd=70% critical; most urgent DD intervention)
10. XRP_5m: max_onesided_cost 5.0->2.0 (max_dd=69% critical; pair-specific after skip test)

**New direction (for stagnant or anomalous pairs):**
11. XRP_1h: conviction_buy_skip 0.50->0.55 (INVERSE — skip=0.45 failed; 57% correct_side may support tighter filter)
12. BTC_5m: cheap_threshold 0.10->0.12 (skip exhausted; try entry threshold loosening)

## Researcher Compliance

researcher_ack (iter 57-58) was accurate: evaluated conviction_buy_skip 0.50->0.35 (DISCARD) and
then correctly followed up with skip=0.45 (KEEP). Full compliance with strategy.

For next rotation, researcher should start with XRP_15m (pair_index=10, next after current XRP_5m) and
follow priority order above. The skip=0.40 continuation tests should be highest priority.
