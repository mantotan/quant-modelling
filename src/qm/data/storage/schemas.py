"""Database schema definitions and SQL for TimescaleDB.

All table creation, hypertable configuration, indexing, retention policies,
and compression settings are defined here.
"""

# ── Table creation SQL ──────────────────────────────────────────────

CREATE_TRADES_TABLE = """
CREATE TABLE IF NOT EXISTS trades (
    time        TIMESTAMPTZ NOT NULL,
    asset       TEXT NOT NULL,
    exchange    TEXT NOT NULL,
    price       DOUBLE PRECISION NOT NULL,
    size        DOUBLE PRECISION NOT NULL,
    side        TEXT,
    trade_id    TEXT
);
"""

CREATE_OHLCV_TABLE = """
CREATE TABLE IF NOT EXISTS ohlcv (
    time        TIMESTAMPTZ NOT NULL,
    asset       TEXT NOT NULL,
    timeframe   TEXT NOT NULL,
    exchange    TEXT NOT NULL DEFAULT 'aggregated',
    open        DOUBLE PRECISION NOT NULL,
    high        DOUBLE PRECISION NOT NULL,
    low         DOUBLE PRECISION NOT NULL,
    close       DOUBLE PRECISION NOT NULL,
    volume      DOUBLE PRECISION NOT NULL,
    trade_count INTEGER NOT NULL,
    vwap        DOUBLE PRECISION NOT NULL
);
"""

CREATE_POLYMARKET_SNAPSHOTS_TABLE = """
CREATE TABLE IF NOT EXISTS polymarket_snapshots (
    time          TIMESTAMPTZ NOT NULL,
    condition_id  TEXT NOT NULL,
    token_id_up   TEXT NOT NULL,
    token_id_down TEXT NOT NULL,
    asset         TEXT NOT NULL,
    market_type   TEXT NOT NULL,
    window_start  TIMESTAMPTZ NOT NULL,
    window_end    TIMESTAMPTZ NOT NULL,
    mid_up        DOUBLE PRECISION,
    mid_down      DOUBLE PRECISION,
    spread_up     DOUBLE PRECISION,
    volume        DOUBLE PRECISION
);
"""

CREATE_AUDIT_LOG_TABLE = """
CREATE TABLE IF NOT EXISTS audit_log (
    time         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    event_type   TEXT NOT NULL,
    asset        TEXT,
    market_type  TEXT,
    signal_id    TEXT,
    details      JSONB NOT NULL DEFAULT '{}'
);
"""

# ── Hypertable creation ─────────────────────────────────────────────

HYPERTABLE_TRADES = """
SELECT create_hypertable('trades', 'time',
    chunk_time_interval => INTERVAL '1 hour',
    if_not_exists => TRUE
);
"""

HYPERTABLE_OHLCV = """
SELECT create_hypertable('ohlcv', 'time',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);
"""

HYPERTABLE_PM_SNAPSHOTS = """
SELECT create_hypertable('polymarket_snapshots', 'time',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);
"""

HYPERTABLE_AUDIT_LOG = """
SELECT create_hypertable('audit_log', 'time',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);
"""

# ── Indexes ─────────────────────────────────────────────────────────

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_trades_asset_time ON trades (asset, time DESC);",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_ohlcv_unique ON ohlcv (time, asset, timeframe, exchange);",
    "CREATE INDEX IF NOT EXISTS idx_pm_snap_asset_time ON polymarket_snapshots (asset, time DESC);",
    "CREATE INDEX IF NOT EXISTS idx_audit_event_time ON audit_log (event_type, time DESC);",
]

# ── Retention policies ──────────────────────────────────────────────

RETENTION_TRADES_7D = """
SELECT add_retention_policy('trades', INTERVAL '7 days', if_not_exists => TRUE);
"""

RETENTION_PM_SNAPSHOTS_90D = """
SELECT add_retention_policy('polymarket_snapshots', INTERVAL '90 days', if_not_exists => TRUE);
"""

# ── Compression ─────────────────────────────────────────────────────

COMPRESSION_OHLCV = """
ALTER TABLE ohlcv SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'asset,timeframe,exchange',
    timescaledb.compress_orderby = 'time DESC'
);
"""

COMPRESSION_POLICY_OHLCV = """
SELECT add_compression_policy('ohlcv', INTERVAL '1 day', if_not_exists => TRUE);
"""

# ── Upsert for idempotent backfill ──────────────────────────────────

UPSERT_OHLCV = """
INSERT INTO ohlcv (time, asset, timeframe, exchange, open, high, low, close, volume, trade_count, vwap)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
ON CONFLICT (time, asset, timeframe, exchange) DO NOTHING;
"""

INSERT_TRADE = """
INSERT INTO trades (time, asset, exchange, price, size, side, trade_id)
VALUES ($1, $2, $3, $4, $5, $6, $7);
"""

INSERT_POLYMARKET_SNAPSHOT = """
INSERT INTO polymarket_snapshots (
    time, condition_id, token_id_up, token_id_down,
    asset, market_type, window_start, window_end,
    mid_up, mid_down, spread_up, volume
)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12);
"""

INSERT_AUDIT = """
INSERT INTO audit_log (time, event_type, asset, market_type, signal_id, details)
VALUES ($1, $2, $3, $4, $5, $6);
"""

# ── Full initialization sequence ────────────────────────────────────

INIT_SEQUENCE = [
    CREATE_TRADES_TABLE,
    CREATE_OHLCV_TABLE,
    CREATE_POLYMARKET_SNAPSHOTS_TABLE,
    CREATE_AUDIT_LOG_TABLE,
    HYPERTABLE_TRADES,
    HYPERTABLE_OHLCV,
    HYPERTABLE_PM_SNAPSHOTS,
    HYPERTABLE_AUDIT_LOG,
    *CREATE_INDEXES,
    RETENTION_TRADES_7D,
    RETENTION_PM_SNAPSHOTS_90D,
    COMPRESSION_OHLCV,
    COMPRESSION_POLICY_OHLCV,
]
