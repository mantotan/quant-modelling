# QM — ML/Quant Crypto Polymarket Prediction System

## What This Is
ML system predicting crypto price movements (BTC/ETH/XRP/SOL) on 5m/15m/1h timeframes to exploit edge on Polymarket binary prediction markets.

## Current State
- **Phases 1-3 + Steps 0-4 built**: Data infra, features (37+), backtest engine (dual-mode), LightGBM trainer + Optuna HPO, isotonic calibration, treelite compilation, signal generation, risk management, portfolio tracking, paper trading loop
- **Pulse model built**: Intra-bar prediction model (23 features, 16 samples/bar, Black-Scholes market sim)
- **1.9M bars downloaded**: 4 assets × 3 timeframes, 2022-2026, from Binance Vision (futures USDT-M)
- **227 unit tests passing**
- **Steps 5-8 deferred**: Live Polymarket execution, scheduler, Rust fast path, deployment — saved in `docs/STEPS_5_8_REMAINING.md`. Build only after model is profitable.

## Model Naming

| Name | Code Name | What It Does | When It Runs |
|------|-----------|-------------|-------------|
| **Sentinel** | `sentinel` | Bar-level: predicts NEXT bar direction from completed bars | Once per bar completion |
| **Pulse** | `pulse` | Late-bar: predicts CURRENT bar outcome from t=0.80 snapshot | Once at 80% of bar elapsed |

- Scripts: `scripts/train_sentinel.py`, `scripts/train_pulse.py`
- Model dirs: `data/models/sentinel/{ASSET}_{TF}/`, `data/models/pulse/{ASSET}_{TF}/`

## Current Focus: Deployment + Validation
Optimization is complete for BTC/ETH/SOL (all at structural floors). ETH is cleared for deployment (PBO=0.18). BTC/SOL need regime-bucketed validation. XRP baseline in progress.

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
- `docs/PULSE_MODEL_PLAN.md` — Pulse intra-bar model plan
- `src/qm/core/types.py` — All domain types (Bar, PartialBar, Signal, Asset, etc.)
- `src/qm/features/pipeline.py` — Sentinel feature computation pipeline (37 features)
- `src/qm/features/intrabar.py` — Pulse intra-bar feature calculator (23 features)
- `src/qm/backtest/engine.py` — Sentinel dual-mode backtesting engine
- `src/qm/backtest/intrabar_backtest.py` — Pulse intra-bar backtester (time-segmented)
- `src/qm/backtest/market_sim.py` — Black-Scholes market odds simulator
- `src/qm/model/trainers/lgbm_trainer.py` — Sentinel LightGBM + Optuna trainer
- `src/qm/model/trainers/pulse_trainer.py` — Pulse trainer (bar-level walk-forward)
- `src/qm/model/targets/intrabar.py` — Pulse training data generator (OHLC path sim)
- `src/qm/model/calibration/calibrator.py` — Isotonic calibration
- `src/qm/model/signals.py` — Signal generation (edge calculation)
- `scripts/download_historical.py` — Binance Vision bulk downloader
- `scripts/train_sentinel.py` — End-to-end Sentinel training
- `scripts/train_pulse.py` — End-to-end Pulse training

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
