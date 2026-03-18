# QM — ML/Quant Crypto Polymarket Prediction System

## What This Is
ML system predicting crypto price movements (BTC/ETH/XRP/SOL) on 5m/15m/1h timeframes to exploit edge on Polymarket binary prediction markets.

## Current State
- **Phases 1-3 + Steps 0-4 built**: Data infra, features (37+), backtest engine (dual-mode), LightGBM trainer + Optuna HPO, isotonic calibration, treelite compilation, signal generation, risk management, portfolio tracking, paper trading loop
- **1.9M bars downloaded**: 4 assets × 3 timeframes, 2022-2026, from Binance Vision (futures USDT-M)
- **144 unit tests passing**
- **Steps 5-8 deferred**: Live Polymarket execution, scheduler, Rust fast path, deployment — saved in `docs/STEPS_5_8_REMAINING.md`. Build only after model is profitable.

## Current Focus: Model Training + Backtesting
The next priority is training a profitable model and validating it through rigorous backtesting before building any execution infrastructure.

## Architecture
- **Platform**: Python 3.11 (Windows dev/backtest, Ubuntu Linux production)
- **Data**: Polars, DuckDB, Hive-partitioned Parquet, TimescaleDB
- **ML**: LightGBM → treelite compiled inference, isotonic calibration
- **Backtest**: Dual-mode engine (vectorized for HPO, event-driven for validation)
- **Validation**: Walk-forward with purge+embargo, CPCV with PBO
- **Risk**: Fractional Kelly (0.25x), circuit breaker, correlation limits
- **Future**: Rust fast path (crates/qm-fast/) for <1.5ms live inference

## Key Conventions
- `pathlib.Path` everywhere (cross-platform)
- Polars over Pandas (Rust-backed, 10-50x faster)
- All feature computation via Polars expressions
- `structlog` with secret redaction for logging
- Prometheus metrics in `src/qm/monitoring/metrics.py`
- Tests in `tests/unit/` — run with `uv run pytest tests/unit/ -v`

## Key Files
- `PLAN.md` — Full implementation plan
- `docs/STEPS_5_8_REMAINING.md` — Deferred execution/deployment steps
- `src/qm/core/types.py` — All domain types (Bar, Signal, Asset, etc.)
- `src/qm/features/pipeline.py` — Feature computation pipeline
- `src/qm/backtest/engine.py` — Dual-mode backtesting engine
- `src/qm/model/trainers/lgbm_trainer.py` — LightGBM + Optuna trainer
- `src/qm/model/calibration/calibrator.py` — Isotonic calibration
- `src/qm/model/signals.py` — Signal generation (edge calculation)
- `scripts/download_historical.py` — Binance Vision bulk downloader

## Data
- `data/raw/ohlcv/` — Hive-partitioned Parquet (asset=X/timeframe=Y/date=Z/)
- ~1.9M bars: BTC/ETH 442k each, SOL/XRP 432k each (2022-2026)
- Binance Vision futures USDT-M, validated with 5-layer reconciliation

## Acceptance Criteria (must pass before going live)
| Metric | Threshold |
|--------|-----------|
| PBO | < 0.40 |
| Deflated Sharpe | > 0.0 |
| OOS Brier | < 0.25 |
| OOS ECE | < 0.05 |
| Net PnL after costs | > 0 |
| Max drawdown | < 30% |
