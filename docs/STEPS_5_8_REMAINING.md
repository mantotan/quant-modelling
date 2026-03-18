# Steps 5-8: Remaining Implementation (Build After Model Is Profitable)

> Do NOT build these until the model passes backtest acceptance criteria.
> A perfect execution system with a bad model loses money faster.

## Step 5: Polymarket Live Execution (~600 lines)
- `src/qm/execution/polymarket/client.py` — py-clob-client wrapper (retry, rate limit, secret redaction)
- `src/qm/execution/polymarket/market_scanner.py` — Poll Gamma API every 15s, filter by asset/type/liquidity/time budget
- `src/qm/execution/polymarket/order_manager.py` — Heartbeat supervisor (10s), order lifecycle, 60s timeout
- `src/qm/execution/polymarket/position_tracker.py` — Reconcile local vs Polymarket API on startup
- `src/qm/execution/polymarket/live_executor.py` — Same interface as PaperExecutor, calls real CLOB API
- `src/qm/execution/reconciliation.py` — Startup state sync
- Blockchain: Alchemy/QuickNode RPC, nonce management, gas cap, tx retry

## Step 6: Scheduler + Runner + CLI (~400 lines)
- `src/qm/scheduler/runner.py` — SystemRunner with modes: ingest/paper/live
- `src/qm/scheduler/jobs.py` — Recalibration (6h), data check (30m), drift check (1h), portfolio snapshot (5m)
- `src/qm/scheduler/lifecycle.py` — Graceful startup (13-step sequence) and shutdown (7-step)
- CLI commands: ingest, backfill, features, train, backtest, paper, live, report

## Step 7: Rust Fast Path (~800 lines Rust)
- `crates/qm-fast/` — PyO3/maturin module, `#![forbid(unsafe_code)]`
- Rolling feature engine (O(1) incremental updates, pre-allocated ring buffers)
- L2 orderbook manager (delta application, price impact calculator)
- EIP-712 order signer (alloy crate, <1ms vs Python ~30ms)
- `src/qm/features/live_cache.py` — Python wrapper with automatic fallback
- CI parity tests: Rust vs Python outputs must match within 1e-9

## Step 8: Deployment (~200 lines)
- `deploy/qm.service` — systemd unit (auto-restart, watchdog, env file)
- `deploy/deploy.sh` — rsync → uv sync → maturin build → alembic migrate → restart → health check → rollback on failure
- `deploy/Dockerfile` — Multi-stage: Rust build → Python → runtime
- `docker-compose.prod.yml` — 127.0.0.1 only, restart:always, resource limits
