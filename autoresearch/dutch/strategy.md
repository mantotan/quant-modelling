# Dutch Strategy
Updated: 2026-03-22 after manual experiment session (Exp1–Exp19)

## Summary

Manual experiment session replaced autoresearch loop. 19 experiments on BTC_15m identified
V7.1/V7.2/V7.3 engine changes + knob tuning that reduced total loss 95% across all 12 pairs.
6/12 pairs now profitable. All 12 knobs + best_knobs updated to Exp17 config.

### Key Findings (from deep bar/event JSONL analysis)

1. **Unmatched wrong-side waste was THE killer** — 98% of unmatched shares were on the losing
   side. The engine accumulated the cheap (market-unfavored) side more, which was almost always
   the side that lost. Root cause: symmetric bilateral buying + asymmetric market pricing.

2. **Model is 84% directionally accurate** — but lost money because the accumulation mechanic
   created wrong-side waste regardless of prediction quality.

3. **max_marginal_pair_cost is the dominant knob** — cliff between 1.02 (no effect) and 1.01
   (66% loss reduction). Below 1.00 starves the engine.

4. **Conviction-based buy gating was the breakthrough** — V7.1 (skip) + V7.2 (sizing) together
   converted the engine from pure bilateral to hybrid directional/bilateral. This aligned
   unmatched inventory with the model's prediction, turning waste into directional profit.

5. **One-sided cost cap (V7.3)** cut tail losses on wrong directional bets from $8-9 to $5 max.

---

## Current Config (all 12 pairs)

All pairs share identical config (Exp17). Per-pair tuning is the next phase.

| Knob | Value | Rationale |
|------|-------|-----------|
| max_marginal_pair_cost | 1.01 | Only allow cheap pairs through |
| spread_offset | 0.00 | Place at bid, not mid — saves ~1c/side |
| conviction_buy_skip | 0.50 | Skip side when model gives < 50% |
| conviction_size_floor | 0.30 | Bias order size toward favored side |
| max_onesided_cost | 5.00 | Cap tail loss on directional bets |
| min_unmatched_shares | 10 | Tighter unmatched discipline |
| unmatched_ratio | 0.25 | Tighter unmatched discipline |
| pace_urgency_lo | 0.35 | Earlier order placement |

---

## Per-Pair Status

### Profitable (6 pairs)

| Pair | PnL | MaxDD% | Correct% | Notes |
|------|-----|--------|----------|-------|
| BTC_5m | +$16 | 24% | 56% | Strongest model, consistent |
| BTC_15m | +$48 | 23% | 63% | Best overall performance |
| BTC_1h | +$21 | 6% | 52% | Lowest DD, fewest bars |
| ETH_1h | +$9 | 12% | 54% | Marginal, needs monitoring |
| SOL_1h | +$2 | 9% | 54% | Marginal, near breakeven |
| XRP_1h | +$13 | 6% | 57% | Good correct%, low DD |

**Pattern**: All BTC pairs + all 1h pairs profitable. 1h timeframe provides more time for pairs
to form and less noise.

### Unprofitable (6 pairs)

| Pair | PnL | MaxDD% | Correct% | Blocker |
|------|-----|--------|----------|---------|
| ETH_5m | -$149 | 84% | 41% | Weak model signal (correct < 45%) |
| ETH_15m | -$78 | 48% | 46% | Weak model signal |
| SOL_5m | -$59 | 32% | 46% | Weak model signal |
| SOL_15m | -$24 | 15% | 50% | Marginal, near breakeven |
| XRP_5m | -$115 | 67% | 43% | Weak model signal + low fill rate (58%) |
| XRP_15m | -$14 | 21% | 52% | Marginal, near breakeven |

**Pattern**: 5m timeframes are hardest (noise, model accuracy). ETH/XRP 5m are the worst —
correct_side_pct below 45% means model directional signal too weak. SOL_15m and XRP_15m are
near breakeven and may flip profitable with per-pair tuning.

---

## Next Actions (priority order)

1. **Per-pair tuning for marginal pairs** — SOL_15m, XRP_15m, ETH_15m are near breakeven.
   Try tighter max_onesided_cost ($3) or higher conviction_buy_skip (0.55) on these.

2. **Consider disabling worst pairs** — ETH_5m (-$149) and XRP_5m (-$115) may not be fixable
   with Dutch optimization; the Pulse model's directional accuracy is too low. Could exclude
   from live deployment.

3. **Scale up profitable pairs** — BTC pairs and 1h pairs could tolerate higher bar_budget
   or looser risk_ceil to deploy more capital on proven edge.

4. **Live paper trading validation** — backtest-to-live gap unknown for V7.3 config. The
   hybrid directional/bilateral approach may behave differently with live tick density.

---

## Experiment History (2026-03-22)

| Exp | Config Delta from Baseline | BTC_15m P&L | Key Insight |
|-----|---------------------------|-------------|-------------|
| Baseline | V7 defaults | -$549 | Pure bilateral, all pairs losing |
| Exp1 | max_chase 2→1 | -$430 | Chase adds 5-7c to fills |
| Exp2 | unmatched_ratio 0.50→0.35 | -$581 | Alone doesn't help |
| Exp3 | mpc=1.00 + ch=1 + um=0.35 | -$1 | Near breakeven but starved (20% match) |
| Exp6 | mpc=1.01 + ch=2 + um=0.35 | -$184 | Best knobs-only config |
| Exp8 | +conv_skip=0.55 | -$141 | Skip helps but mild threshold |
| Exp10 | +conv_skip=0.50 | -$22 | Strong — near breakeven |
| Exp13 | +conv_size=0.30 (no skip) | -$98 | Sizing alone insufficient |
| Exp14 | sizing + skip + bid + unm | +$19 | FIRST PROFITABLE |
| Exp17 | +max_onesided_cost=5 | +$47 | BEST — tail risk capped |

---

## Blacklists (obsolete — V7.3 config supersedes all prior pair-level blacklists)

Prior blacklists were for V7 pure bilateral mode. V7.3 hybrid mode changes the dynamics
fundamentally. All pair-level blacklists are cleared. New blacklists will be established
as per-pair tuning resumes.
