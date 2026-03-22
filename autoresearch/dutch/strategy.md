# Dutch Strategy
Updated: after iteration 95 (2026-03-23T16:00:00Z) — STRATEGIST analysis

## Summary

Sixth full rotation complete on V7.3 (iters 84-95). KEEP rate this rotation: 3/12 = 25%.
Overall V7.3 KEEP rate (iters 33-95): 23/63 = 36.5%.

Key findings from rotation 6:
1. **SOL_5m DD repaired**: max_onesided_cost 5.0->2.0 KEEP (iter 84): pair_cost +9.9%
   (0.8140->0.7333), DD halved 31.1%->22.3%. Pattern confirmed: onesided=2.0 repairs 5m DD.
2. **SOL_1h capital scaling**: bar_budget 300 KEEP (iter 86): pair_cost +0.87%, avg_profit
   +$0.54->+$0.69/bar, DD halved 9.1%->5.8%. SOL pairs confirmed to accept higher budgets.
   SOL_1h is now the BEST pair by avg_profit ($0.69/bar) and DD (5.8%).
3. **ETH_5m DD repaired**: max_onesided_cost 5.0->2.0 KEEP (iter 92): pair_cost +6.0%
   (0.7819->0.7355), DD halved 47%->22.9%, correct_side improved 37.3%->42.8%.
4. **SOL_15m skip floor confirmed at 0.45**: conviction_buy_skip 0.40 DISCARD (iter 85) —
   collapsed pair formation (matched_ratio 4.8%->0.0%). Same pattern as XRP_15m (iter 60).
5. **risk_ceil 0.15->0.20 FAILS on XRP pairs**: XRP_15m (iter 87) worsened cost. XRP_1h
   (iter 88) worsened cost. Pattern generalized: risk_ceil increase fails on ALL tested pairs.
   Only exception hypothesis remaining: SOL_1h/SOL_5m with positive avg_profit.
6. **BTC_5m DD partially repaired**: max_onesided_cost 5.0->3.0 (iter 89): DD 33%->17.25%
   but cost marginally WORSE (-0.38%). Try 2.0 for stronger cap — same step as SOL/ETH.
7. **BTC_15m compound direction definitively fails**: skip=0.45+onesided=2.0 (iter 90) and
   skip=0.45+onesided=3.0 (iter 78) both DISCARD. Skip=0.45 collapses BTC_15m matching
   regardless of onesided cap (matched_ratio 11.9%->0.2%). Do NOT test skip=0.45 on BTC_15m.
8. **ETH_15m onesided series floor at 1.5**: onesided 1.5->1.0 DISCARD (iter 94) — pair
   formation collapse (matched_ratio 1%->0%). Re-eval (iter 93) showed 20.5% variance on 3
   new bars — structural volatility on low-matched-ratio pair. ETH_15m floor = 1.5.
9. **BTC_1h onesided sub-5% effect**: max_onesided_cost 5->3 (iter 91) +1.0%, DISCARD.
   Improvement below threshold. Try 2.0 as final test; if still sub-5%, abandon onesided on BTC_1h.

Current best_knobs state (post-iter-95):
- SOL_1h: bar_budget=300 (pair_cost=0.655, max_dd=5.8%, avg_profit=+$0.69/bar) — BEST PAIR
- XRP_1h: skip=0.50 default (pair_cost=0.674, max_dd=6%, avg_profit=+$1.08/bar)
- ETH_15m: onesided=1.5 (pair_cost=0.560, but volatile — re-eval showed 0.675 on 3 new bars)
- ETH_5m: onesided=2.0 (pair_cost=0.736, max_dd=22.9%)
- SOL_5m: onesided=2.0 (pair_cost=0.733, max_dd=22.3%)
- SOL_15m: bar_budget=300, skip=0.45 (pair_cost=0.786, max_dd=9.5%)
- BTC_5m: best_knobs unchanged (pair_cost=0.948, onesided=5.0, DD partially fixed by 3.0 test but DISCARD)
- BTC_15m: all compound skip=0.45 directions exhausted; best_knobs = baseline (pair_cost=0.933)

---

## BTC_5m (pair_cost=0.948, KEEP rate 0/8=0%, max_dd=24.4%)
V7.3 best: avg_profit=+$0.06/bar, correct_side=56%, matched_ratio=11%.
iter 89: max_onesided_cost 5->3 fixed DD (33%->17.25%) but cost marginally WORSE. DISCARD.
Pattern across ETH_5m and SOL_5m: onesided=2.0 (not 3.0) is the effective repair step.
All skip directions exhausted. All cheap_threshold directions exhausted.

Priority queue:
1. max_onesided_cost 5.0->2.0 — iter 89 confirmed 3.0 fixes DD but not cost. Following
   ETH_5m (iter 92) and SOL_5m (iter 84), both KEEP at 2.0. Try 2.0 as the proven effective
   onesided value. This is the highest-confidence remaining experiment for BTC_5m.
2. risk_ceil 0.15->0.10 (REDUCE) — if onesided=2.0 still leaves pair_cost above 0.90,
   reducing capital exposure may help. Low priority — try onesided=2.0 first.
3. pace_urgency_lo 0.35->0.45 — alternative lever if onesided approach exhausted.
   Tests delayed entry timing to improve fill quality on this pair.

Blacklists (BTC_5m): unmatched_ratio tightening, sell_loss_start tightening,
conviction_buy_skip 0.45 (D iter 33), conviction_buy_skip 0.55 (D iter 50),
cheap_threshold 0.07 (D iter 17), cheap_threshold 0.12 (D iter 62),
max_onesided_cost 5->3 (D iter 89 — use 2.0 instead). SKIP SERIES + CHEAP_THRESHOLD EXHAUSTED.

---

## BTC_15m (pair_cost=0.933, KEEP rate 0/7=0%, max_dd=23%)
V7.3 best: avg_profit=+$0.50/bar, correct_side=63%, matched_ratio=12%.
iter 90: compound skip=0.45+onesided=2.0 DISCARD — matched_ratio collapsed 11.9%->0.2%.
iter 78: compound skip=0.45+onesided=3.0 DISCARD — similar collapse.
CONCLUSION: conviction_buy_skip=0.45 is definitively incompatible with BTC_15m's matching
structure. The 63% correct_side is strong but current skip=0.50 appears to be the floor.
No single successful experiment since V7.3 reset. Zero KEEP rate.

Priority queue:
1. max_onesided_cost 5.0->2.0 (ALONE, no skip change) — isolate onesided effect without
   skip. Skip=0.45 direction fully exhausted. Try onesided=2.0 alone to see if it helps
   pair_cost without altering skip. ETH_5m/SOL_5m both benefited from onesided=2.0 alone.
   BTC_15m has higher matched_ratio (12%) vs 5m peers — onesided may work differently.
2. pace_urgency_lo 0.35->0.30 — earlier entry timing. BTC_15m correct_side=63% is system
   high — timing may be limiting fill quality. Test if earlier urgency gate improves pair_cost.
3. bar_budget 200->300 — BTC_15m unique in having positive avg_profit (+$0.50) with
   high correct_side. If pair_cost can be improved first, capital scaling may be viable.
   NOTE: was DISCARD (iter 63) on prior config. Re-test only after structural cost improvement.

Blacklists (BTC_15m): unmatched_ratio tightening, max_marginal_pair_cost below 1.01,
cheap_threshold to 0.07, bar_budget 300 before cost fix (D iter 63),
conviction_buy_skip 0.45 (ANY combination DISCARD — iter 51, 78, 90 all confirm collapse),
conviction_buy_skip 0.45+onesided=2.0 (D iter 90), conviction_buy_skip 0.45+onesided=3.0 (D iter 78).
SKIP=0.45 DIRECTION DEFINITIVELY EXHAUSTED.

---

## BTC_1h (pair_cost=0.799, KEEP rate 2/9=22%, max_dd=9%)
V7.3 + 2 KEEPs: skip=0.45 (iter 52), skip=0.40 (iter 64).
iter 91: max_onesided_cost 5->3 +1.0% DISCARD — below 5% threshold.
Effective best_knobs pair_cost = 0.7988 (iter 64). Thin dataset (35 bars) means high variance.
Risk_ceil increase failed (iter 80). Onesided cap sub-threshold (iter 91).

Priority queue:
1. max_onesided_cost 5.0->2.0 — iter 91 showed 3.0 only +1.0%. Following 5m pattern:
   2.0 is the effective step. One more test before abandoning onesided on BTC_1h.
   If sub-5% again: blacklist onesided for BTC_1h.
2. pace_urgency_lo 0.35->0.45 — delayed entry timing may improve fill prices on
   volatile pair with thin matching (1.2% matched_ratio). Test after onesided confirmed.
3. bar_budget 200->300 — thin dataset, but SOL_1h KEEP at 300 (iter 86). BTC_1h has
   different profile (negative avg_profit). Test only if onesided improves cost sufficiently.

Blacklists (BTC_1h): risk_ceil tightening, sell_loss_start tightening, pace_urgency_hi loosening,
bar_budget 400, conviction_buy_skip raising above 0.50, risk_ceil 0.15->0.20 standalone (D iter 80),
max_onesided_cost 5->3 (D iter 91 — sub-threshold; try 2.0 then blacklist if still sub-5%).
NOTE: skip series exhausted (0.40 KEEP iter 64, skip=0.35 high collapse risk).

---

## ETH_5m (pair_cost=0.736, KEEP rate 3/5=60%, max_dd=22.9%)
V7.3 + 3 KEEPs (iters 65, 66, 92): re-eval + skip=0.45 + onesided=2.0.
iter 92: max_onesided_cost 5->2 KEEP — pair_cost +6.0% (0.7819->0.7355), DD halved 47%->22.9%,
correct_side improved 37.3%->42.8%. DD crisis now RESOLVED (below 30% threshold).
ETH_5m now beats pair_cost benchmark (0.736 < 0.85) with controlled DD.

Priority queue:
1. max_onesided_cost 2.0->1.5 — ETH_15m series showed gains at 2.0 AND 1.5. Following same
   progression. ETH_5m at onesided=2.0 is where ETH_15m was before iter 82 KEEP.
   Risk: ETH_15m needed higher matched_ratio (3%) to accept 1.5; ETH_5m has 1.1% — may collapse
   at 1.5. Monitor matched_ratio carefully. If collapses (like ETH_15m at 1.0): floor=2.0.
2. conviction_buy_skip 0.45->0.40 — now safer with DD controlled (22.9%). However correct_side=
   42.8% is still borderline. Test carefully — watch for collapse to <0%.
3. risk_ceil 0.15->0.20 — with avg_profit near-zero (-$0.02/bar), increasing capital may hurt.
   LOW priority. Test only after pair_cost improvements proven stable.

Blacklists (ETH_5m): unmatched_ratio tightening, conviction_buy_skip raising above 0.50,
conviction_buy_skip 0.45->0.40 (hold until onesided series confirmed stable).

---

## ETH_15m (pair_cost=0.560 best / ~0.675 on current 134 bars, KEEP rate 4/10=40%, max_dd=27%)
V7.3 + 4 KEEPs: re-eval (iter 53), skip=0.45 (iter 54), onesided=2.0 (iter 68), onesided=1.5 (iter 82).
IMPORTANT: iter 93 re-eval showed 20.5% regression (0.560->0.675) on just 3 new bars. ETH_15m
has critically low matched_ratio (1%) — individual bars drive extreme pair_cost variance.
Onesided=1.0 (iter 94): pair formation collapsed. Floor confirmed at 1.5.
ETH_15m is high-performer but structurally volatile due to near-zero matching.

Priority queue:
1. bar_budget 200->300 — with onesided series exhausted at 1.5 floor, scale capital on
   best pair when metrics are favorable. NOTE: current re-eval shows 0.675, not 0.560.
   Run bar_budget test using current best_knobs (onesided=1.5). Accept if cost stays below 0.70.
   ETH_15m's high volatility means outcome uncertain — proceed with caution.
2. pace_urgency_lo 0.35->0.30 — earlier entry timing to improve pair formation rate.
   ETH_15m's 1% matched_ratio is structurally limiting. Earlier urgency gate may capture
   more pairs before price moves away.
3. conviction_buy_skip 0.45->0.40 — with DD controlled (26.8%), this test is safer.
   correct_side=36% is concerning but onesided cap provides downside protection.
   Test only after bar_budget experiment resolves.

Blacklists (ETH_15m): unmatched_ratio tightening, conviction_buy_skip raising to 0.55,
max_onesided_cost increasing above 1.5 (confirmed zero effect), max_onesided_cost 1.5->1.0
(D iter 94 — formation collapse), bar_budget before onesided series settled (order matters).

---

## ETH_1h (pair_cost=0.706, KEEP rate 2/6=33%, max_dd=17%)
V7.3 + 2 KEEPs: re-eval (iter 39), skip=0.45 (iter 40).
iter 95: re-eval DISCARD (+1.8%, 35 bars vs 34 — only 1 new bar, still high variance).
risk_ceil (iter 83): DISCARD +3.8%. max_onesided_cost (D iter 55). Skip exhausted.
ETH_1h best_knobs pair_cost = 0.706, but CURRENT 35-bar re-eval = 0.693 (improvement w/o change).

Priority queue:
1. bar_budget 200->250 — cautious intermediate step. XRP_1h failed at 300 (iter 88 context:
   risk_ceil change, not budget). ETH_1h has matched_ratio=7% (higher than XRP_1h 3.4%).
   If bar_budget 250 helps avg_profit (currently -$0.49/bar), this pair may trend positive.
2. pace_urgency_lo 0.35->0.45 — later entry timing may improve fill prices.
   ETH_1h fills at 88.4% already; tests whether delaying urgency gate improves pair quality.
3. conviction_market_start 0.30->0.25 — lower entry bar for qualifying predictions.
   Matched_ratio=7% is moderate; cautious volume expansion may improve cost through more data.

Blacklists (ETH_1h): max_onesided_cost increasing (D iter 55 — zero effect above $5),
conviction_buy_skip 0.40 (D iter 69), risk_ceil 0.15->0.20 standalone (D iter 83 — only 3.8%).
NOTE: skip series exhausted at 0.45. Do NOT test further skip changes on ETH_1h.

---

## SOL_5m (pair_cost=0.733, KEEP rate 3/4=75%, max_dd=22.3%)
V7.3 + 3 KEEPs (iters 70, 71, 84): re-eval + skip=0.45 + onesided=2.0.
iter 84: max_onesided_cost 5->2 KEEP — pair_cost +9.9%, DD halved 31.1%->22.3%.
ALL BENCHMARKS NOW MET: pair_cost=0.733 (<0.85), max_dd=22.3% (<30%), avg_profit=+$0.05/bar.
SOL_5m is the highest KEEP-rate pair in the system (75%).

Priority queue:
1. max_onesided_cost 2.0->1.5 — following ETH_15m and ETH_5m progression. Try next step
   in the series. Risk: SOL_5m matched_ratio=0.68% is very low — may collapse like ETH_15m
   at onesided=1.0. Monitor carefully.
2. conviction_buy_skip 0.45->0.40 — now safe with DD controlled (22.3%) and positive
   avg_profit providing buffer. Similar to SOL_15m test, but SOL_5m has 0.68% matched_ratio
   vs SOL_15m's 4.8% — higher collapse risk. Careful.
3. bar_budget 200->300 — if onesided series holds and DD remains under control, scale capital.
   Positive avg_profit is the enabling factor.

Blacklists (SOL_5m): conviction_buy_skip raising to 0.55 (D iter 41),
conviction_buy_skip 0.45->0.40 (hold until onesided stability confirmed — current matched_ratio=0.68%).

---

## SOL_15m (pair_cost=0.786, KEEP rate 3/5=60%, max_dd=9.5%)
V7.3 + 3 KEEPs: skip=0.45 (iter 56), re-eval (iter 72, +0.11%), bar_budget 300 (iter 73, +1.11%).
iter 85: conviction_buy_skip 0.40 DISCARD — collapsed (matched_ratio 4.8%->0.0%).
CONFIRMED: SOL_15m skip floor = 0.45 (same as ETH_1h, XRP_15m, SOL_1h, SOL_5m).
Current: pair_cost=0.786, avg_profit=+$0.17/bar, max_dd=9.5%, bar_budget=300.
All benchmark targets met. Skip series fully exhausted.

Priority queue:
1. max_onesided_cost 5.0->2.0 — pre-emptive cap to protect against future DD creep.
   Current 9.5% max_dd is excellent, but applying proven pattern before it becomes a problem.
   If matched_ratio (currently ~5%) holds, this should improve pair_cost further.
2. bar_budget 300->400 — SOL_15m showed different response to budget increase than XRP pairs.
   avg_profit positive and DD excellent. If onesided cap test passes, test budget scaling.
3. pace_urgency_lo 0.35->0.30 — alternative lever; test if earlier urgency timing helps
   on this pair with confirmed structural stability.

Blacklists (SOL_15m): min_unmatched_shares tightening, conviction_buy_skip raising above 0.50,
conviction_buy_skip 0.40 (D iter 85 — confirmed collapse). SKIP SERIES FULLY EXHAUSTED.

---

## SOL_1h (pair_cost=0.655, KEEP rate 3/5=60%, max_dd=5.8%)
V7.3 + 3 KEEPs: re-eval (iter 43), skip=0.45 (iter 58), bar_budget 300 (iter 86).
iter 86: bar_budget 300 KEEP — pair_cost +0.87%, avg_profit +$0.54->+$0.69/bar, DD halved.
BEST PAIR by DD (5.8%) and avg_profit (+$0.69/bar with 34 bars). Skip series exhausted.
Budget scaled to 300 — confirmed SOL pairs accept higher budgets (both SOL_1h and SOL_15m KEEP).

Priority queue:
1. risk_ceil 0.15->0.20 — 5.8% max_dd is extraordinary headroom. avg_profit=+$0.69/bar
   makes this uniquely viable among 1h pairs (all previous risk_ceil tests on negative-profit
   pairs failed). Differentiated case: SOL_1h has PROVEN POSITIVE profit with minimal DD.
2. bar_budget 300->400 — push budget further if risk_ceil test succeeds (or even if it fails).
   SOL pairs are uniquely budget-scalable. With $0.69/bar avg_profit, every budget dollar
   compounds. Test after risk_ceil experiment.
3. pace_urgency_lo 0.35->0.30 — alternative timing lever. SOL_1h fill rate is 89.2%
   already; earlier urgency may squeeze further quality.

Blacklists (SOL_1h): conviction_buy_skip 0.35 (collapsed iter 57),
conviction_buy_skip 0.45->0.40 (DISCARD iter 74 — skip floor confirmed at 0.45),
bar_budget 400 (test 300 confirmed first; try 400 after 300 KEEP validated).
SKIP SERIES FULLY EXHAUSTED on SOL_1h.

---

## XRP_5m (pair_cost=0.909, KEEP rate 1/2=50%, max_dd=68.7%)
V7.3 + 1 KEEP (re-eval only, iter 44). fill_ticks=15 DISCARD (iter 59).
WORST PAIR: max_dd=68.7% is highest in system by far. Only 2 non-baseline experiments.
No rotation 6 experiment ran for XRP_5m — pair not reached.

Priority queue:
1. conviction_buy_skip 0.50->0.45 — analogous to SOL_5m (iter 71, +8.4% KEEP). Never
   tested on XRP_5m. Run before onesided cap to understand skip direction first.
2. max_onesided_cost 5.0->2.0 — CRITICAL DD repair regardless of skip outcome.
   max_dd=68.7% is unsustainable. Apply immediately after skip test.
   ETH_5m (iter 92) and SOL_5m (iter 84) both confirmed onesided=2.0 halves DD.
3. fill_ticks 10->20 — prior test (ticks=15) structural limit at 54% fill rate.
   One more test at 20 to confirm whether structural limit persists.

Blacklists (XRP_5m): fill_ticks 10->15 (structural limit D iter 59 — try 20 as final test),
conviction_buy_skip raising above 0.50.

---

## XRP_15m (pair_cost=0.778, KEEP rate 1/5=20%, max_dd=17%)
V7.3 + 1 KEEP: skip=0.45 (iter 46, +18.6%).
iter 87: risk_ceil 0.15->0.20 DISCARD — worsened pair_cost 0.88% (0.778->0.785).
Skip/budget/risk_ceil all exhausted or failed.
Current: pair_cost=0.778, avg_profit=+$0.01/bar (marginally positive), max_dd=17%.
IMPORTANT: XRP_15m re-eval not run since iter 46 (122 bars). Now likely 132 bars.

Priority queue:
1. pace_urgency_lo 0.35->0.30 — earlier entry timing. XRP_15m is highly selective
   (matched_ratio=2%); earlier urgency timing may capture more pairs before price moves.
   risk_ceil confirmed failed; this is the next untested lever.
2. conviction_market_start 0.30->0.25 — lower prediction entry bar to qualify more signals.
   Very low matched_ratio (2%) suggests over-filtering. Cautious reduction may improve volume.
3. max_onesided_cost 5.0->2.0 — pre-emptive DD cap. max_dd=17% is within benchmark
   but pair has barely positive profit. Onesided cap may improve cost consistency.

Blacklists (XRP_15m): conviction_buy_skip 0.40 (DISCARD iter 60 — collapsed),
bar_budget 300 (DISCARD iter 75 — worsened cost, optimum at 200),
risk_ceil 0.15->0.20 (DISCARD iter 87 — worsened cost). SKIP EXHAUSTED. BUDGET OPTIMUM AT 200.

---

## XRP_1h (pair_cost=0.674, KEEP rate 1/5=20%, max_dd=6%)
V7.3 + 1 KEEP: re-eval (iter 47, +5.87%).
iter 88: risk_ceil 0.15->0.20 DISCARD — worsened pair_cost 4.9% (0.674->0.707).
Skip series exhausted (0.45 D iter 48, 0.55 D iter 61). bar_budget 300 DISCARD (iter 76).
Risk_ceil increase also failed (iter 88). avg_profit=+$1.08/bar is system-best avg_profit.
Most levers exhausted. Focus shifts to timing and market parameters.

Priority queue:
1. pace_urgency_lo 0.35->0.45 — test fill quality improvement via timing.
   XRP_1h already has 87.8% fill rate and 3.4% matched_ratio. Delayed entry may
   improve fill prices by capturing more favorable tick-level entries.
2. conviction_market_start 0.30->0.25 — very small reduction in market entry threshold.
   Low matched_ratio (3.4%) suggests over-filtering. May qualify marginally more predictions
   without degrading quality significantly.
3. pace_urgency_hi 0.85->0.75 — alternative urgency gate tuning.
   Lower hi threshold may help timing without impacting skip behavior.

Blacklists (XRP_1h): conviction_buy_skip 0.45 (D iter 48), conviction_buy_skip 0.55 (D iter 61),
bar_budget 300 (DISCARD iter 76 — optimum at 200), risk_ceil 0.15->0.20 (DISCARD iter 88).
BOTH SKIP DIRECTIONS EXHAUSTED. BAR_BUDGET OPTIMUM AT 200.

---

## Cross-Pair Observations

**Skip floor mapping (post-rotation-6 confirmed):**
- skip=0.40 confirmed floor: BTC_1h (KEEP iter 64)
- skip=0.45 confirmed floor: ETH_1h (D iter 69), SOL_1h (D iter 74), XRP_15m (D iter 60),
  SOL_15m (D iter 85 — newly confirmed this rotation), SOL_5m (KEEP iter 71 — 0.45 works, 0.40 untested)
- skip=0.50 confirmed floor: XRP_1h (D iter 48+61), BTC_5m (D iter 33+50)
- skip=0.45 definitively fails: BTC_15m (D iters 51, 78 compound, 90 compound — 3 tests confirm collapse)
- skip series active: ETH_5m (0.40 on hold pending stability), ETH_15m (0.40 on hold), XRP_5m (0.45 untested)

**max_onesided_cost confirmed as dominant lever for 5m pairs:**
- SOL_5m: 5->2 KEEP iter 84 (+9.9%, DD 31%->22%)
- ETH_5m: 5->2 KEEP iter 92 (+6.0%, DD 47%->23%)
- ETH_15m: 5->2 KEEP iter 68 (+5.6%), 2->1.5 KEEP iter 82 (+20.4%)
- BTC_5m: 5->3 sub-threshold (iter 89), 2.0 next (high confidence)
- XRP_5m: untested — high priority
- Pattern: 2.0 is the optimal first target. 1.5 works only if matched_ratio >1%.

**risk_ceil increase FAILS on ALL tested pairs:**
- BTC_1h (D iter 80), ETH_1h (D iter 83), XRP_15m (D iter 87), XRP_1h (D iter 88)
- 4/4 DISCARDs across diverse pairs. Pattern: more capital forces buys at sub-optimal prices.
- Only remaining hypothesis: SOL_1h/SOL_5m with PROVEN positive avg_profit may be exceptions.
- After SOL_1h test: if DISCARD, add risk_ceil increase to GLOBAL BLACKLIST.

**bar_budget scale-up pattern fully mapped:**
- XRP pairs: bar_budget 200 is CONFIRMED OPTIMUM. 300 DISCARDs for XRP_15m (iter 75) and XRP_1h (iter 76).
- SOL pairs: bar_budget 300 CONFIRMED KEEP for SOL_15m (iter 73) and SOL_1h (iter 86). SOL pairs unique.
- BTC_15m: bar_budget 300 DISCARD (iter 63). BTC pairs at 200.
- General rule: pairs with positive avg_profit accept budget increases; negative-profit pairs resist.

**conviction_buy_skip 0.45->0.40 universally collapses low-matched-ratio pairs:**
- XRP_15m (D iter 60): matched_ratio 2%->0%
- SOL_15m (D iter 85): matched_ratio 4.8%->0%
- Both pairs had matched_ratio <5% before test. Threshold: <5% matched_ratio = collapse risk.
- Higher matched_ratio pairs (ETH_5m, SOL_5m >5%) may be safer — test with caution.

---

## trader_a Benchmark Comparison (post-iter-95 best_knobs)
| Pair | PairCost | Target | Gap | AvgProfit | MaxDD% | Trend |
|------|----------|--------|-----|-----------|--------|-------|
| BTC_5m | 0.948 | < 0.85 | +0.098 | +$0.06 | 24.4% | needs onesided=2.0 next |
| BTC_15m | 0.933 | < 0.85 | +0.083 | +$0.50 | 23% | compound direction exhausted; try onesided=2.0 alone |
| BTC_1h | 0.799 | < 0.85 | -0.051 | -$0.33 | 9% | BEATS benchmark; onesided=2.0 final test |
| ETH_5m | 0.736 | < 0.85 | -0.114 | -$0.02 | 22.9% | BEATS benchmark; DD resolved; onesided=1.5 next |
| ETH_15m | 0.560 | < 0.85 | -0.290 | -$0.21 | 27% | BEST cost — volatile, bar_budget test next |
| ETH_1h | 0.706 | < 0.85 | -0.144 | -$0.49 | 17% | BEATS benchmark; bar_budget 250 next |
| SOL_5m | 0.733 | < 0.85 | -0.117 | +$0.05 | 22.3% | BEATS benchmark; onesided=1.5 next |
| SOL_15m | 0.786 | < 0.85 | -0.064 | +$0.17 | 9.5% | BEATS benchmark, PROFITABLE; onesided=2.0 pre-emptive |
| SOL_1h | 0.655 | < 0.85 | -0.195 | +$0.69 | 5.8% | BEST pair — risk_ceil test (best case for it) |
| XRP_5m | 0.909 | < 0.85 | +0.059 | -$0.32 | 68.7% | WORST pair, DD critical; skip=0.45 + onesided=2.0 |
| XRP_15m | 0.778 | < 0.85 | -0.072 | +$0.01 | 17% | BEATS benchmark; pace_urgency_lo next |
| XRP_1h | 0.674 | < 0.85 | -0.134 | +$1.08 | 6% | BEST avg_profit; pace_urgency_lo next |

**9 pairs beating trader_a pair_cost benchmark** (unchanged from rotation 5 — maintained through rotation 6).
Improvements this rotation: ETH_5m added (0.736) and SOL_5m improved (0.733, was 0.814).
BTC_5m and BTC_15m remain above benchmark — BTC_5m progress: DD fixed by 3.0, cost improvement at 2.0 next.

---

## Blacklist (per-pair)

- BTC_5m: unmatched_ratio tightening, sell_loss_start tightening, conviction_buy_skip 0.45 (D iter 33),
  conviction_buy_skip 0.55 (D iter 50), cheap_threshold 0.07 (D iter 17), cheap_threshold 0.12 (D iter 62),
  max_onesided_cost 5->3 (D iter 89 — sub-threshold, use 2.0). SKIP SERIES + CHEAP_THRESHOLD EXHAUSTED.
- BTC_15m: unmatched_ratio tightening, max_marginal_pair_cost below 1.01, cheap_threshold to 0.07,
  bar_budget 300 before cost fix (D iter 63), conviction_buy_skip 0.45 in ANY combination
  (D iters 51, 78, 90 — definitively confirmed collapse on BTC_15m).
- BTC_1h: risk_ceil tightening, sell_loss_start tightening, pace_urgency_hi loosening, bar_budget 400,
  conviction_buy_skip raising above 0.50, risk_ceil 0.15->0.20 standalone (D iter 80),
  max_onesided_cost 5->3 (D iter 91 — sub-threshold; try 2.0). Skip floor at 0.40.
- ETH_5m: unmatched_ratio tightening, conviction_buy_skip raising above 0.50,
  conviction_buy_skip 0.45->0.40 (on hold — test onesided=1.5 first)
- ETH_15m: unmatched_ratio tightening, conviction_buy_skip raising to 0.55,
  max_onesided_cost increasing above 1.5 (zero effect), max_onesided_cost 1.5->1.0 (D iter 94 — collapse)
- ETH_1h: max_onesided_cost increasing (D iter 55), conviction_buy_skip 0.40 (D iter 69),
  risk_ceil 0.15->0.20 (D iter 83). SKIP EXHAUSTED.
- SOL_5m: conviction_buy_skip raising to 0.55 (D iter 41), conviction_buy_skip 0.45->0.40
  (on hold until onesided=1.5 tested — matched_ratio 0.68% is high collapse risk)
- SOL_15m: min_unmatched_shares tightening, conviction_buy_skip raising above 0.50,
  conviction_buy_skip 0.40 (D iter 85 — confirmed collapse). SKIP SERIES FULLY EXHAUSTED.
- SOL_1h: conviction_buy_skip 0.35 (collapsed iter 57), conviction_buy_skip 0.45->0.40 (D iter 74),
  bar_budget 400 (test 300 validated — step to 400 after further confirmation). SKIP EXHAUSTED.
- XRP_5m: fill_ticks 10->15 (structural limit D iter 59), conviction_buy_skip raising above 0.50
- XRP_15m: conviction_buy_skip 0.40 (D iter 60 — collapsed), bar_budget 300 (D iter 75 — optimum at 200),
  risk_ceil 0.15->0.20 (D iter 87 — worsened). SKIP EXHAUSTED. BUDGET OPTIMUM AT 200.
- XRP_1h: conviction_buy_skip 0.45 (D iter 48), conviction_buy_skip 0.55 (D iter 61),
  bar_budget 300 (D iter 76 — optimum at 200), risk_ceil 0.15->0.20 (D iter 88 — worsened).
  BOTH SKIP DIRECTIONS EXHAUSTED. BUDGET OPTIMUM AT 200.

## Global Blacklist
- unmatched_ratio tightening: 3/3 DISCARDs (BTC_5m, ETH_5m, ETH_15m)
- sell_loss_start tightening: 2/2 DISCARDs (BTC_5m, BTC_1h)
- max_marginal_pair_cost tightening below 1.01: collapses matched_ratio
- pace_urgency_hi loosening: zero effect (BTC_1h 1/1 D)
- conviction_buy_skip RAISING above 0.50: 0/4 KEEP (ETH_5m, ETH_15m, SOL_5m, BTC_5m)
- bar_budget doubling (200->400): 1/1 DISCARD (BTC_1h) — use 300 as max
- bar_budget 200->300 on XRP pairs: 2/2 DISCARDs (XRP_15m iter 75, XRP_1h iter 76)
- max_onesided_cost increasing on ETH_1h (0/1, iter 55 — cap never triggers on 1h TFs at > $5)
- conviction_buy_skip 0.45 on BTC_15m: 0/3 KEEP (iters 51, 78, 90 — all collapse matching)
- conviction_buy_skip below 0.40: collapses pair formation (except BTC_1h at skip=0.40)
- conviction_buy_skip 0.40 on low-matched-ratio pairs (<5%): collapses (XRP_15m iter 60, SOL_15m iter 85)
- fill_ticks 10->15 (XRP_5m): structural microstructure limit at 54%
- risk_ceil increase on negative-avg-profit pairs: 0/4 KEEP (BTC_1h iter 80, ETH_1h iter 83,
  XRP_15m iter 87, XRP_1h iter 88). Hypothesis: only positive-profit pairs (SOL_1h) may benefit.
- max_onesided_cost 5->3 (BTC_5m iter 89, BTC_1h iter 91): sub-5% threshold — use 2.0 directly

---

## Priority Order for Next Rotation (rotation 7, starting at SOL_5m pair_index=6)

**onesided cap continuation (5m DD repairs mostly done, extend to remaining):**
1. SOL_5m: max_onesided_cost 2.0->1.5 (onesided series next step — highest KEEP-rate pair)
2. BTC_5m: max_onesided_cost 5.0->2.0 (proven effective at 2.0 on ETH/SOL, D at 3.0)
3. XRP_5m: conviction_buy_skip 0.50->0.45 FIRST (never tested; D analog is high value)
   followed by max_onesided_cost 5.0->2.0 (max_dd=68.7% critical regardless)

**Capital scaling on proven profitable pairs:**
4. SOL_1h: risk_ceil 0.15->0.20 (unique case: POSITIVE avg_profit + 5.8% DD — best candidate)
5. SOL_15m: max_onesided_cost 5.0->2.0 (pre-emptive cap; also next structural lever)

**BTC_15m single-change approach:**
6. BTC_15m: max_onesided_cost 5.0->2.0 ALONE (compound skip direction exhausted — isolate onesided)

**SOL_1h+ETH_1h capital/timing tests:**
7. SOL_1h: bar_budget 300->400 (after risk_ceil test; SOL pairs are budget-scalable)
8. ETH_1h: bar_budget 200->250 (cautious intermediate; matched_ratio=7% higher than XRP failures)

**ETH_15m and remaining pairs:**
9. ETH_15m: bar_budget 200->300 (onesided series floor confirmed; scale capital on best-cost pair)
10. BTC_1h: max_onesided_cost 5.0->2.0 (final onesided test; blacklist if sub-5%)
11. XRP_15m: pace_urgency_lo 0.35->0.30 (all other levers exhausted)
12. XRP_1h: pace_urgency_lo 0.35->0.45 (test timing as final available lever)

## Researcher Compliance

researcher_ack (iter 95, ETH_1h) correctly identified: re-eval at 35 bars, then bar_budget 200->250
per strategy.md priority queue #1. The re-eval ran correctly as a DISCARD (+1.8% insufficient).
Next step correctly identified as bar_budget 200->250. Full compliance confirmed.

For rotation 7, researcher resumes at SOL_5m (pair_index=6) and follows priority order above.
