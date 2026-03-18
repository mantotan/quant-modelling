"""Tests for target construction."""

from datetime import datetime, timedelta, timezone

import polars as pl
import pytest

from qm.model.targets.binary import BinaryDirectionTarget, ThresholdTouchTarget


def _make_bars(n: int = 20) -> pl.DataFrame:
    base = datetime(2026, 3, 18, 12, 0, 0, tzinfo=timezone.utc)
    # Price goes up then down: 100, 101, 102, ..., 109, 108, 107, ...
    prices = list(range(100, 100 + n // 2)) + list(range(100 + n // 2 - 1, 100 - 1, -1))
    prices = prices[:n]
    return pl.DataFrame({
        "time": [base + timedelta(minutes=5 * i) for i in range(n)],
        "open": [float(p) for p in prices],
        "high": [float(p + 2) for p in prices],
        "low": [float(p - 1) for p in prices],
        "close": [float(p + 1) for p in prices],
        "volume": [100.0] * n,
    })


class TestBinaryTarget:
    def test_basic_computation(self):
        bars = _make_bars(10)
        target = BinaryDirectionTarget(horizon_bars=1)
        y = target.compute(bars)
        assert len(y) == 10
        assert y.dtype == pl.Int8

    def test_last_rows_are_null(self):
        bars = _make_bars(10)
        target = BinaryDirectionTarget(horizon_bars=2)
        y = target.compute(bars)
        assert y[-1] is None
        assert y[-2] is None

    def test_up_market_mostly_ones(self):
        """In a steadily rising market, most targets should be 1."""
        n = 20
        base = datetime(2026, 3, 18, 12, 0, 0, tzinfo=timezone.utc)
        bars = pl.DataFrame({
            "time": [base + timedelta(minutes=5 * i) for i in range(n)],
            "open": [100.0 + i * 10 for i in range(n)],
            "high": [110.0 + i * 10 for i in range(n)],
            "low": [95.0 + i * 10 for i in range(n)],
            "close": [105.0 + i * 10 for i in range(n)],
            "volume": [100.0] * n,
        })
        target = BinaryDirectionTarget(horizon_bars=1)
        y = target.compute(bars)
        valid = y.drop_nulls()
        # In a rising market, close[t+1] > open[t] should be True mostly
        assert valid.sum() > len(valid) * 0.5

    def test_horizon_matches_polymarket(self):
        """horizon=1 on 5m bars = 5 minute prediction window."""
        target = BinaryDirectionTarget(horizon_bars=1)
        assert target.horizon_bars == 1


class TestThresholdTarget:
    def test_threshold_reached(self):
        bars = _make_bars(20)
        target = ThresholdTouchTarget(threshold=105.0, window_bars=10)
        y = target.compute(bars)
        # Bars go up to 109+2=111 high, so threshold 105 should be reached
        valid = y.drop_nulls()
        assert valid.sum() > 0

    def test_threshold_not_reached(self):
        bars = _make_bars(20)
        target = ThresholdTouchTarget(threshold=999.0, window_bars=10)
        y = target.compute(bars)
        valid = y.drop_nulls()
        assert valid.sum() == 0
