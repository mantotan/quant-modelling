# Dutch Strategy
Updated: after iteration 83 (2026-03-24T00:30:00Z) — STRATEGIST analysis

## Summary

Fifth full rotation complete on V7.3 (iters 72-83). KEEP rate this rotation: 3/12 = 25%.
Overall V7.3 KEEP rate (iters 33-83): 20/51 = 39%.

Key findings from rotation 5:
1. **ETH_15m breakthrough**: max_onesided_cost 2.0->1.5 yielded a massive 20.4% pair_cost
   improvement (0.7032->0.5600, iter 82). max_dd halved 32.5%->26.8% (now below 30%).
   ETH_15m is now the BEST 15m pair and 2nd best in system (pair_cost=0.560).
2. **SOL_15m scales up**: re-eval (iter 72, +0.1%) + bar_budget 300 (iter 73, +1.1%) both KEEP.
   avg_profit improved to +$0.17/bar, max_dd dropped to 9.5%. SOL_15m now profitable with budget=300.
3. **SOL_1h skip floor confirmed at 0.45**: skip 0.45->0.40 DISCARD (iter 74, -11.5% regression).
   Pattern matches ETH_1h (iter 69). Both SOL_1h and ETH_1h have structural skip floor at 0.45.
4. **bar_budget scale-up globally fails**: XRP_15m (iter 75, -0.7%), XRP_1h (iter 76, -10.3%),
   BTC_15m compound change (iter 78, +3.97%). Larger budgets worsen pair_cost on selective pairs.
   CONFIRMED: bar_budget optimum at 200 for XRP pairs and most 1h pairs.
5. **BTC_5m structural DD crisis**: re-eval (iter 77) shows max_dd=33.2% on full dataset (385 bars).
   Pair_cost improved slightly (0.9480->0.9446) but DD exceeds 30% threshold. No knob change —
   structural issue. BTC_5m needs DD repair urgently before any cost optimization.
6. **BTC_15m near-miss**: compound skip=0.45+onesided=3.0 achieved 3.97% improvement (iter 78),
   just below 5% KEEP RELAXED threshold. This compound direction is promising — try adjusting values.
7. **BTC_1h dataset variance**: re-eval (iter 79) regressed 0.7988->0.8476 with only 1 new bar
   (34 total vs 33). Variance on thin dataset (1h = few bars). Risk_ceil test (iter 80) also failed.
   BTC_1h at structural floor — skip=0.40 likely optimal but vulnerable to dataset noise.
8. **Risk_ceil experiments fail on 1h pairs**: ETH_1h (iter 83, +3.8%) and BTC_1h (iter 80, below
   cost floor) both below KEEP threshold. Risk_ceil increases don't improve cost on 1h pairs.

Current best_knobs state (post-iter-83):
- ETH_15m: skip=0.45, max_onesided_cost=1.5 (pair_cost=0.560, max_dd=26.8%)
- SOL_15m: skip=0.45, bar_budget=300 (pair_cost=0.786, max_dd=9.5%, avg_profit=+$0.17/bar)
- BTC_1h: skip=0.40 (pair_cost=0.799, subject to dataset variance)
- All others: unchanged from post-iter-71

---

## BTC_5m (pair_cost=0.948, KEEP rate 0/6=0%, max_dd=33.2%)
V7.3 best: avg_profit=+$0.06/bar, correct_side=56%, matched_ratio=11%.
CRITICAL: max_dd=33.2% on full dataset (iter 77 re-eval). DD exceeds 30% threshold on expanded data.
Skip both directions exhausted. cheap_threshold both directions exhausted. risk_ceil untested.

Priority queue:
1. max_onesided_cost 5.0->2.0 — URGENT DD repair. max_dd=33.2% exceeds threshold.
   ETH_15m confirmed this works on 15m TFs (iter 68: halved DD). Apply same pattern.
   If successful, DD drops to ~16% and unlocks further optimization.
2. risk_ceil 0.15->0.10 (REDUCE) — if max_onesided_cost test does not fully contain DD,
   reducing capital allocation reduces exposure. DD-first approach.
3. risk_ceil 0.15->0.20 (INCREASE) — only if DD is resolved by onesided cap. Was strategy
   priority in iter 71; now deferred until DD fix confirmed.

Blacklists (BTC_5m): unmatched_ratio tightening, sell_loss_start tightening,
conviction_buy_skip 0.45 (D iter 33), conviction_buy_skip 0.55 (D iter 50),
cheap_threshold 0.07 (D iter 17), cheap_threshold 0.12 (D iter 62),
risk_ceil 0.15->0.20 (hold until DD resolved). BOTH skip directions EXHAUSTED.

---

## BTC_15m (pair_cost=0.933, KEEP rate 0/4=0%, max_dd=23%)
V7.3 best: avg_profit=+$0.50/bar, correct_side=63%, matched_ratio=12%.
Compound skip=0.45+onesided=3.0 achieved 3.97% improvement (iter 78), just below 5% threshold.
bar_budget 300 DISCARD (iter 63). No single successful experiment since V7.3 reset.

Priority queue:
1. conviction_buy_skip 0.50->0.45 + max_onesided_cost 5.0->2.0 (tighter onesided) —
   iter 78 used onesided=3.0 and got 3.97%. Try onesided=2.0 for a stronger cap effect.
   The compound direction is right; the onesided value may need tightening to cross 5% threshold.
   This pairs ETH_15m's confirmed onesided=2.0 effect with BTC_15m's 63% correct_side.
2. conviction_buy_skip 0.50->0.45 alone — if compound fails, test skip alone to isolate contribution.
   iter 51 showed skip alone caused DD=37.9%; combine with onesided to contain.
3. max_onesided_cost 5.0->2.0 alone — isolate the onesided effect before combining.

Blacklists (BTC_15m): unmatched_ratio tightening, max_marginal_pair_cost below 1.01,
cheap_threshold to 0.07, bar_budget 300 (D iter 63 — larger budget worsens cost),
conviction_buy_skip 0.45 alone without DD protection (DD 37.9% in iter 51).

---

## BTC_1h (pair_cost=0.799, KEEP rate 2/5=40%, max_dd=9%)
V7.3 + 2 KEEPs: skip=0.45 (iter 52), skip=0.40 (iter 64).
Re-eval (iter 79): regression to 0.8476 due to dataset variance (only 1 new bar, 34 total).
Risk_ceil 0.15->0.20 (iter 80): DISCARD — cost floor 0.7988 not breached.
Effective best_knobs pair_cost = 0.7988. Subject to single-bar dataset variance.
Thin dataset (34 bars) means high variance — any single bar can shift metrics ±5%.

Priority queue:
1. max_onesided_cost 5.0->3.0 — matched_ratio is critically thin (1.2% at skip=0.40).
   Onesided cap may protect against single bad-direction bars that cause pair_cost variance.
   Lower priority than DD repairs but safest next lever.
2. pace_urgency_lo 0.35->0.45 — delayed entry timing may improve fill prices on this
   volatile pair with thin matching. test after onesided cap.
3. risk_ceil 0.15->0.20 — already failed (iter 80). Try only after structural changes.
   NOTE: at 34 bars, re-testing risk_ceil after onesided cap may produce different result.

Blacklists (BTC_1h): risk_ceil tightening, sell_loss_start tightening, pace_urgency_hi loosening,
bar_budget 400, conviction_buy_skip raising above 0.50, risk_ceil 0.15->0.20 standalone (D iter 80).
NOTE: skip series exhausted (0.40 KEEP, 0.35 untested on BTC_1h — but skip=0.35 collapsed SOL_1h
at iter 57; thin matched_ratio at 1.2% likely collapse risk, skip=0.40 probably the floor).

---

## ETH_5m (pair_cost=0.782, KEEP rate 2/3=67%, max_dd=47%)
V7.3 + 2 KEEPs (rotation 4): re-eval (iter 65) + skip=0.45 (iter 66).
No new experiments in rotation 5 (pair was not reached in rotation). State unchanged.
CRITICAL: correct_side=37.3% near anti-predictive floor (35%). max_dd=47% critical.

Priority queue:
1. max_onesided_cost 5.0->2.0 — URGENT DD repair. max_dd=47% is 2nd highest in system.
   ETH_15m (iter 68) + ETH_15m (iter 82) both confirmed onesided cap halves DD.
   ETH_5m is the most urgent remaining DD case.
2. conviction_buy_skip 0.45->0.40 — HOLD until DD resolved. correct_side=37.3% is too
   close to anti-predictive floor. Do not test skip further until max_onesided_cost resolves.
3. [DISABLE risk] If max_onesided_cost=2.0 still leaves max_dd>40%, consider DISABLE flag.
   correct_side<35% at any future step = structural anti-predictive — halt experiments.

Blacklists (ETH_5m): unmatched_ratio tightening, conviction_buy_skip raising above 0.50,
conviction_buy_skip 0.45->0.40 (hold until DD resolved — current correct_side=37.3% too low).

---

## ETH_15m (pair_cost=0.560, KEEP rate 4/5=80%, max_dd=27%)
V7.3 + 4 KEEPs: re-eval (iter 53), skip=0.45 (iter 54), onesided=2.0 (iter 68), onesided=1.5 (iter 82).
MASSIVE improvement: onesided=1.5 added 20.4% (0.7032->0.5600). Now BEST 15m pair and 2nd best overall.
All benchmark targets met: pair_cost=0.560 (<0.85), max_dd=26.8% (<30%).
correct_side=35.1% is low but pair_cost breakthrough dominates.

Priority queue:
1. max_onesided_cost 1.5->1.0 — test further reduction. Onesided series has shown
   consistent gains (5->2->1.5 each improved). If 1.0 further improves pair_cost without
   collapsing matched_ratio (currently 0.3%), KEEP. Risk: cap too tight may starve pair formation.
2. bar_budget 200->300 — pair_cost now excellent (0.560). max_dd=26.8% is safe.
   Dataset now at 131 bars. Scale capital on this benchmark-beating pair.
   Caution: XRP_1h and XRP_15m both had bar_budget DISCARDs — verify behavior is different here.
3. conviction_buy_skip 0.45->0.40 — with DD now controlled (26.8%), this test is safer.
   correct_side=35.1% is still concerning. Test only after confirming current pair_cost holds.

Blacklists (ETH_15m): unmatched_ratio tightening, conviction_buy_skip raising to 0.55,
max_onesided_cost increasing (confirmed zero effect on >=2.0 cap direction),
bar_budget 200->300 before testing onesided=1.0 (ordering matters).

---

## ETH_1h (pair_cost=0.706, KEEP rate 2/3=67%, max_dd=17%)
V7.3 + 2 KEEPs: re-eval (iter 39), skip=0.45 (iter 40).
Skip floor confirmed at 0.45 (same as SOL_1h). Risk_ceil 0.15->0.20 DISCARD (iter 83, +3.8%).
Risk_ceil increase produces only 3.8% improvement on ETH_1h — below 5% threshold.

Priority queue:
1. bar_budget 200->250 — smaller increment than 300 to test sensitivity.
   bar_budget 300 DISCARDs for XRP pairs, but ETH_1h has lower matched_ratio (7%) than XRP (3.4%).
   intermediate test to check if budget scale direction is viable before committing to 300.
2. pace_urgency_lo 0.35->0.45 — later entry timing may improve fill prices.
   ETH_1h fills at 88.4% already; this tests whether delaying urgency gate improves pair quality.
3. max_onesided_cost 5.0->3.0 — test lower cap on 1h TF (confirmed zero effect at 5->7 in iter 55,
   but smaller cap might trigger and help). Low priority — 1h bars typically don't hit the cap.

Blacklists (ETH_1h): max_onesided_cost increasing (D iter 55 — zero effect above $5),
conviction_buy_skip 0.40 (D iter 69), risk_ceil 0.15->0.20 standalone (D iter 83 — only 3.8%).
NOTE: skip series exhausted at 0.45. Do NOT test further skip changes on ETH_1h.

---

## SOL_5m (pair_cost=0.814, KEEP rate 2/3=67%, max_dd=31%)
V7.3 + 2 KEEPs (rotation 4): re-eval (iter 70), skip=0.45 (iter 71).
No new experiments in rotation 5. State unchanged from post-iter-71.
avg_profit near-zero positive (+$0.0007/bar). max_dd=31.1% marginally above 30%.

Priority queue:
1. max_onesided_cost 5.0->2.0 — URGENT. max_dd=31.1% above 30% threshold.
   ETH_15m confirmed this pattern twice (iter 68 and 82). High confidence this will help SOL_5m.
   This is the single most important experiment for SOL_5m.
2. conviction_buy_skip 0.45->0.40 — HOLD until DD resolved. avg_profit barely positive;
   collapse risk same as XRP_15m (iter 60). Hold.
3. risk_ceil 0.15->0.10 (REDUCE) — fallback if onesided cap insufficient to bring DD<30%.

Blacklists (SOL_5m): conviction_buy_skip raising to 0.55 (D iter 41),
conviction_buy_skip 0.45->0.40 (hold until DD resolved).

---

## SOL_15m (pair_cost=0.786, KEEP rate 3/4=75%, max_dd=9.5%)
V7.3 + 3 KEEPs: skip=0.45 (iter 56), re-eval (iter 72, +0.11%), bar_budget 300 (iter 73, +1.11%).
Current: pair_cost=0.786, avg_profit=+$0.17/bar, max_dd=9.5%, correct_side=44.6%, bar_budget=300.
avg_profit POSITIVE. max_dd EXCELLENT. IMPROVED pair this rotation.
bar_budget 300 confirmed effective on SOL_15m (unlike XRP pairs which regressed).

Priority queue:
1. conviction_buy_skip 0.45->0.40 — test carefully. XRP_15m collapsed at 0.40 (iter 60);
   SOL_15m has different correct_side profile (44.6% vs XRP_15m's 33.3%).
   avg_profit positive and DD excellent provide safety margin. Watch matched_ratio collapse risk.
   If matched_ratio drops to 0% like XRP_15m, immediately DISCARD.
2. bar_budget 300->400 — SOL_15m showed different response to budget increase than XRP pairs.
   If skip=0.40 maintains pair quality, scale further. Test after skip experiment.
3. max_onesided_cost 5.0->2.0 — pre-emptive if skip=0.40 increases DD above 15%.
   Currently 9.5% max_dd is very safe; use as safety net if skip test increases DD.

Blacklists (SOL_15m): min_unmatched_shares tightening, conviction_buy_skip raising above 0.50.

---

## SOL_1h (pair_cost=0.661, KEEP rate 2/4=50%, max_dd=9%)
V7.3 + 2 KEEPs: re-eval (iter 43), skip=0.45 (iter 58).
Skip floor confirmed at 0.45 (iter 74: skip 0.45->0.40 DISCARD, -11.5% regression).
CONFIRMED PATTERN: SOL_1h skip floor = ETH_1h skip floor = 0.45.
Current: pair_cost=0.661, avg_profit=+$0.54/bar, max_dd=9.1%.
2ND BEST overall pair. Skip series now fully exhausted.

Priority queue:
1. bar_budget 200->300 — SOL_1h is 2nd best pair. SOL_15m KEEP at bar_budget=300 (iter 73)
   suggests SOL pairs may accept higher budgets better than XRP pairs.
   XRP_1h DISCARD at 300 (iter 76); XRP_15m DISCARD at 300 (iter 75). SOL pairs different.
   Test with caution given these DISCARDs, but SOL_1h+SOL_15m profile different from XRP.
2. risk_ceil 0.15->0.20 — 9% max_dd provides enormous headroom. With positive avg_profit,
   more capital per bar may compound gains. Note: risk_ceil failed on BTC_1h (iter 80) and
   ETH_1h (iter 83) — verify if positive avg_profit makes SOL_1h different.
3. pace_urgency_lo 0.35->0.45 — later entry timing test as alternative lever.

Blacklists (SOL_1h): conviction_buy_skip 0.35 (collapsed iter 57),
conviction_buy_skip 0.45->0.40 (DISCARD iter 74 — skip floor confirmed at 0.45),
bar_budget 400 (use 300 as max per prior BTC_1h DISCARD analog).
NOTE: SKIP SERIES FULLY EXHAUSTED on SOL_1h.

---

## XRP_5m (pair_cost=0.909, KEEP rate 1/2=50%, max_dd=69%)
V7.3 + 1 KEEP (re-eval only, iter 44). fill_ticks=15 DISCARD (iter 59).
conviction_buy_skip 0.50->0.45 not yet tested on V7.3.
WORST pair: max_dd=69% is highest in system. Needs urgent DD intervention.

Priority queue:
1. conviction_buy_skip 0.50->0.45 — confirmed effective on SOL_5m (iter 71, +8.4%).
   XRP_5m has similar profile. Test first before onesided cap.
   If fails on pair_cost: immediately apply max_onesided_cost next.
2. max_onesided_cost 5.0->2.0 — CRITICAL DD repair regardless of skip outcome.
   max_dd=69% is unsustainable. Apply in parallel or following skip test.
   Even partial DD reduction from 69% is high value.
3. fill_ticks 10->20 — prior test (ticks=15) showed 54% fill rate unchanged.
   Try 20 as final confirmation of structural microstructure limit. If still 54%, abandon.

Blacklists (XRP_5m): fill_ticks 10->15 (structural limit — try 20 as last test),
conviction_buy_skip raising above 0.50.

---

## XRP_15m (pair_cost=0.778, KEEP rate 1/3=33%, max_dd=17%)
V7.3 + 1 KEEP: skip=0.45 (iter 46, +18.6%).
skip=0.40 DISCARD (iter 60, collapsed). bar_budget 200->300 DISCARD (iter 75, -0.7%).
CONFIRMED: bar_budget 200 is OPTIMUM for XRP_15m (larger budget worsens pair_cost).
Current: pair_cost=0.778, avg_profit=+$0.01/bar (marginally positive), max_dd=17%.

Priority queue:
1. risk_ceil 0.15->0.20 — skip and bar_budget series exhausted. Max_dd=17% has headroom.
   With marginally positive avg_profit and good pair_cost, more per-bar capital may help.
   Different from risk_ceil failures on BTC_1h/ETH_1h (which have negative avg_profit).
2. pace_urgency_lo 0.35->0.30 — earlier entry timing to improve fill prices.
   XRP_15m is highly selective (matched_ratio=2%); earlier timing may help.
3. conviction_market_start 0.30->0.25 — lower the bar for qualifying predictions.
   Very low matched_ratio (2%) suggests over-filtering. Cautious reduction may help volume.

Blacklists (XRP_15m): conviction_buy_skip 0.40 (DISCARD iter 60 — collapsed),
bar_budget 300 (DISCARD iter 75 — worsened cost), conviction_buy_skip raising.
NOTE: skip series EXHAUSTED. bar_budget OPTIMUM at 200. Do NOT test further skip or budget.

---

## XRP_1h (pair_cost=0.674, KEEP rate 1/3=33%, max_dd=6%)
V7.3 + 1 KEEP: re-eval (iter 47, +5.87%).
skip=0.45 DISCARD (iter 48). skip=0.55 DISCARD (iter 61). bar_budget 200->300 DISCARD (iter 76, -10.3%).
CONFIRMED: bar_budget 200 is OPTIMUM for XRP_1h (300 collapses avg_profit 77%).
BEST pair (or near-best): avg_profit=+$1.08/bar, max_dd=6%, correct_side=57%.

Priority queue:
1. risk_ceil 0.15->0.20 — 6% max_dd is absolute floor. With $1.08/bar profit,
   more per-bar capital directly amplifies returns. Skip and budget series both exhausted.
   Different from risk_ceil failures on BTC/ETH 1h (XRP_1h has POSITIVE avg_profit).
2. pace_urgency_lo 0.35->0.45 — test fill quality improvement via timing.
3. conviction_market_start 0.30->0.25 — XRP_1h already selective (3.4% matched_ratio).
   Very small reduction in market entry bar may qualify more predictions without hurting quality.

Blacklists (XRP_1h): conviction_buy_skip 0.45 (D iter 48), conviction_buy_skip 0.55 (D iter 61),
bar_budget 300 (DISCARD iter 76 — optimum at 200).
NOTE: BOTH skip directions EXHAUSTED. bar_budget OPTIMUM at 200. Do NOT test these.

---

## Cross-Pair Observations

**Skip floor mapping (post-rotation-5 confirmed):**
- skip=0.40 confirmed floor: BTC_1h (KEEP iter 64)
- skip=0.45 confirmed floor: ETH_1h (D iter 69), SOL_1h (D iter 74), XRP_15m (D iter 60)
- skip=0.50 confirmed floor: XRP_1h (D iter 48), BTC_5m (D iter 33+50)
- skip series active: BTC_15m (0.45 never tested alone successfully), SOL_15m (0.40 untested),
  ETH_15m (0.40 on hold pending DD), ETH_5m (0.40 on hold pending DD), SOL_5m (0.40 on hold),
  XRP_5m (0.45 untested)

**bar_budget scale-up pattern confirmed:**
- XRP pairs: bar_budget 200 is CONFIRMED OPTIMUM. 300 DISCARDs for both XRP_15m and XRP_1h.
- SOL_15m: bar_budget 300 KEEP (iter 73). SOL pairs accept larger budgets.
- BTC_15m: bar_budget 300 DISCARD (iter 63). BTC_15m at 200.
- General rule: highly selective pairs (matched_ratio <3%) resist larger budgets.

**max_onesided_cost progression confirmed as most reliable lever:**
- ETH_15m: 5->2->1.5 each improved pair_cost. Total onesided series effect: ~27% improvement.
- 5->2 confirmed on ETH_15m (iter 68). 2->1.5 MASSIVE +20.4% (iter 82).
- Remaining high-DD pairs needing onesided repair: ETH_5m (47%), XRP_5m (69%), SOL_5m (31%), BTC_5m (33%).
- Pattern: aggressive onesided caps (<=2.0) prevent runaway directional accumulation.

**risk_ceil increase fails on 1h pairs with negative avg_profit:**
- ETH_1h (iter 83): +3.8%, DISCARD. BTC_1h (iter 80): below cost floor.
- Exception hypothesis: XRP_1h and SOL_1h have POSITIVE avg_profit — risk_ceil may work there.

**DD repair is the dominant blocking theme for rotation 6:**
- ETH_5m (47%), XRP_5m (69%), SOL_5m (31%), BTC_5m (33%): all need max_onesided_cost.
- Until DD is resolved on these pairs, skip/capital experiments are blocked.

---

## trader_a Benchmark Comparison (post-iter-83 best_knobs)
| Pair | PairCost | Target | Gap | AvgProfit | MaxDD% | Trend |
|------|----------|--------|-----|-----------|--------|-------|
| BTC_5m | 0.948 | < 0.85 | +0.098 | +$0.06 | 33.2% | CRITICAL DD — needs onesided cap first |
| BTC_15m | 0.933 | < 0.85 | +0.083 | +$0.50 | 23% | compound skip+onesided=2.0 next |
| BTC_1h | 0.799 | < 0.85 | -0.051 | -$0.33 | 9% | BEATS benchmark — skip exhausted, onesided test |
| ETH_5m | 0.782 | < 0.85 | -0.068 | -$0.21 | 47% | BEATS benchmark, DD urgent |
| ETH_15m | 0.560 | < 0.85 | -0.290 | -$0.21 | 26.8% | BEST 15m, BEATS benchmark — onesided=1.0 next |
| ETH_1h | 0.706 | < 0.85 | -0.144 | -$0.49 | 17% | BEATS benchmark — bar_budget 250 test |
| SOL_5m | 0.814 | < 0.85 | -0.036 | +$0.00 | 31.1% | BEATS benchmark, DD slight excess |
| SOL_15m | 0.786 | < 0.85 | -0.054 | +$0.17 | 9.5% | BEATS benchmark, PROFITABLE, skip=0.40 next |
| SOL_1h | 0.661 | < 0.85 | -0.189 | +$0.54 | 9.1% | BEST pair — skip exhausted, budget test |
| XRP_5m | 0.909 | < 0.85 | +0.059 | -$0.32 | 69% | WORST pair, DD critical — skip=0.45 + onesided |
| XRP_15m | 0.778 | < 0.85 | -0.072 | +$0.01 | 17% | BEATS benchmark — risk_ceil test next |
| XRP_1h | 0.674 | < 0.85 | -0.134 | +$1.08 | 6% | BEST pair — risk_ceil test (positive profit edge) |

**9 pairs beating trader_a pair_cost benchmark** (unchanged from rotation 4).
Progress: rotation 5 maintained 9/12 despite failures. BTC_5m, BTC_15m, XRP_5m remain above benchmark.
ETH_15m gap widened dramatically to -0.290 (was -0.147 last rotation) — biggest improvement of rotation 5.

---

## Blacklist (per-pair)

- BTC_5m: unmatched_ratio tightening, sell_loss_start tightening, conviction_buy_skip 0.45 (D iter 33),
  conviction_buy_skip 0.55 (D iter 50), cheap_threshold 0.07 (D iter 17), cheap_threshold 0.12 (D iter 62),
  risk_ceil increase (hold until DD resolved). SKIP SERIES + CHEAP_THRESHOLD EXHAUSTED.
- BTC_15m: unmatched_ratio tightening, max_marginal_pair_cost below 1.01, cheap_threshold to 0.07,
  bar_budget 300 (D iter 63), conviction_buy_skip 0.45 alone without onesided cap (DD 37.9%)
- BTC_1h: risk_ceil tightening, sell_loss_start tightening, pace_urgency_hi loosening, bar_budget 400,
  conviction_buy_skip raising above 0.50, risk_ceil 0.15->0.20 standalone (D iter 80).
  Skip floor likely at 0.40 (thin matched_ratio 1.2% — collapse risk below).
- ETH_5m: unmatched_ratio tightening, conviction_buy_skip raising above 0.50,
  conviction_buy_skip 0.45->0.40 (hold until DD resolved — correct_side=37.3%)
- ETH_15m: unmatched_ratio tightening, conviction_buy_skip raising to 0.55,
  max_onesided_cost increasing above 5.0, skip=0.40 (hold until confirmed stable)
- ETH_1h: max_onesided_cost increasing (zero effect D iter 55), conviction_buy_skip 0.40 (D iter 69),
  risk_ceil 0.15->0.20 (D iter 83, +3.8% only). SKIP EXHAUSTED.
- SOL_5m: conviction_buy_skip raising to 0.55 (D iter 41), conviction_buy_skip 0.45->0.40 (hold)
- SOL_15m: min_unmatched_shares tightening, conviction_buy_skip raising above 0.50
- SOL_1h: conviction_buy_skip 0.35 (collapsed iter 57), conviction_buy_skip 0.45->0.40 (D iter 74),
  bar_budget 400. SKIP SERIES FULLY EXHAUSTED.
- XRP_5m: fill_ticks 10->15 (structural limit D iter 59), conviction_buy_skip raising above 0.50
- XRP_15m: conviction_buy_skip 0.40 (collapsed D iter 60), bar_budget 300 (D iter 75 — optimum at 200).
  SKIP SERIES EXHAUSTED. BAR_BUDGET OPTIMUM AT 200.
- XRP_1h: conviction_buy_skip 0.45 (D iter 48), conviction_buy_skip 0.55 (D iter 61),
  bar_budget 300 (D iter 76 — optimum at 200). BOTH SKIP DIRECTIONS EXHAUSTED. BUDGET OPTIMUM AT 200.

## Global Blacklist
- unmatched_ratio tightening: 3/3 DISCARDs (BTC_5m, ETH_5m, ETH_15m)
- sell_loss_start tightening: 2/2 DISCARDs (BTC_5m, BTC_1h)
- max_marginal_pair_cost tightening below 1.01: collapses matched_ratio
- pace_urgency_hi loosening: zero effect (BTC_1h 1/1 D)
- conviction_buy_skip RAISING above 0.50: 0/4 KEEP (ETH_5m, ETH_15m, SOL_5m, BTC_5m)
- bar_budget doubling (200->400): 1/1 DISCARD (BTC_1h) — use 300 as max
- bar_budget 200->300 on XRP pairs: 2/2 DISCARDs (XRP_15m iter 75, XRP_1h iter 76)
- max_onesided_cost increasing on 1h TFs: zero effect (ETH_1h 0/1 — cap never triggered)
- conviction_buy_skip below 0.40 (except BTC_1h): collapses pair formation
- fill_ticks 10->15 (XRP_5m): structural microstructure limit at 54%
- risk_ceil increase on 1h pairs with NEGATIVE avg_profit: 0/2 KEEP (BTC_1h iter 80, ETH_1h iter 83)

---

## Priority Order for Next Rotation

**DD repair (urgent — blocking further optimization on 4 pairs):**
1. ETH_5m: max_onesided_cost 5.0->2.0 (max_dd=47%, ETH_15m doubled-confirmed pattern)
2. SOL_5m: max_onesided_cost 5.0->2.0 (max_dd=31%, same pattern, high confidence)
3. BTC_5m: max_onesided_cost 5.0->2.0 (max_dd=33.2%, 15m analog confirmed)
4. XRP_5m: conviction_buy_skip 0.50->0.45 FIRST (then onesided=2.0 regardless of skip outcome)

**Onesided cap extension (ETH_15m series continuation):**
5. ETH_15m: max_onesided_cost 1.5->1.0 (series has yielded gains at every step, try one more)

**Capital scaling on positive-profit pairs:**
6. XRP_1h: risk_ceil 0.15->0.20 (POSITIVE avg_profit edge — different from failed 1h tests)
7. SOL_1h: bar_budget 200->300 (SOL_15m confirmed 300 works for SOL; skip exhausted)

**BTC_15m compound experiment (near-miss in rotation 5):**
8. BTC_15m: conviction_buy_skip 0.50->0.45 + max_onesided_cost 5.0->2.0 (tighter onesided=2.0
   vs iter 78's onesided=3.0; trying to cross the 5% threshold from 3.97%)

**Skip and misc tests for pairs with safe DD:**
9. SOL_15m: conviction_buy_skip 0.45->0.40 (9.5% DD is safe, avg_profit positive)
10. XRP_15m: risk_ceil 0.15->0.20 (positive profit, skip exhausted, budget exhausted)
11. ETH_1h: bar_budget 200->250 (cautious budget test — smaller step than 300)
12. BTC_1h: max_onesided_cost 5.0->3.0 (protect against thin-matched-ratio variance)

## Researcher Compliance

researcher_ack (iter 83, ETH_1h) was accurate: correctly tested risk_ceil 0.15->0.20 per
strategy priority queue item #1 (ETH_1h risk_ceil). Full compliance with strategy.md.
Result: DISCARD (+3.8%, below 5% threshold). ETH_1h risk_ceil confirmed insufficient lever.

For next rotation, researcher should resume at SOL_5m (pair_index=6, current pair) and follow
priority order above. The DD repair experiments are the dominant theme for rotation 6.
