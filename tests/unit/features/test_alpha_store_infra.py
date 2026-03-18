"""Tests for alpha store infrastructure: join_alpha_asof + CrossAssetPipeline alpha_stores."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import numpy as np
import polars as pl

from qm.core.types import Asset, Timeframe
from qm.features.cross_asset import (
    CrossAssetPipeline,
    join_alpha_asof,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bars(n: int = 100, interval_min: int = 5, seed: int = 42) -> pl.DataFrame:
    """Create a synthetic OHLCV DataFrame sorted by time."""
    rng = np.random.RandomState(seed)
    base = datetime(2026, 1, 1, tzinfo=UTC)
    times = [base + timedelta(minutes=interval_min * i) for i in range(n)]
    close = 100.0 + np.cumsum(rng.randn(n) * 0.5)
    return pl.DataFrame({
        "time": times,
        "open": close + rng.randn(n) * 0.1,
        "high": close + abs(rng.randn(n) * 0.3),
        "low": close - abs(rng.randn(n) * 0.3),
        "close": close,
        "volume": rng.uniform(100, 1000, n),
        "trade_count": rng.randint(10, 100, n).astype(np.int64),
        "vwap": close + rng.randn(n) * 0.05,
    })


def _make_alpha_8h(n_days: int = 4, seed: int = 99) -> pl.DataFrame:
    """Simulate funding-rate-like alpha at 8 h intervals."""
    rng = np.random.RandomState(seed)
    base = datetime(2026, 1, 1, tzinfo=UTC)
    times = [base + timedelta(hours=8 * i) for i in range(n_days * 3)]
    return pl.DataFrame({
        "time": times,
        "rate": rng.uniform(-0.001, 0.001, len(times)),
        "predicted": rng.uniform(-0.002, 0.002, len(times)),
    })


# ---------------------------------------------------------------------------
# Tests for join_alpha_asof
# ---------------------------------------------------------------------------

class TestJoinAlphaAsof:
    def test_columns_prefixed(self):
        """Alpha columns should be renamed with the supplied prefix."""
        bars = _make_bars(50)
        alpha = _make_alpha_8h(2)

        result = join_alpha_asof(bars, alpha, prefix="funding")

        assert "funding_rate" in result.columns
        assert "funding_predicted" in result.columns
        # Original "rate" should not leak through
        assert "rate" not in result.columns

    def test_row_count_preserved(self):
        """All bar rows must be preserved (left-side semantics)."""
        bars = _make_bars(100)
        alpha = _make_alpha_8h(4)

        result = join_alpha_asof(bars, alpha, prefix="funding")

        assert len(result) == len(bars)

    def test_backward_no_lookahead(self):
        """Each bar should get the alpha row at-or-before its timestamp."""
        bars = _make_bars(50, interval_min=5)
        alpha = _make_alpha_8h(2)

        result = join_alpha_asof(bars, alpha, prefix="funding")

        for i in range(len(result)):
            bar_time = result["time"][i]
            alpha_val = result["funding_rate"][i]
            if alpha_val is not None:
                # Find the matched alpha row — it must be <= bar_time
                matched = alpha.filter(pl.col("rate") == alpha_val)
                if not matched.is_empty():
                    assert matched["time"][0] <= bar_time

    def test_tolerance_creates_nulls(self):
        """Bars far from any alpha row should get nulls when tolerance is set."""
        base = datetime(2026, 1, 1, tzinfo=UTC)
        # Bars every 5 min for 1 hour
        bars = _make_bars(12, interval_min=5)
        # Single alpha row at t=0
        alpha = pl.DataFrame({
            "time": [base],
            "rate": [0.001],
        })

        result = join_alpha_asof(bars, alpha, prefix="funding", tolerance="15m")

        # First 4 bars (t=0, 5, 10, 15 min) should have a value
        for i in range(4):
            assert result["funding_rate"][i] is not None, f"Row {i} should not be null"

        # Later bars should be null (> 15 min from the single alpha row)
        for i in range(4, 12):
            assert result["funding_rate"][i] is None, f"Row {i} should be null"

    def test_empty_alpha_noop(self):
        """Empty alpha DataFrame should return bars unchanged."""
        bars = _make_bars(20)
        empty_alpha = pl.DataFrame(
            {"time": [], "rate": []}
        ).cast({"time": pl.Datetime("us", "UTC"), "rate": pl.Float64})

        result = join_alpha_asof(bars, empty_alpha, prefix="funding")

        assert result.columns == bars.columns
        assert len(result) == 20

    def test_alpha_without_time_noop(self):
        """Alpha DataFrame missing 'time' column should return bars unchanged."""
        bars = _make_bars(20)
        bad_alpha = pl.DataFrame({"ts": [datetime(2026, 1, 1, tzinfo=UTC)], "rate": [0.001]})

        result = join_alpha_asof(bars, bad_alpha, prefix="funding")

        assert "funding_rate" not in result.columns
        assert len(result) == 20

    def test_unsorted_inputs(self):
        """join_alpha_asof should handle unsorted inputs gracefully."""
        bars = _make_bars(30).sort("time", descending=True)  # reversed
        alpha = _make_alpha_8h(2).sort("time", descending=True)

        result = join_alpha_asof(bars, alpha, prefix="funding")

        assert len(result) == 30
        assert "funding_rate" in result.columns
        # Result should be sorted by time (ascending)
        times = result["time"].to_list()
        assert times == sorted(times)


# ---------------------------------------------------------------------------
# Tests for CrossAssetPipeline with alpha_stores
# ---------------------------------------------------------------------------

class TestCrossAssetPipelineAlphaStores:
    def _make_mock_store(self) -> MagicMock:
        """Create a mock ParquetStore that returns synthetic OHLCV data."""
        base = datetime(2026, 1, 1, tzinfo=UTC)
        store = MagicMock()

        def read_bars(asset, timeframe, **kwargs):
            seed = {Asset.BTC: 1, Asset.ETH: 2, Asset.SOL: 3, Asset.XRP: 4}.get(asset, 0)
            n = 200
            rng = np.random.RandomState(seed)
            times = [base + timedelta(minutes=5 * i) for i in range(n)]
            close = 100.0 + np.cumsum(rng.randn(n) * 0.5)
            return pl.DataFrame({
                "time": times,
                "open": close + rng.randn(n) * 0.1,
                "high": close + abs(rng.randn(n) * 0.3),
                "low": close - abs(rng.randn(n) * 0.3),
                "close": close,
                "volume": rng.uniform(100, 1000, n),
                "trade_count": rng.randint(10, 100, n).astype(np.int64),
                "vwap": close + rng.randn(n) * 0.05,
            })

        store.read_bars = read_bars
        return store

    def _make_mock_alpha_store(self, col_name: str = "rate", seed: int = 99) -> MagicMock:
        """Mock alpha store whose read_metrics returns 8h-cadence data."""
        alpha_store = MagicMock()

        def _read_metrics(asset, **kwargs):
            base = datetime(2026, 1, 1, tzinfo=UTC)
            rng = np.random.RandomState(seed)
            n = 75  # ~25 days of 8h data, covers 200 * 5min = ~16.7h
            times = [base + timedelta(hours=8 * i) for i in range(n)]
            return pl.DataFrame({
                "time": times,
                col_name: rng.uniform(-0.001, 0.001, n),
            })

        alpha_store.read_metrics = MagicMock(side_effect=_read_metrics)
        return alpha_store

    def test_alpha_columns_present_in_output(self):
        """Alpha store columns should appear (prefixed) in compute() output."""
        store = self._make_mock_store()
        alpha = self._make_mock_alpha_store("rate")
        cross = CrossAssetPipeline(
            store, Timeframe.M5,
            alpha_stores={"funding": alpha},
        )

        result = cross.compute(Asset.ETH)

        assert "funding_rate" in result.columns
        assert len(result) > 0

    def test_multiple_alpha_stores(self):
        """Multiple alpha stores should all contribute columns."""
        store = self._make_mock_store()
        funding = self._make_mock_alpha_store("rate", seed=1)
        liquidation = self._make_mock_alpha_store("liq_volume", seed=2)
        cross = CrossAssetPipeline(
            store, Timeframe.M5,
            alpha_stores={"funding": funding, "liquidation": liquidation},
        )

        result = cross.compute(Asset.ETH)

        assert "funding_rate" in result.columns
        assert "liquidation_liq_volume" in result.columns

    def test_alpha_tolerance_passed_through(self):
        """Alpha tolerance should limit the join window."""
        store = self._make_mock_store()
        alpha = self._make_mock_alpha_store("rate")
        cross = CrossAssetPipeline(
            store, Timeframe.M5,
            alpha_stores={"funding": alpha},
            alpha_tolerances={"funding": "9h"},
        )

        result = cross.compute(Asset.ETH)

        # With 9h tolerance and 8h-cadence alpha, most bars should have data
        assert "funding_rate" in result.columns
        # Some rows may be null if bars fall outside 9h window of any alpha row
        non_null = result["funding_rate"].drop_nulls()
        assert len(non_null) > 0

    def test_empty_alpha_store_graceful(self):
        """Empty alpha store should not add columns or crash."""
        store = self._make_mock_store()
        empty_store = MagicMock()
        empty_store.read_metrics = MagicMock(return_value=pl.DataFrame())

        cross = CrossAssetPipeline(
            store, Timeframe.M5,
            alpha_stores={"empty": empty_store},
        )

        result = cross.compute(Asset.ETH)

        # Should still work, just no empty_* columns
        assert len(result) > 0
        assert not any(c.startswith("empty_") for c in result.columns)

    def test_failing_alpha_store_graceful(self):
        """Alpha store that raises an exception should be skipped gracefully."""
        store = self._make_mock_store()
        bad_store = MagicMock()
        bad_store.read_metrics = MagicMock(side_effect=RuntimeError("connection failed"))

        cross = CrossAssetPipeline(
            store, Timeframe.M5,
            alpha_stores={"broken": bad_store},
        )

        # Should not raise
        result = cross.compute(Asset.ETH)

        assert len(result) > 0
        assert not any(c.startswith("broken_") for c in result.columns)

    def test_no_alpha_stores_backward_compatible(self):
        """Pipeline without alpha_stores should behave exactly as before."""
        store = self._make_mock_store()
        cross_old = CrossAssetPipeline(store, Timeframe.M5)
        cross_new = CrossAssetPipeline(store, Timeframe.M5, alpha_stores={})

        result_old = cross_old.compute(Asset.ETH)
        result_new = cross_new.compute(Asset.ETH)

        assert result_old.columns == result_new.columns
        assert len(result_old) == len(result_new)

    def test_caching_with_alpha_stores(self):
        """Alpha data should be joined and cached, not re-read on second call."""
        store = self._make_mock_store()
        alpha = self._make_mock_alpha_store("rate")
        cross = CrossAssetPipeline(
            store, Timeframe.M5,
            alpha_stores={"funding": alpha},
        )

        cross.compute(Asset.ETH)
        cross.compute(Asset.SOL)

        # BTC is context for both ETH and SOL — its alpha read should be cached
        assert Asset.BTC in cross._featured_cache
        # read_metrics called once per unique asset accessed (ETH, BTC, SOL)
        assert alpha.read_metrics.call_count == 3
