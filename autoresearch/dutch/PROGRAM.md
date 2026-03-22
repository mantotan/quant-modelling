# Dutch Accumulation Autoresearch

## Objective

Autonomously optimize DutchConfig parameters for bilateral accumulation of Polymarket binary UP/DOWN tokens. Target: replicate the performance of trader trader_a ((redacted)).

## Key Metrics (targets from trader_a analysis)

| Metric | Target | Description |
|--------|--------|-------------|
| avg_pair_cost | < 0.85 | Average cost per matched pair (< 1.0 = profit) |
| avg_profit | > 0 | Mean profit per bar |
| max_dd_pct | < 30% | Max drawdown as % of bar budget |
| correct_side_pct | > 0.55 | Fraction of bars where unmatched side wins |
| sell_ratio | 0.10-0.40 | Sell events / buy events (capital recycling) |

Note: `matched_ratio` and `fill_rate` are tracked but NOT KEEP gates — backtest produces
lower values than live (12% fill, 6% match) due to tick density differences. These improve
when moving to live execution.

## Architecture

### Per-Pair Config System

Each of 12 asset/timeframe pairs has independent knobs:
- `knobs_{ASSET}_{TF}.json` — working config for that pair
- `best_knobs_{ASSET}_{TF}.json` — last KEEP checkpoint for that pair
- Pairs: BTC_5m, BTC_15m, BTC_1h, ETH_5m, ETH_15m, ETH_1h, SOL_5m, SOL_15m, SOL_1h, XRP_5m, XRP_15m, XRP_1h
- Fallback: `knobs.json` / `best_knobs.json` (shared defaults)

### Dispatch Loop

- **Backtest mode**: `/loop 2m dutch-dispatch` — researcher rotates through pairs (~10s each)
- **Live mode**: `/loop 20m dutch-dispatch` — EXIT while incubating
- **Pair rotation**: dispatch advances `current_pair` after each researcher invocation
- **Full rotation**: 12 iterations = all pairs tested once

### Roles

- **Researcher**: ONE parameter change on ONE pair → run backtest → KEEP/DISCARD
- **Strategist**: Every 12 iterations (1 rotation), per-pair analysis + priority queues
- **Auditor**: Every 24 iterations (2 rotations), deep analysis, FREEZE/PRIORITIZE/RESET directives
- **Monitor**: Check PM2 health + anomaly detection (skips PM2 in backtest mode)

## Tunable Parameters (V7 + V7.1/V7.2/V7.3)

See `knobs_{PAIR}.json` for per-pair parameters. Key categories:
- Pair cost (cheap_threshold, max_marginal_pair_cost)
- Pacing (pace_urgency_lo/hi, max_per_prediction, bar_budget, order_size)
- Risk budget (risk_floor, risk_ceil, risk_t_start, risk_t_end, risk_exponent)
- Conviction buy-side (conviction_buy_skip, conviction_size_floor) — **V7.1/V7.2**
- Conviction sell-side (conviction_market_start, conviction_market_full)
- Unmatched cap (min_unmatched_shares, unmatched_ratio)
- One-sided cost cap (max_onesided_cost) — **V7.3**
- Balance (max_side_fraction)
- Sell (sell_loss_start, sell_dump_start, sell_max_fraction, sell_min_shares, rebalance_warmup)
- Fill simulator (fill_ticks, sweep_threshold, chase_threshold, max_chase, spread_offset, cancel_distance)

### V7.1: Conviction Buy Skip (2026-03-22)
Skip buying the unfavored side when model conviction is below threshold.
- `conviction_buy_skip=0.50` — skip side when model gives it < 50% chance.
- Converts engine from pure bilateral to hybrid directional/bilateral.
- Impact: correct_side_pct 10% → 60%, eliminates most wrong-side waste.

### V7.2: Conviction-Aware Buy Sizing (2026-03-22)
Scale order size by model confidence: `size_mult = floor + (1 - floor) * model_p_side`.
- `conviction_size_floor=0.30` — unfavored side gets 0.3x–1.0x sizing.
- Biases accumulation toward model-favored side even when both sides buy.

### V7.3: One-Sided Cost Cap (2026-03-22)
Limit total spend when no matched pairs exist (pure directional bet).
- `max_onesided_cost=5.0` — max $5 before first pair forms.
- Prevents $8-9 tail losses on wrong directional bets.

## Fill Simulator V3 (2026-03-21)

Maker-only simulation matching production `post_only=True` behavior:
- **Buy orders**: placed at bid (maker) or at ask-0.01 (aggressive tiers). Never at/above ask.
- **Sell orders**: placed at ask (maker on sell side). Fill when bid >= ask.
- **fill_ticks=10** (~5s): ask must stay at/below limit for 10 consecutive book updates.
- **Sweep detection**: price passes through limit by >= 1c → instant fill on tick 1.
- **Zero-depth rejection**: no depth at limit price → order stays pending.
- **Chase**: below ask only, max 2 chases, cancel at >= 5c drift.
- **Sell depth**: checks `book.bids` (not asks) for sell-side liquidity.

## Current Best Config (Exp17, 2026-03-22)

Validated across all 12 pairs. 6/12 profitable, total loss reduced 95% vs V7 baseline.

| Knob | Old (V7) | New (V7.3) | Why |
|------|----------|------------|-----|
| max_marginal_pair_cost | 1.03 | 1.01 | Only allow cheap pairs |
| spread_offset | 0.01 | 0.00 | Bid-based pricing, saves ~1c/side |
| conviction_buy_skip | N/A | 0.50 | Skip losing side when model >50% confident |
| conviction_size_floor | N/A | 0.30 | Bias order size toward favored side |
| max_onesided_cost | N/A | 5.00 | Cap tail loss on directional bets |
| min_unmatched_shares | 20 | 10 | Tighter unmatched discipline |
| unmatched_ratio | 0.50 | 0.25 | Tighter unmatched discipline |
| pace_urgency_lo | 0.50 | 0.35 | Earlier order placement |

### Validation Results (Exp17)
| Pair | PnL | MaxDD% | Correct% | Profitable? |
|------|-----|--------|----------|-------------|
| BTC_5m | +$16 | 24% | 56% | YES |
| BTC_15m | +$48 | 23% | 63% | YES |
| BTC_1h | +$21 | 6% | 52% | YES |
| ETH_5m | -$149 | 84% | 41% | No |
| ETH_15m | -$78 | 48% | 46% | No |
| ETH_1h | +$9 | 12% | 54% | YES |
| SOL_5m | -$59 | 32% | 46% | No |
| SOL_15m | -$24 | 15% | 50% | No |
| SOL_1h | +$2 | 9% | 54% | YES |
| XRP_5m | -$115 | 67% | 43% | No |
| XRP_15m | -$14 | 21% | 52% | No |
| XRP_1h | +$13 | 6% | 57% | YES |
| **TOTAL** | **-$331** | | | 6/12 |
| vs Baseline | -$6,391 | | | 0/12 |

## Data Sources

### Backtest mode (primary)
- Tick Parquet: `data/raw/polymarket_ticks/asset={A}/timeframe={TF}/date={D}/ticks_*.parquet`
- Backtest output: `autoresearch/dutch/backtest_results.tsv` (10 metrics + max_dd_pct)
- Backtest bar JSONL: `data/dutch_backtest/{A}_{TF}/bars_*.jsonl` (optional, `--save-bars`)
- Script: `scripts/dutch_backtest.py --knobs-dir autoresearch/dutch/ --pair {PAIR}`

### Live mode
- Bar summaries: `data/dutch_paper/BTC_{tf}/bars_*.jsonl`
- Events: `data/dutch_paper/BTC_{tf}/events_*.jsonl`
- PM2 logs: `data/dutch_{tf}.err.log`, `data/dutch_{tf}.out.log`

## results.tsv Format

```
iteration  pair  timestamp  status  avg_pair_cost  avg_profit  total_profit  matched_ratio  fill_rate  correct_side_pct  budget_util  sell_ratio  max_dd_pct  bars_evaluated  description  param_changed
```

## Auditor Directives

| Directive | Effect |
|-----------|--------|
| FREEZE {pair} | Lock pair's best_knobs, skip in rotation |
| PRIORITIZE {pair} | Give pair 2 extra iterations |
| RESET {pair} {hash} | Restore pair's knobs from git commit |
| CONTINUE | Keep rotating normally |
