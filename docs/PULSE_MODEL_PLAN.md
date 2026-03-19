# Pulse Model — FULLY IMPLEMENTED

> Original plan archived at `docs/archive/PULSE_MODEL_PLAN_COMPLETE.md`

All 8 steps (A-H) are complete. The Pulse intra-bar prediction model is trained, backtested, and passes all acceptance criteria on BTC and ETH.

## Implemented Files

| Component | File | Status |
|-----------|------|--------|
| PartialBar type | `src/qm/core/types.py` | Done |
| BarBuilder.get_partial_bar() | `src/qm/data/ingestion/bar_builder.py` | Done |
| IntraBarFeatureCalculator (50 features) | `src/qm/features/intrabar.py` | Done |
| Training data generator (OHLC path sim) | `src/qm/model/targets/intrabar.py` | Done |
| Pulse trainer (bar-level walk-forward) | `src/qm/model/trainers/pulse_trainer.py` | Done |
| Intra-bar backtester (dual mode) | `src/qm/backtest/intrabar_backtest.py` | Done |
| Trading loop (on_bar_completed) | `src/qm/execution/loop.py` | Done |
| Training scripts | `scripts/train_pulse.py`, `scripts/train_pulse_v2.py`, `scripts/train_pulse_fast.py` | Done |

## Current Best Results (21 autoresearch iterations)

| Metric | BTC | ETH | Acceptance |
|--------|-----|-----|------------|
| OOS Brier | 0.1439 | 0.1966 | < 0.25 |
| OOS ECE | 0.0041 | 0.0216 | < 0.05 |
| Max DD | 28.7% | 5.25% | < 30% |
| Net PnL | $67.26 | $309.08 | > 0 |

## Optimal Config

- `time_pcts`: [0.30, 0.40, 0.60, 0.80]
- `objective.primary`: "brier"
- `walk_forward.n_splits`: 8
- `walk_forward.test_bars`: 2000

## Next Steps

See production readiness plan at `.claude/plans/concurrent-marinating-ladybug.md` for:
- PBO validation (last acceptance criterion)
- Paper trading system
- Rust fast path
- Live Polymarket execution
