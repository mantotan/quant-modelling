# Steps 5-8: Remaining Implementation

> Model passes all backtest acceptance criteria on BTC + ETH (as of 2026-03-19).
> These steps are now ACTIVE — proceeding with production readiness.

## Step 5: Polymarket Live Execution (~600 lines)

**Status: PARTIALLY BUILT** — Paper trading loop, executor interface, and market recorder exist. Live CLOB integration needed.

Already built:
- `src/qm/execution/loop.py` — TradingLoop (unified paper/live decision loop)
- `src/qm/execution/paper/engine.py` — PaperExecutor (instant sim fills, 8 tests)
- `src/qm/execution/audit.py` — Append-only audit log writer
- `src/qm/data/connectors/polymarket_recorder.py` — Gamma API market discovery + odds polling
- `src/qm/data/ingestion/bar_builder.py` — BarBuilder with get_partial_bar()
- `src/qm/data/connectors/ccxt_ws.py` — CcxtWebsocketConnector (auto-reconnect)

Still needed:
- `src/qm/execution/polymarket/client.py` — py-clob-client wrapper (retry, rate limit, secret redaction)
- `src/qm/execution/polymarket/market_scanner.py` — Reuse recorder's _discover_markets() + depth check
- `src/qm/execution/polymarket/order_manager.py` — Heartbeat supervisor (10s), order lifecycle, 60s timeout
- `src/qm/execution/polymarket/position_tracker.py` — Reconcile local vs Polymarket API on startup
- `src/qm/execution/polymarket/live_executor.py` — Same Executor interface, calls real CLOB API
- `src/qm/execution/reconciliation.py` — Startup state sync

## Step 6: Scheduler + Runner + CLI (~400 lines)

**Status: NOT STARTED** — Deferred until after paper trading validates the system.

- `src/qm/scheduler/runner.py` — SystemRunner with modes: ingest/paper/live
- `src/qm/scheduler/jobs.py` — Recalibration (6h), data check (30m), drift check (1h), portfolio snapshot (5m)
- `src/qm/scheduler/lifecycle.py` — Graceful startup (13-step sequence) and shutdown (7-step)
- CLI commands: ingest, backfill, features, train, backtest, paper, live, report

## Step 7: Rust Fast Path (~800 lines Rust) — ELEVATED TO CORE

**Status: SKELETON EXISTS** — `crates/qm-fast/` has empty module dirs. No Cargo.toml or Rust code yet.

**User requirement**: Rust handles ALL real-time signal processing, orderbook management, and trade execution.

- `crates/qm-fast/` — PyO3/maturin module, `#![forbid(unsafe_code)]`
- `src/features/calculator.rs` — Rust port of IntraBarFeatureCalculator (same 50 features)
- `src/features/ring_buffer.rs` — O(1) rolling statistics
- `src/orderbook/l2_book.rs` — L2 orderbook with delta application (Polymarket WS)
- `src/signing/eip712.rs` — Polymarket order signing via alloy crate (<1ms)
- `src/signing/keystore.rs` — Encrypted keyfile (AES-256-GCM)
- `src/qm/features/live_cache.py` — Python wrapper with automatic Rust/Python fallback
- CI parity tests: Rust vs Python outputs must match within 1e-9

## Step 8: Deployment (~200 lines)

**Status: NOT STARTED** — After paper trading + Rust fast path.

- `deploy/qm.service` — systemd unit (auto-restart, watchdog, env file)
- `deploy/paper_trade.service` — systemd unit for paper trading (built in Phase 2)
- `deploy/deploy.sh` — rsync → uv sync → maturin build → restart → health check → rollback
- `deploy/Dockerfile` — Multi-stage: Rust build → Python → runtime
- `docker-compose.prod.yml` — 127.0.0.1 only, restart:always, resource limits
