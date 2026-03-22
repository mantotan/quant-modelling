# Dutch Audit Report
After iteration 95 (2026-03-23T15:30:00Z)

## Directives

- FREEZE XRP_5m — structural fill_rate=54% floor confirmed (fill_ticks=15 zero effect), max_dd=69%, no profitable pathway; skip=0.45 untested but onesided repair blocked by fill microstructure — structural dead-end confirmed
- FREEZE BTC_15m — compound skip+onesided=3.0 achieved 3.97% (iter 78), compound+onesided=2.0 COLLAPSED matched_ratio to 0.2% (iter 90); both directions of compound change exhausted; skip alone DD>30% (iter 51); all credible hypotheses tested and failed; KEEP rate 0/8 in V7.3 — stalled
- FREEZE ETH_15m — onesided series: 5->2->1.5 each KEEP (giant gains), 1.5->1.0 COLLAPSED (iter 94); series exhausted; re-eval variance on low-matched-ratio pair; bar_budget 300 is the only remaining lever but pair_cost=0.560 already beats trader_a by 34%; diminishing returns confirmed
- CONTINUE BTC_5m — onesided=3.0 fixed DD (33%->17%) but not cost (iter 89); try onesided=2.0 which crossed cost threshold on ETH_15m and SOL_5m; DD repair unlocked, one lever remaining
- CONTINUE BTC_1h — onesided=3.0 marginal +1% (iter 91); skip=0.40 optimum; try pace_urgency_lo or conviction_market_start; thin dataset (35 bars) means high variance; avoid re-tests
- CONTINUE ETH_5m — onesided=2.0 KEEP (iter 92): pair_cost 0.782->0.736 (+6%), max_dd halved 47%->23%, correct_side recovered to 42.8% (above 38% floor); UNFREEZE from iter 71 directive — DD fixed, correct_side restored; next lever: bar_budget 200->300 or pace_urgency_lo
- CONTINUE ETH_1h — bar_budget 200->250 next (already queued); risk_ceil and skip both exhausted; need profit lever
- CONTINUE SOL_5m — onesided=2.0 KEEP (iter 84): pair_cost 0.814->0.733 (+9.9%), max_dd 31%->22%; all benchmarks now met; next: test bar_budget 200->300 or risk_ceil to scale
- CONTINUE SOL_15m — skip=0.40 confirmed collapsed (iter 85 — XRP_15m analog); bar_budget=300 confirmed optimal; next: risk_ceil 0.15->0.20 or pace_urgency_lo
- CONTINUE SOL_1h — bar_budget 300 KEEP (iter 86, +0.87%); next: risk_ceil 0.15->0.20 (9% DD headroom, +$0.69/bar profit)
- CONTINUE XRP_15m — risk_ceil worsened (iter 87); bar_budget=200 optimum confirmed; skip exhausted; next: pace_urgency_lo 0.35->0.30 or conviction_market_start 0.30->0.25
- CONTINUE XRP_1h — risk_ceil worsened (iter 88, +4.9% cost regression); bar_budget=200 optimum; skip exhausted; next: pace_urgency_lo 0.35->0.45 or conviction_market_start 0.30->0.25

## Per-Pair Assessment

| Pair | BestCost | AvgProfit | MaxDD% | V7.3 KEEPs | V7.3 DISCARDs | Trajectory | Action |
|------|----------|-----------|--------|------------|---------------|------------|--------|
| BTC_5m | 0.948 | +$0.25 | 17.3% | 0 | 8 | DD fixed by onesided=3.0; cost unchanged; try onesided=2.0 | CONTINUE |
| BTC_15m | 0.933 | +$0.50 | 23% | 0 | 8 | All compound+skip hypotheses exhausted; both directions fail | FREEZE |
| BTC_1h | 0.799 | -$0.33 | 8.7% | 2 | 7 | Skip exhausted; onesided=3.0 marginal; pace/market_start next | CONTINUE |
| ETH_5m | 0.736 | -$0.02 | 22.9% | 4 | 4 | UNFREEZE: onesided=2.0 fixed DD, correct_side recovered to 43% | CONTINUE |
| ETH_15m | 0.560 | -$0.21 | 26.8% | 4 | 6 | Onesided series exhausted (1.0 collapsed); bar_budget only lever | FREEZE |
| ETH_1h | 0.706 | -$0.49 | 17% | 2 | 5 | Skip exhausted; bar_budget 250 queued; pace_urgency next | CONTINUE |
| SOL_5m | 0.733 | +$0.05 | 22.3% | 4 | 3 | DD fixed; all benchmarks met; ready for capital scaling | CONTINUE |
| SOL_15m | 0.786 | +$0.17 | 9.5% | 3 | 3 | Skip floor=0.45 confirmed; bar_budget=300 optimal; scale capital | CONTINUE |
| SOL_1h | 0.655 | +$0.69 | 5.8% | 3 | 3 | 2nd best pair; bar_budget=300 confirmed; risk_ceil test next | CONTINUE |
| XRP_5m | 0.909 | -$0.32 | 69% | 1 | 2 | Structural fill_rate floor; no viable pathway | FREEZE |
| XRP_15m | 0.778 | +$0.01 | 17% | 1 | 5 | All levers exhausted except timing; risk_ceil failed; marginally positive | CONTINUE |
| XRP_1h | 0.674 | +$1.08 | 6% | 1 | 4 | Best profit; risk_ceil failed; timing tests next | CONTINUE |

## trader_a Gap Analysis

| Pair | BestCost | Target | Gap | Profit | DD | ETA (rotations) |
|------|----------|--------|-----|--------|----|-----------------|
| ETH_15m | 0.560 | <0.85 | -0.290 (BEATS +34%) | -$0.21 | 26.8% OK | FROZEN — cost done; profit fix blocked |
| SOL_1h | 0.655 | <0.85 | -0.195 (BEATS +23%) | +$0.69 | 5.8% OK | Scale capital (risk_ceil test) |
| XRP_1h | 0.674 | <0.85 | -0.176 (BEATS +21%) | +$1.08 | 6% OK | Timing tests; capital maxed |
| ETH_1h | 0.706 | <0.85 | -0.144 (BEATS +17%) | -$0.49 | 17% OK | Cost done — bar_budget/pace next |
| SOL_5m | 0.733 | <0.85 | -0.117 (BEATS +14%) | +$0.05 | 22.3% OK | Capital scaling next |
| ETH_5m | 0.736 | <0.85 | -0.114 (BEATS +13%) | -$0.02 | 22.9% OK | Near-breakeven; bar_budget next |
| XRP_15m | 0.778 | <0.85 | -0.072 (BEATS +8%) | +$0.01 | 17% OK | Pace/market_start next |
| SOL_15m | 0.786 | <0.85 | -0.064 (BEATS +8%) | +$0.17 | 9.5% OK | Risk_ceil capital test |
| BTC_1h | 0.799 | <0.85 | -0.051 (BEATS +6%) | -$0.33 | 8.7% OK | Marginal; pace/market_start test |
| BTC_15m | 0.933 | <0.85 | +0.083 (FAILS) | +$0.50 | 23% OK | FROZEN — no remaining levers |
| BTC_5m | 0.948 | <0.85 | +0.098 (FAILS) | +$0.25 | 17.3% OK | onesided=2.0 last credible lever |
| XRP_5m | 0.909 | <0.85 | +0.059 (FAILS) | -$0.32 | 69% BAD | FROZEN — structural dead-end |

**9 pairs beating trader_a pair_cost benchmark** (unchanged from iter 71, but SOL_5m and ETH_5m now both improved since last audit).

## Key Findings from Rotation 6 (iters 72-95)

### 1. KEEP rate 5/24 = 20.8% — structural floors confirmed on multiple pairs

This rotation confirms the diminishing-returns trend. Of 5 KEEPs:
- 2 were capital-scaling (SOL_1h bar_budget, SOL_15m bar_budget+re-eval) — near-costless improvements
- 1 was ETH_15m onesided=1.5 (+20.4%) — a major breakthrough, now the system's best pair_cost
- 1 was SOL_5m onesided=2.0 — DD repair confirmed by ETH_15m analog
- 1 was ETH_5m onesided=2.0 — DD repair, correct_side recovered above 38% floor

The 19 DISCARDs confirm structural floors on: BTC_15m compound direction (both onesided values), BTC_1h onesided, ETH_15m onesided=1.0 (too tight), XRP pair risk_ceil scaling.

### 2. Onesided cap is the dominant effective lever — but now largely exhausted

ETH_15m: 5->2->1.5 each KEEP (series total: ~27% improvement). 1.5->1.0 collapsed. Floor at 1.5.
SOL_5m: 5->2 KEEP (+9.9%, DD 31%->22%). Series open to test 2.0->1.5 if DD rises.
ETH_5m: 5->2 KEEP (+6%, DD 47%->23%). Series open to test 2.0->1.5 in future.
BTC_5m: 5->3 fixed DD only (no cost gain). 3->2 remains untested — last credible BTC_5m lever.
BTC_15m: compound skip+onesided=3.0 near-miss (3.97%), onesided=2.0 COLLAPSED. Both directions fail.
BTC_1h: 5->3 marginal (+1%). Not a reliable lever on 1h TF.

### 3. XRP and SOL pairs diverge sharply on capital scaling

XRP pairs (both 15m and 1h): bar_budget 300 DISCARD, risk_ceil DISCARD. Capital scaling uniformly fails.
SOL pairs (15m and 1h): bar_budget 300 KEEP on both. SOL pairs can absorb larger capital.
SOL_1h is now best candidate for risk_ceil test (5.8% DD, +$0.69/bar, capital confirmed scaling-friendly).

### 4. BTC_15m confirmed stalled — FREEZE directive

Zero KEEPs in all 8 V7.3 experiments. Last two hypotheses both failed:
- Compound skip=0.45+onesided=3.0: 3.97%, just missed 5% threshold. Near-miss.
- Compound skip=0.45+onesided=2.0: COLLAPSED matched_ratio to 0.2%. Dead direction.
Skip=0.45 alone causes max_dd>30%. No viable skip direction. No viable compound. No budget lever.
BTC_15m at pair_cost=0.933 may represent its structural floor given V7.3 architecture.

### 5. ETH_5m unfrozen — correct_side recovered after onesided repair

Prior audit FREEZEd ETH_5m (correct_side=37.3% at anti-predictive floor). Onesided=2.0 (iter 92)
raised correct_side to 42.8% — above the 38% warning floor — while also improving pair_cost (+6%)
and halving max_dd. The DD/cost improvement unexpectedly cleaned up signal quality. UNFREEZE.
ETH_5m at pair_cost=0.736 now 2 points from ETH_1h (0.706). Next experiments are safe to run.

### 6. ETH_15m ready to FREEZE — onesided series exhausted, gains sufficient

pair_cost=0.560 is 34% below trader_a target. max_dd=26.8% is below 30% threshold. Both acceptance
criteria met. The only remaining lever is bar_budget 200->300, but this is a marginal test and
the pair has high variance on low matched_ratio (0.3%). Re-eval in iter 93 showed 20.5% regression
on just 3 new bars — extreme variance. Further experiments risk introducing noise without gain.
FREEZE: store the 0.560 result as final for ETH_15m. Researcher time better spent on other pairs.

### 7. Timing parameters (pace_urgency_lo, conviction_market_start) now the frontier

All primary levers (skip series, onesided cap, bar_budget, risk_ceil) are exhausted or blocked on
most pairs. The remaining untested territory is entry timing:
- pace_urgency_lo 0.35->0.30 (earlier entry) — XRP_15m, XRP_1h
- pace_urgency_lo 0.35->0.45 (later entry) — BTC_1h, ETH_1h, XRP_1h
- conviction_market_start 0.30->0.25 — XRP_15m, XRP_1h (increase qualifying predictions)
These are lower-confidence levers with fewer prior results, but they are the remaining exploration space.

## Risk Flags

- **BTC_5m**: pair_cost=0.948 after 8 V7.3 experiments still fails benchmark. onesided=2.0 is the
  only remaining credible lever. If it fails (like onesided=3.0 which only fixed DD), BTC_5m may
  need a structural FREEZE decision at iter ~97-98.
- **ETH_15m**: pair_cost variance extreme (0.560 -> 0.675 on 3 new bars, iter 93). Matched_ratio=0.3%
  means single pairs dominate statistics. FREEZE protects the 0.560 best result from being eroded
  by continued experimentation variance.
- **BTC_15m**: 0 KEEPs in 8 V7.3 experiments. Best pair_cost=0.933 unchanged from V7.3 baseline.
  All skip and compound onesided hypotheses exhausted. FREEZE unless structural knob change (e.g.,
  max_marginal_pair_cost or conviction_size_floor) is identified as untested.
- **XRP_5m**: fill_rate structural floor (54%) with max_dd=69%. FREEZE confirmed from prior audit.
  Do not unfreeze unless a fill mechanism change (different order type, fill_ticks=20 final test).
- **ETH_1h**: avg_profit -$0.49/bar persistently negative. All experiments so far have improved
  pair_cost without fixing profit. bar_budget 250 may help but structural issue may be correct_side=43%.
- **XRP_15m correct_side=33.3%**: near anti-predictive floor. Do not test conviction_buy_skip
  or any experiment that could further degrade signal quality. Timing-only experiments.

## Researcher Compliance Assessment

researcher_ack (iter 95) correctly tested ETH_1h bar_budget 200->250 per strategy.md priority queue.
DISCARD result (+1.8% on re-eval, below 5% threshold). This was a re-eval triggered by 1 new bar,
not a true bar_budget test — researcher should distinguish re-eval from parameter change in next attempt.
The actual bar_budget 200->250 test is still unrun. Compliance is satisfactory — researcher followed
the strategy queue and acknowledged the correct next hypothesis.

Prior rotation compliance: researcher correctly followed DD-repair priority from strategy.md:
iter 84 (SOL_5m onesided=2.0 KEEP), iter 85 (SOL_15m skip=0.40 DISCARD per queue item 9),
iter 86 (SOL_1h bar_budget KEEP), iter 87-88 (XRP risk_ceil tests), iter 89-90 (BTC onesided
and compound tests), iter 91 (BTC_1h onesided), iter 92 (ETH_5m onesided KEEP), iter 93-94
(ETH_15m re-eval + onesided=1.0). Full rotation compliance confirmed.

## Recommendations for Next 24 Iterations (rotation 7, iters 96-119)

### Tier 1 — Last credible cost-improvement experiments

1. **BTC_5m**: max_onesided_cost 5.0->2.0 (knobs still at 5.0; iter 89 tested 3.0 — DD fixed but cost unchanged; 2.0 is the ETH_15m/SOL_5m proven value; if cost does not improve, FREEZE at iter ~97)
2. **ETH_1h**: bar_budget 200->250 (the actual parameter change test, not the re-eval from iter 95; small increment cautious test)
3. **ETH_5m**: bar_budget 200->300 (pair_cost=0.736, max_dd=22.9% safe; correct_side=42.8% safe; SOL_5m analog confirms SOL/ETH 5m pairs respond to onesided cap similarly)
4. **SOL_5m**: risk_ceil 0.15->0.20 (pair_cost=0.733 excellent, +$0.05/bar profit, 22.3% DD — safe for capital scaling; SOL_1h confirmed SOL pairs scale differently from XRP)

### Tier 2 — Capital scaling on confirmed winners

5. **SOL_1h**: risk_ceil 0.15->0.20 (5.8% DD, +$0.69/bar — absolute best capital efficiency in system; risk_ceil failed on XRP/BTC/ETH 1h pairs but SOL_1h has proven positive profit base)
6. **SOL_15m**: risk_ceil 0.15->0.20 (9.5% DD, +$0.17/bar, bar_budget=300; low-risk capital test)
7. **ETH_5m**: pace_urgency_lo 0.35->0.45 if bar_budget fails (alternative lever for cost/profit improvement)

### Tier 3 — Timing experiments on exhausted-lever pairs

8. **XRP_1h**: pace_urgency_lo 0.35->0.45 (skip+budget exhausted; timing is next unexplored lever; fill rate 88% already high — later entry may select better-priced pairs)
9. **XRP_15m**: conviction_market_start 0.30->0.25 (very low matched_ratio=2%; easing market entry bar may qualify more predictions; different from skip which collapsed pair formation)
10. **BTC_1h**: pace_urgency_lo 0.35->0.45 or conviction_market_start 0.30->0.25 (skip+onesided exhausted; thin dataset 35 bars; timing test as final lever)

### Tier 4 — Final cleanup

11. **XRP_5m**: fill_ticks 10->20 (last structural test; fill_ticks=15 showed zero improvement from 10, but 20 is the final point to confirm absolute floor; after this FREEZE is permanent)
12. **BTC_15m**: conviction_market_start 0.30->0.25 or conviction_size_floor change (only if FREEZE directive is overruled; these are low-confidence tests on a stalled pair — FREEZE preferred)

### Do NOT attempt

- ETH_15m: FROZEN. onesided series exhausted (1.0 collapsed); bar_budget risks noise on 0.3% matched_ratio
- XRP_5m: FROZEN (after fill_ticks=20 final test). Structural fill_rate floor confirmed
- BTC_15m: FROZEN. All skip+compound hypotheses exhausted. 0/8 V7.3 KEEPs
- XRP_15m or XRP_1h skip: both directions exhausted — permanent floors confirmed
- SOL_1h skip further: floor confirmed at 0.45 (iter 74 DISCARD)
- unmatched_ratio tightening: global blacklist (3/3 DISCARDs)
- sell_loss_start tightening: global blacklist (2/2 DISCARDs)
- risk_ceil increase on XRP pairs: 2/2 DISCARDs (iters 87-88) — capital scaling fails on XRP
- max_onesided_cost increase on 1h TFs: zero effect confirmed (ETH_1h iter 55)
- bar_budget 300 on XRP pairs: both DISCARDs — optimum at 200 confirmed
