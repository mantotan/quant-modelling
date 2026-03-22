# Dutch Audit Report
After iteration 46 (2026-03-22T22:50:00Z)

## Directives
- PRIORITIZE ETH_1h — 2 KEEPs in first rotation, best improvement rate: pair_cost 0.9528->0.7058 (25.9% drop), next experiment pending
- PRIORITIZE XRP_15m — 1 KEEP already: pair_cost 0.9558->0.7780 (18.6% drop), conv_skip=0.45 confirmed, needs scale testing
- PRIORITIZE SOL_1h — best pair_cost in system (0.6967), 1 KEEP, throughput still only 2%; matched_ratio boost is the #1 lever
- PRIORITIZE XRP_1h — best baseline pair_cost (0.7157), 0 experiments yet, untouched in this rotation; high-value pair needs attention
- FREEZE ETH_5m — correct_side=40%, conv_skip=0.60 DISCARD confirms anti-predictive at all confidence levels; no viable path
- FREEZE SOL_5m — correct_side=40% post-skip (iter41 DISCARD: skip=0.55 worsened all metrics including tripling DD); structurally challenged
- CONTINUE BTC_5m — profitable baseline, conv_skip=0.45 DISCARD informative (profit flips negative); try bar_budget or max_onesided_cost next
- CONTINUE BTC_15m — best correct_side (63%), no param changes tried yet; needs conv_skip=0.45 test
- CONTINUE BTC_1h — bar_budget=400 DISCARD; try conv_skip=0.45 next
- CONTINUE ETH_15m — conv_skip=0.55 DISCARD; correct_side improving with more data needed
- CONTINUE SOL_15m — near-breakeven; min_unmatched_shares DISCARD; try conv_skip=0.40 next
- CONTINUE XRP_5m — pair_cost improved from 0.9973 to 0.9085 via dataset growth alone (KEEP); still above target, try fill_ticks=15

## Per-Pair Assessment
| Pair | BestCost | AvgProfit | MaxDD% | KEEPs | Experiments | Trajectory | Action |
|------|----------|-----------|--------|-------|-------------|------------|--------|
| BTC_5m | 0.9480 | +$0.055 | 24% | 0 | 1 (DISCARD) | Conv_skip=0.45 flipped profit; needs different approach | CONTINUE |
| BTC_15m | 0.9334 | +$0.498 | 23% | 0 | 1 (re-run, not real) | Untested; strong baseline | CONTINUE |
| BTC_1h | 0.9378 | +$0.827 | 6% | 0 | 1 (DISCARD) | Bar_budget=400 worse; needs conv_skip | CONTINUE |
| ETH_5m | 0.9087 | -$0.517 | 84% | 0 | 1 (DISCARD) | Anti-predictive confirmed at all skip levels | FREEZE |
| ETH_15m | 0.9220 | -$0.803 | 48% | 0 | 1 (DISCARD) | Conv_skip=0.55 improved cost but hurt profit | CONTINUE |
| ETH_1h | 0.7058 | -$0.487 | 17% | 2 | 2 KEEPs | Best trajectory: 25.9% cost reduction in 2 iters | PRIORITIZE |
| SOL_5m | 0.9455 | -$0.205 | 108% | 0 | 1 (DISCARD) | DD tripled with skip=0.55; structurally broken | FREEZE |
| SOL_15m | 0.9133 | -$0.245 | 15% | 0 | 1 (DISCARD) | Min_unmatched DISCARD; fresh baseline 0.9133 | CONTINUE |
| SOL_1h | 0.6967 | +$0.817 | 9% | 1 | 1 (dataset re-eval) | Best profit/bar; throughput bottleneck | PRIORITIZE |
| XRP_5m | 0.9085 | -$0.323 | 69% | 1 | 1 (dataset re-eval) | Cost improved 8.9% via data; fill_rate weak | CONTINUE |
| XRP_15m | 0.7780 | +$0.010 | 17% | 1 | 2 (1 re-run + KEEP) | 18.6% cost drop with conv_skip=0.45 | PRIORITIZE |
| XRP_1h | 0.7157 | +$0.512 | 6% | 0 | 0 | Best baseline, untouched this rotation | PRIORITIZE |

## trader_a Gap Analysis
| Pair | BestCost | Target | Gap | Profit | DD Gap | KEEPs | ETA (rotations) |
|------|----------|--------|-----|--------|--------|-------|-----------------|
| SOL_1h | 0.6967 | <0.85 | -0.153 (BEATS) | +$0.82 | 9% (OK) | 1 | DONE on cost; scale now |
| XRP_1h | 0.7157 | <0.85 | -0.134 (BEATS) | +$0.51 | 6% (OK) | 0 | DONE on cost; scale now |
| XRP_15m | 0.7780 | <0.85 | -0.072 (BEATS) | +$0.01 | 17% (OK) | 1 | DONE on cost; scale now |
| ETH_1h | 0.7058 | <0.85 | -0.144 (BEATS) | -$0.49 | 17% (OK) | 2 | Cost done; fix profit |
| BTC_15m | 0.9334 | <0.85 | +0.083 | +$0.50 | 23% (OK) | 0 | ~2-3 rotations |
| BTC_5m | 0.9480 | <0.85 | +0.098 | +$0.06 | 24% (OK) | 0 | ~3-4 rotations |
| BTC_1h | 0.9378 | <0.85 | +0.088 | +$0.83 | 6% (OK) | 0 | ~2-3 rotations |
| SOL_15m | 0.9133 | <0.85 | +0.063 | -$0.25 | 15% (OK) | 0 | ~3 rotations if signal exists |
| ETH_15m | 0.9220 | <0.85 | +0.072 | -$0.80 | 48% (bad) | 0 | Unclear — DD too high |
| XRP_5m | 0.9085 | <0.85 | +0.058 | -$0.32 | 69% (bad) | 1 | ~2-3 rotations on cost; DD unsustainable |
| ETH_5m | 0.9087 | <0.85 | +0.059 | -$0.52 | 84% (bad) | 0 | FROZEN — anti-predictive |
| SOL_5m | 0.9455 | <0.85 | +0.096 | -$0.21 | 108% (bad) | 0 | FROZEN — DD catastrophic |

## Key Findings from This Rotation

### 1. Four pairs already beating trader_a cost benchmark
SOL_1h (0.697), ETH_1h (0.706), XRP_1h (0.716), XRP_15m (0.778) all below 0.85 target.
Of these, SOL_1h and XRP_1h are profitable. ETH_1h shows negative avg_profit despite great cost
(likely throughput effect: only 7% matched_ratio means the few pairs that form are chosen well
but profit/bar is dragged by many unmatched bars). XRP_15m is barely positive (+$0.01/bar).

### 2. conv_skip=0.45 is powerful but inconsistent
- ETH_1h: KEEP (cost -7.7%, profit maintained at -$0.49 with relaxed threshold)
- XRP_15m: KEEP (cost -18.6%, profit turned positive)
- BTC_5m: DISCARD (profit flipped negative: +$0.055 -> -$0.040)
- ETH_5m: DISCARD (all metrics worsened)
- SOL_5m: DISCARD (DD tripled)

Pattern: conv_skip=0.45 works when the pair has correct_side >= 43%. BTC_5m at 56% correct should
benefit but the DISCARD shows the signal is weak at 45-50% confidence range. Hypothesis: BTC_5m
correct_side is concentrated at >60% confidence bets; lowering threshold introduces noise.

### 3. Dataset growth yielding natural improvements
Iters 39 (ETH_1h), 43 (SOL_1h), 44 (XRP_5m) were dataset re-evals showing 8-20% cost improvements.
This suggests backtest variance at lower bar counts was masking true performance. As bar count grows,
costs naturally improve. This is a tailwind — pairs will continue to improve with more data.

### 4. Anti-predictive pairs confirmed
ETH_5m (correct_side 40% at skip=0.50, 34% at skip=0.60 — worse with more selectivity) and
SOL_5m (DD tripled with skip=0.55) are structurally broken. The model signal direction is wrong.
No parameter tuning can fix a model that is net negative directionally. These should be FROZEN.

### 5. BTC pairs untested for conv_skip
BTC_15m has 0 real param experiments post-V7.3 (iter35 was a re-run, not a change). BTC_1h only
tested bar_budget. Neither has tested conv_skip=0.45 yet. Given BTC_15m's 63% correct_side,
this is the highest-priority untested hypothesis in the system.

### 6. ETH_1h profit is negative despite great cost
ETH_1h best_cost=0.706 with avg_profit=-$0.487/bar. The cost is excellent (beats benchmark by 14%)
but the absolute profit is negative. Two causes: (a) matched_ratio=7% means most bars earn nothing,
(b) correct_side dropped 46.7%->43.3% with skip=0.45. Try max_onesided_cost=7.0 to capture more
upside on the correct-direction bets, or bar_budget=300 to scale the 43% correct bets.

## Risk Flags
- **ETH_5m**: Anti-predictive model confirmed (40% correct, worsening with skip). FREEZE — no recovery path.
- **SOL_5m**: DD=108% after single experiment. FREEZE — catastrophic drawdown risk.
- **ETH_15m**: DD=48% with avg_profit=-$0.80 and correct_side dropping with skip. Monitor closely; may need FREEZE next audit.
- **XRP_5m**: fill_rate=53% (worst in system). High pair_cost volatility. Natural dataset growth helped but DD=69% remains unacceptable.
- **ETH_1h**: Profit negative despite best-in-class cost. Risk of over-optimizing cost while ignoring P&L sustainability.
- **BTC_5m**: conv_skip=0.45 flipped profit sign. The helpful signal may be concentrated only at high conviction (>0.55). Do not lower skip further.

## Recommendations for Next 24 Iterations

### Tier 1 — Scale confirmed winners (4 pairs)
1. **SOL_1h** (best_cost=0.697, +$0.82/bar): conviction_buy_skip 0.50->0.40 or bar_budget 200->400.
   These have lowest DD (9%) and proven profitability. Scale is safe here.
2. **XRP_1h** (best_cost=0.716, +$0.51/bar): conviction_buy_skip 0.50->0.40 and bar_budget 200->400.
   Zero experiments — immediate priority. Best cost+profit combination in system.
3. **XRP_15m** (best_cost=0.778, skip=0.45 confirmed): bar_budget 200->300, then min_unmatched_shares 10->15.
   Profit is barely positive (+$0.01); scale carefully with bar_budget increase.
4. **ETH_1h** (best_cost=0.706, skip=0.45 confirmed): max_onesided_cost 5->7, then bar_budget 200->300.
   Profit is negative; need to understand if onesided cap or budget is limiting upside.

### Tier 2 — Unlock BTC pairs
5. **BTC_15m**: conviction_buy_skip 0.50->0.45 — highest priority untested, 63% correct_side.
6. **BTC_1h**: conviction_buy_skip 0.50->0.45 — 52% correct, low DD, safe to experiment.
7. **BTC_5m**: bar_budget 200->300 or max_onesided_cost 5->7. Do NOT lower conv_skip further.

### Tier 3 — Weak pairs (limited resources)
8. **SOL_15m**: conviction_buy_skip 0.50->0.40 — 50% correct_side means bilateral symmetry; lower skip
   should not hurt directionally and may improve throughput.
9. **ETH_15m**: max_onesided_cost 5->3 — tight the tail to reduce DD before more throughput experiments.
10. **XRP_5m**: fill_simulator.fill_ticks 10->15 — address 53% fill_rate as root cause before other changes.

### Do NOT attempt
- ETH_5m: FROZEN. Any experiment wastes an iteration.
- SOL_5m: FROZEN. DD already at 108%.
- unmatched_ratio tightening: Global blacklist (3/3 DISCARDs).
- sell_loss_start tightening: Global blacklist (2/2 DISCARDs).
- max_marginal_pair_cost below 1.01: Collapses matched_ratio.

### Researcher compliance note
Researcher correctly ran XRP_15m conv_skip=0.45 per strategy.md priority queue (iter46 KEEP).
researcher_ack (iter45) correctly identified next hypothesis. No compliance issues detected.
Strategy.md priorities are broadly correct but need updating to reflect: (a) ETH_5m and SOL_5m
FREEZE, (b) 4 pairs already beating trader_a cost benchmark. Strategist should update strategy.md
at next iteration (iters_since_strategist=13, already overdue).
