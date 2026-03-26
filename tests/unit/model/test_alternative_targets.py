"""Tests for alternative target formulations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import polars as pl
import pytest

from qm.model.targets.cumulative import CumulativeDirectionTarget
from qm.model.targets.magnitude import MagnitudeTarget
from qm.model.targets.threshold import ThresholdDirectionTarget


def _make_bars(n: int = 200, seed: int = 42) -> pl.DataFrame:
    """Generate synthetic OHLCV data with trending behaviour."""
    rng = np.random.RandomState(seed)
    base = 84000.0
    prices = base + np.cumsum(rng.randn(n) * 50)
    base_time = datetime(2026, 3, 18, 0, 0, 0, tzinfo=UTC)

    return pl.DataFrame({
        "time": [base_time + timedelta(minutes=5 * i) for i in range(n)],
        "open": prices + rng.randn(n) * 10,
        "high": prices + abs(rng.randn(n) * 30) + 10,
        "low": prices - abs(rng.randn(n) * 30) - 10,
        "close": prices + rng.randn(n) * 10,
        "volume": abs(rng.randn(n) * 100) + 50,
    })


# ── Cumulative Direction Target ──────────────────────────────────────


class TestCumulativeDirectionTarget:
    def test_basic_semantics(self):
        """Target should compare close[t+h] to close[t]."""
        bars = pl.DataFrame({
            "close": [100.0, 102.0, 99.0, 105.0, 101.0],
            "open": [99.0, 101.0, 103.0, 98.0, 104.0],
        })
        target = CumulativeDirectionTarget(horizon_bars=2)
        result = target.compute(bars)

        # t=0: close[2]=99 >= close[0]=100? No → 0
        # t=1: close[3]=105 >= close[1]=102? Yes → 1
        # t=2: close[4]=101 >= close[2]=99? Yes → 1
        # t=3, t=4: null (no future data)
        assert result[0] == 0
        assert result[1] == 1
        assert result[2] == 1
        assert result[3] is None
        assert result[4] is None

    def test_last_h_rows_null(self):
        bars = _make_bars(100)
        target = CumulativeDirectionTarget(horizon_bars=5)
        result = target.compute(bars)
        # Last 5 should be null
        assert result[-5:].null_count() == 5
        # First 95 should have values
        assert result[:95].null_count() == 0

    def test_horizon_1_differs_from_binary(self):
        """Cumulative h=1 uses close[t+1] >= close[t], not close[t+1] >= open[t+1]."""
        bars = pl.DataFrame({
            "close": [100.0, 98.0, 102.0],
            "open": [99.0, 97.0, 103.0],
        })
        cum_target = CumulativeDirectionTarget(horizon_bars=1).compute(bars)
        # t=0: close[1]=98 >= close[0]=100? No → 0
        assert cum_target[0] == 0

        from qm.model.targets.binary import BinaryDirectionTarget
        bin_target = BinaryDirectionTarget(horizon_bars=1).compute(bars)
        # t=0: close[1]=98 >= open[1]=97? Yes → 1
        assert bin_target[0] == 1

    def test_invalid_horizon(self):
        with pytest.raises(ValueError, match="horizon_bars must be >= 1"):
            CumulativeDirectionTarget(horizon_bars=0)

    def test_compute_with_meta(self):
        bars = _make_bars(50)
        target = CumulativeDirectionTarget(horizon_bars=3)
        result = target.compute_with_meta(bars)
        assert "target" in result.columns
        assert "target_return" in result.columns


# ── Magnitude Target ─────────────────────────────────────────────────


class TestMagnitudeTarget:
    def test_basic(self):
        bars = _make_bars(200)
        target = MagnitudeTarget(lookback=50)
        result = target.compute(bars)
        # Should have binary values after warmup
        tail = result.slice(60)
        vals = tail.drop_nulls()
        assert len(vals) > 0
        unique = set(vals.to_list())
        assert unique.issubset({0, 1})

    def test_approximately_balanced(self):
        """Target should be roughly 50/50 by definition (above/below median)."""
        bars = _make_bars(1000, seed=123)
        target = MagnitudeTarget(lookback=100)
        result = target.compute(bars)
        vals = result.slice(110).drop_nulls()
        mean = vals.mean()
        # Should be roughly 50% — median splits data in half
        assert 0.35 < mean < 0.65, f"Target mean {mean} is too far from 0.50"

    def test_last_row_null(self):
        bars = _make_bars(100)
        target = MagnitudeTarget(lookback=20)
        result = target.compute(bars)
        assert result[-1] is None

    def test_invalid_lookback(self):
        with pytest.raises(ValueError, match="lookback must be >= 10"):
            MagnitudeTarget(lookback=5)

    def test_compute_with_meta(self):
        bars = _make_bars(200)
        target = MagnitudeTarget(lookback=50)
        result = target.compute_with_meta(bars)
        assert "future_abs_return" in result.columns
        assert "magnitude_threshold" in result.columns


# ── Threshold Direction Target ───────────────────────────────────────


class TestThresholdDirectionTarget:
    def test_drops_small_moves(self):
        bars = _make_bars(1000, seed=42)
        target = ThresholdDirectionTarget(min_percentile=0.30, lookback=200)
        result = target.compute(bars)
        # After warmup, some rows should be null (small moves dropped)
        tail = result.slice(210)
        null_count = tail.null_count()
        total = len(tail)
        # Should drop roughly 30% of samples
        drop_rate = null_count / total
        assert 0.15 < drop_rate < 0.50, f"Drop rate {drop_rate:.2f} unexpected"

    def test_preserves_large_moves(self):
        bars = _make_bars(1000, seed=42)
        target = ThresholdDirectionTarget(min_percentile=0.30, lookback=200)
        result = target.compute(bars)
        # Non-null values should be 0 or 1
        vals = result.drop_nulls()
        unique = set(vals.to_list())
        assert unique.issubset({0, 1})

    def test_direction_correct(self):
        """Up moves should be 1, down moves should be 0."""
        # Create bars with known large moves
        bars = pl.DataFrame({
            "open": [100.0] * 10,
            "close": [100.0, 110.0, 90.0, 115.0, 85.0,
                      100.0, 120.0, 80.0, 105.0, 95.0],
            "high": [120.0] * 10,
            "low": [80.0] * 10,
            "volume": [100.0] * 10,
        })
        target = ThresholdDirectionTarget(min_percentile=0.10, lookback=10)
        result = target.compute(bars)
        # Check non-null values match expected direction
        for i in range(len(result) - 1):
            val = result[i]
            if val is not None:
                future_ret = (bars["close"][i + 1] - bars["open"][i + 1]) / bars["open"][i + 1]
                if val == 1:
                    assert future_ret > 0, f"Row {i}: target=1 but return={future_ret}"
                else:
                    assert future_ret < 0, f"Row {i}: target=0 but return={future_ret}"

    def test_invalid_percentile(self):
        with pytest.raises(ValueError, match="min_percentile must be in"):
            ThresholdDirectionTarget(min_percentile=0.0)
        with pytest.raises(ValueError, match="min_percentile must be in"):
            ThresholdDirectionTarget(min_percentile=1.0)

    def test_compute_with_meta(self):
        bars = _make_bars(200)
        target = ThresholdDirectionTarget(min_percentile=0.30, lookback=100)
        result = target.compute_with_meta(bars)
        assert "target_return" in result.columns
