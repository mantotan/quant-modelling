# Pulse Model (Intra-Bar Prediction) — Implementation Plan

## Model Naming Convention

| Name | Code Name | What It Does | When It Runs |
|------|-----------|-------------|-------------|
| **Sentinel** | `sentinel` | Bar-level: predicts NEXT bar direction from completed bars | Once per bar completion |
| **Pulse** | `pulse` | Intra-bar: predicts CURRENT bar outcome from live tick data | Every ~0.5s during window |

- Existing model → **Sentinel** (rename scripts, model dirs)
- New model → **Pulse** (this plan)
- Scripts: `train_sentinel.py`, `train_pulse.py`
- Model dirs: `data/models/sentinel/BTC_5m/`, `data/models/pulse/BTC_5m/`

## Context

Sentinel predicts "will the NEXT bar go up?" after each bar completes. But Polymarket 5m markets have live-moving orderbooks **during** each window. The real trading opportunity is intra-bar: at any moment within a window, predict P(close >= open) and compare to live Polymarket odds.

```
Trade arrives (Binance WSS)
    |
    |---> BarBuilder.on_trade()
    |       |
    |       |---> [bar completed] -> SENTINEL (existing, unchanged)
    |       |     -> "next bar direction" signal (context/regime)
    |       |
    |       |---> [throttled, ~2/sec] -> get_partial_bar() -> PULSE (NEW)
    |             -> "THIS bar P(close >= open) = 0.78"
    |             -> Compare to Polymarket live odds -> Trade if edge
    |
    |---> Combine Sentinel + Pulse -> Risk filter -> Execute
```

---

## Implementation Steps (8 steps, ~1,400 lines)

### Step A: Add PartialBar type
**File:** `src/qm/core/types.py` (+20 lines)

```python
@dataclass(slots=True)
class PartialBar:
    """Snapshot of an in-progress bar, updated on every tick."""
    window_start: datetime
    window_end: datetime
    asset: Asset
    timeframe: Timeframe
    open: float
    high_so_far: float
    low_so_far: float
    current_price: float     # latest trade price (NOT final close)
    volume_so_far: float
    trade_count: int
    elapsed_seconds: float   # seconds since window_start
    remaining_seconds: float # seconds until window_end
```

**[REVISED]** `PartialBar` should be `frozen=True` like `Bar` — it's a snapshot, not a live-updating object. Elapsed/remaining are computed at snapshot time and don't change after creation.

Also add to `src/qm/core/events.py`:
```python
@dataclass(frozen=True, slots=True)
class PartialBarUpdated:
    partial_bar: PartialBar
```

### Step B: Expose partial bar state from BarBuilder
**File:** `src/qm/data/ingestion/bar_builder.py` (+30 lines)

```python
def get_partial_bar(self, asset: Asset, timeframe: Timeframe,
                    now: datetime | None = None) -> PartialBar | None:
    """Non-blocking snapshot of the in-progress bar accumulator.

    Args:
        now: Explicit timestamp (for backtesting). Defaults to wall clock.
    """
    acc = self._state[asset].accumulators.get(timeframe)
    if acc is None or not acc.is_initialized:
        return None
    ts = now or datetime.now(timezone.utc)
    return PartialBar(
        window_start=acc.window_start, window_end=acc.window_end,
        asset=asset, timeframe=timeframe,
        open=acc.open, high_so_far=acc.high, low_so_far=acc.low,
        current_price=acc.close, volume_so_far=acc.volume,
        trade_count=acc.trade_count,
        elapsed_seconds=(ts - acc.window_start).total_seconds(),
        remaining_seconds=(acc.window_end - ts).total_seconds(),
    )
```

**[ADDED]** `now` parameter makes this testable and backtest-compatible (no `datetime.now()` dependency).

### Step C: Intra-bar feature calculator (NEW)
**File:** `src/qm/features/intrabar.py` (~130 lines)

```python
class IntraBarFeatureCalculator:
    """< 0.1ms per tick. Pure arithmetic on PartialBar + cached history."""

    def __init__(self):
        self._history_cache: dict[Asset, dict[str, float]] = {}

    def update_cache(self, asset: Asset, features: dict[str, float]):
        """Called once when a bar completes. Caches historical context."""
        self._history_cache[asset] = features

    def compute(self, partial: PartialBar) -> np.ndarray:
        cache = self._history_cache.get(partial.asset, {})
        range_size = partial.high_so_far - partial.low_so_far
        recent_vol = cache.get("realized_vol_10", 0.01)

        return np.array([
            # Tick-level (from PartialBar)
            (partial.current_price - partial.open) / (partial.open + 1e-10),          # distance_from_open
            (partial.current_price - partial.open) / (partial.open * recent_vol + 1e-10),  # [ADDED] vol-normalized distance
            partial.elapsed_seconds / 300.0,                                            # time_pct
            1.0 - partial.elapsed_seconds / 300.0,                                      # [ADDED] time_remaining_pct
            range_size / (partial.open + 1e-10),                                        # partial_range
            (partial.current_price - partial.low_so_far) / (range_size + 1e-10),        # partial_bar_position
            partial.volume_so_far / (cache.get("avg_volume_10", partial.volume_so_far) + 1e-10),  # volume_ratio_so_far [REVISED: normalized]
            partial.trade_count / max(partial.elapsed_seconds, 0.1),                     # trade_intensity

            # Cached historical (from last completed bar)
            cache.get("rsi_14", 50.0),
            cache.get("realized_vol_10", 0.01),
            cache.get("hour_sin", 0.0),
            cache.get("hour_cos", 1.0),
        ], dtype=np.float64)

    @property
    def feature_names(self) -> list[str]:
        return [
            "distance_from_open", "vol_norm_distance", "time_pct",
            "time_remaining_pct", "partial_range", "partial_bar_position",
            "volume_so_far", "trade_intensity",
            "rsi_14", "realized_vol_10", "hour_sin", "hour_cos",
        ]
```

**[ADDED]** `vol_norm_distance`: distance_from_open / realized_vol — normalizes by current volatility regime. A +0.5% move means different things on calm vs volatile days.

**[ADDED]** `time_remaining_pct`: explicit complement of time_pct, since the model cares about "how much time is left to reverse."

### Step D: Training data generator (NEW, REVISED)
**File:** `src/qm/model/targets/intrabar.py` (~180 lines)

**[REVISED]** Interpolation improved from naive linear to **OHLC-aware path simulation:**

```python
class IntraBarTrainingDataGenerator:
    """Generate intra-bar training samples from 5m OHLCV bars.

    For each bar, simulates partial bar states at 10%...90% elapsed.
    Uses OHLC-aware path simulation, NOT naive linear interpolation.

    Path model (per bar):
    1. Price starts at open
    2. Moves toward high or low (whichever was likely hit first)
    3. Then reverses to the other extreme
    4. Then settles toward close

    This is a simplification but much better than linear open->close.
    """

    def generate(
        self, bars_df: pl.DataFrame, history_features: pl.DataFrame,
        time_pcts: list[float] = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9],
    ) -> tuple[np.ndarray, np.ndarray]:
        """Returns (X, y).

        IMPORTANT: Samples from the same bar share a target. Callers must
        split at the BAR level, not the sample level, to avoid leakage.
        """
```

**[ADDED]** Docstring warning about bar-level splitting requirement.

**[ADDED]** OHLC-aware path model:
- For an up-bar (close > open): path goes open → low → high → close
- For a down-bar (close < open): path goes open → high → low → close
- At each simulated time_pct, interpolate along this path
- high_so_far and low_so_far are updated progressively

This still won't match real tick paths perfectly, but it's much better than linear interpolation.

### Step E: Intra-bar model trainer (NEW)
**File:** `src/qm/model/trainers/pulse_trainer.py` (~200 lines)

Same LightGBM + Optuna structure as Sentinel trainer.

**[ADDED]** Critical: walk-forward splits at the **bar level**, then expands each bar to 9 samples:
```python
# WRONG: split on sample level (correlated samples in train+test)
# train_idx, test_idx = splitter.split(n_samples)

# RIGHT: split on bar level, then expand
bar_train_idx, bar_test_idx = splitter.split(n_bars)
sample_train_idx = expand_bar_to_samples(bar_train_idx, samples_per_bar=9)
sample_test_idx = expand_bar_to_samples(bar_test_idx, samples_per_bar=9)
```

### Step F: Intra-bar backtest (NEW)
**File:** `src/qm/backtest/intrabar_backtest.py` (~200 lines)

```python
class IntraBarBacktester:
    def run(self, bars, model, calibrator,
            market_efficiency=0.3,    # how informed the market is
            min_elapsed_pct=0.1,      # [ADDED] don't trade in first 30 sec
            max_elapsed_pct=0.95,     # don't trade in last 15 sec
            max_trades_per_bar=3,     # [ADDED] limit overtrading
    ):
```

**[ADDED]** `min_elapsed_pct`: skip predictions in the first 10% of the bar (30 seconds) — too little information.

**[ADDED]** `max_trades_per_bar`: prevent overtrading on the same bar (correlated decisions).

### Step G: Trading loop with throttling
**File:** `src/qm/execution/loop.py` (+60 lines)

```python
async def on_trade_pulse(self, asset: Asset, price: float, size: float, ts: datetime):
    """Called on every tick. Throttled to ~2 predictions/sec per asset."""
    # [ADDED] Throttle: skip if last prediction was < 500ms ago
    last = self._last_pulse_time.get(asset, 0)
    now_mono = time.monotonic()
    if now_mono - last < 0.5:
        return
    self._last_pulse_time[asset] = now_mono

    partial = self._bar_builder.get_partial_bar(asset, Timeframe.M5, now=ts)
    if partial is None:
        return

    # [ADDED] Skip first 30s and last 5s of window
    if partial.elapsed_seconds < 30 or partial.remaining_seconds < 5:
        return

    features = self._pulse_features.compute(partial)
    p_up = self._pulse_calibrator.transform(
        self._pulse_model.predict(features.reshape(1, -1))
    )[0]

    market_up = self._get_polymarket_up_price(asset)
    if market_up is None:
        return

    edge = p_up - market_up
    if abs(edge) > self._min_edge:
        # Signal generation, sizing, risk check, execute
        ...
```

**[ADDED]** Throttle: max 2 predictions per second per asset (500ms cooldown).
**[ADDED]** Skip first 30 seconds (too little info) and last 5 seconds (too late to trade).

### Step H: Scripts + rename
**Files:**
- `scripts/train_pulse.py` — NEW, end-to-end Pulse training pipeline (~200 lines)
- Rename existing: `train_and_backtest.py` → `train_sentinel.py`
- Rename: `train_v3_correct_target.py` → `train_sentinel_v3.py`
- Rename: `realistic_backtest.py` → `backtest_sentinel.py`

---

## Verification Plan

### Tests:
1. `tests/unit/data/test_partial_bar.py` — BarBuilder.get_partial_bar() with explicit `now` parameter
2. `tests/unit/features/test_intrabar.py` — feature values at t=0%, 50%, 99% of bar
3. `tests/unit/model/test_intrabar_target.py` — correct sample count, OHLC path interpolation, bar-level split integrity
4. `tests/unit/backtest/test_intrabar_backtest.py` — perfect model profits, random model ~0
5. `tests/unit/execution/test_pulse_throttle.py` — [ADDED] verify 500ms throttle works

### [ADDED] Prometheus metrics for Pulse:
Add to `src/qm/monitoring/metrics.py`:
```python
PULSE_PREDICTIONS = Counter("qm_pulse_predictions_total", "Pulse tick predictions", ["asset"])
PULSE_LATENCY_NS = Histogram("qm_pulse_latency_ns", "Pulse prediction latency", ...)
PULSE_EDGE = Histogram("qm_pulse_edge", "Pulse edge distribution", ...)
PULSE_TRADES = Counter("qm_pulse_trades_total", "Pulse trades executed", ["asset", "side"])
```

### Latency:
- `IntraBarFeatureCalculator.compute()`: target < 0.1ms
- LightGBM predict: target < 5ms
- Total `on_trade_pulse()`: target < 10ms
- Throttled to 2/sec → 5ms budget is plenty

### Accuracy expectations:
| Time into bar | Expected Pulse accuracy | Why |
|---------------|----------------------|-----|
| 0-30 sec | ~50% (skip, not enough info) | Random — no distance from open yet |
| 30-90 sec | 50-52% | Small signal from momentum |
| 90-180 sec | 52-58% | Growing signal as price moves |
| 180-270 sec | 58-70% | Strong signal, direction mostly established |
| 270-295 sec | 70-85% | Price has nearly settled |
| 295-300 sec | Skip (too late to trade) | — |

The tradeable window is **30-180 seconds** into the bar, where the model has meaningful edge but the Polymarket market may not have fully priced it in.
