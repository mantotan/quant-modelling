"""Tests for FundingFeatures group (6 features from perpetual funding rates)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import polars as pl
import pytest

from qm.features.groups.funding import FundingFeatures

# Column name after join_alpha_asof(prefix="funding")
_SRC_COL = "funding_funding_rate"

ALL_FUNDING_FEATURES = [
    "funding_rate",
    "funding_rate_sma3",
    "funding_rate_pctile",
    "funding_rate_direction",
    "funding_cumulative_24h",
    "funding_hours_since",
]


def _make_bars_with_funding(n: int = 100) -> pl.DataFrame:
    """Create OHLCV bars with funding_funding_rate column.

    Simulates join_asof output: funding rate is constant for ~96 bars
    (8h at 5m cadence) then jumps to a new value.
    """
    rng = np.random.RandomState(42)
    base = datetime(2026, 1, 1, tzinfo=UTC)
    times = [base + timedelta(minutes=5 * i) for i in range(n)]

    # Funding rate changes every 96 bars (8h / 5m) — simulate forward-fill
    rates = []
    current_rate = 0.0001
    for i in range(n):
        if i > 0 and i % 96 == 0:
            current_rate = rng.uniform(-0.001, 0.001)
        rates.append(current_rate)

    return pl.DataFrame({
        "time": times,
        "open": rng.uniform(90, 110, n),
        "high": rng.uniform(100, 120, n),
        "low": rng.uniform(80, 100, n),
        "close": rng.uniform(90, 110, n),
        "volume": rng.uniform(100, 1000, n),
        _SRC_COL: rates,
    })


def _make_plain_bars(n: int = 50) -> pl.DataFrame:
    """Create OHLCV bars WITHOUT funding columns."""
    rng = np.random.RandomState(42)
    base = datetime(2026, 1, 1, tzinfo=UTC)
    times = [base + timedelta(minutes=5 * i) for i in range(n)]

    return pl.DataFrame({
        "time": times,
        "open": rng.uniform(90, 110, n),
        "high": rng.uniform(100, 120, n),
        "low": rng.uniform(80, 100, n),
        "close": rng.uniform(90, 110, n),
        "volume": rng.uniform(100, 1000, n),
    })


class TestFundingFeatures:
    """Test suite for FundingFeatures group."""

    def test_graceful_noop_without_funding_column(self) -> None:
        """Should return bars unchanged when funding column is absent."""
        calc = FundingFeatures()
        df = _make_plain_bars()
        result = calc.compute(df)

        # No funding features should be added
        for feat in ALL_FUNDING_FEATURES:
            assert feat not in result.columns, f"Unexpected feature: {feat}"

        # Original columns preserved
        assert "close" in result.columns
        assert len(result) == len(df)

    def test_all_features_present(self) -> None:
        """All 6 funding features should be produced when source column exists."""
        calc = FundingFeatures()
        df = _make_bars_with_funding()
        result = calc.compute(df)

        for feat in ALL_FUNDING_FEATURES:
            assert feat in result.columns, f"Missing feature: {feat}"

    def test_funding_rate_passthrough(self) -> None:
        """funding_rate should equal the raw source column."""
        calc = FundingFeatures()
        df = _make_bars_with_funding()
        result = calc.compute(df)

        for i in range(len(result)):
            assert result["funding_rate"][i] == pytest.approx(
                result[_SRC_COL][i], abs=1e-12
            )

    def test_sma3_smoothing(self) -> None:
        """funding_rate_sma3 should be a rolling 3-period mean."""
        calc = FundingFeatures()
        # Use a short series with known values
        df = pl.DataFrame({
            "time": [
                datetime(2026, 1, 1, h, tzinfo=UTC) for h in range(5)
            ],
            "open": [100.0] * 5,
            "high": [101.0] * 5,
            "low": [99.0] * 5,
            "close": [100.0] * 5,
            "volume": [100.0] * 5,
            _SRC_COL: [0.0001, 0.0002, 0.0003, 0.0004, 0.0005],
        })
        result = calc.compute(df)

        # At index 2: mean of [0.0001, 0.0002, 0.0003] = 0.0002
        assert result["funding_rate_sma3"][2] == pytest.approx(0.0002, abs=1e-10)
        # At index 4: mean of [0.0003, 0.0004, 0.0005] = 0.0004
        assert result["funding_rate_sma3"][4] == pytest.approx(0.0004, abs=1e-10)

    def test_pctile_range(self) -> None:
        """funding_rate_pctile should be in [0, 1]."""
        calc = FundingFeatures()
        df = _make_bars_with_funding(200)
        result = calc.compute(df)

        pctile = result["funding_rate_pctile"].drop_nulls()
        assert pctile.min() >= -0.01  # small floating-point tolerance
        assert pctile.max() <= 1.01

    def test_direction_values(self) -> None:
        """funding_rate_direction should be +1, 0, or -1."""
        calc = FundingFeatures()
        df = pl.DataFrame({
            "time": [
                datetime(2026, 1, 1, h, tzinfo=UTC) for h in range(4)
            ],
            "open": [100.0] * 4,
            "high": [101.0] * 4,
            "low": [99.0] * 4,
            "close": [100.0] * 4,
            "volume": [100.0] * 4,
            _SRC_COL: [0.0001, -0.0002, 0.0, 0.0005],
        })
        result = calc.compute(df)

        directions = result["funding_rate_direction"].to_list()
        assert directions[0] == 1    # positive
        assert directions[1] == -1   # negative
        assert directions[2] == 0    # zero
        assert directions[3] == 1    # positive

    def test_cumulative_24h(self) -> None:
        """funding_cumulative_24h should be rolling sum of last 3 values."""
        calc = FundingFeatures()
        df = pl.DataFrame({
            "time": [
                datetime(2026, 1, 1, h, tzinfo=UTC) for h in range(5)
            ],
            "open": [100.0] * 5,
            "high": [101.0] * 5,
            "low": [99.0] * 5,
            "close": [100.0] * 5,
            "volume": [100.0] * 5,
            _SRC_COL: [0.0001, 0.0002, 0.0003, 0.0004, 0.0005],
        })
        result = calc.compute(df)

        # At index 2: sum of [0.0001, 0.0002, 0.0003] = 0.0006
        assert result["funding_cumulative_24h"][2] == pytest.approx(0.0006, abs=1e-10)
        # At index 4: sum of [0.0003, 0.0004, 0.0005] = 0.0012
        assert result["funding_cumulative_24h"][4] == pytest.approx(0.0012, abs=1e-10)

    def test_hours_since_update(self) -> None:
        """funding_hours_since should track time since last rate change."""
        calc = FundingFeatures()
        base = datetime(2026, 1, 1, tzinfo=UTC)
        # Rate changes at index 3 (from 0.0001 to 0.0002)
        df = pl.DataFrame({
            "time": [base + timedelta(hours=i) for i in range(6)],
            "open": [100.0] * 6,
            "high": [101.0] * 6,
            "low": [99.0] * 6,
            "close": [100.0] * 6,
            "volume": [100.0] * 6,
            _SRC_COL: [0.0001, 0.0001, 0.0001, 0.0002, 0.0002, 0.0002],
        })
        result = calc.compute(df)

        hours_since = result["funding_hours_since"]
        # Index 0: first row, rate "changes" from null → value = 0h
        assert hours_since[0] == pytest.approx(0.0, abs=0.01)
        # Index 2: 2 hours since first update (index 0)
        assert hours_since[2] == pytest.approx(2.0, abs=0.01)
        # Index 3: rate changed, 0 hours since update
        assert hours_since[3] == pytest.approx(0.0, abs=0.01)
        # Index 5: 2 hours since last update (index 3)
        assert hours_since[5] == pytest.approx(2.0, abs=0.01)

    def test_null_funding_rates(self) -> None:
        """Nulls in funding rate should not crash computation."""
        calc = FundingFeatures()
        df = _make_bars_with_funding(50)
        # Inject nulls (simulating join_asof gaps)
        mask = pl.Series([True] * 25 + [False] * 25)
        df = df.with_columns(
            pl.when(mask).then(pl.col(_SRC_COL)).otherwise(None)
            .alias(_SRC_COL),
        )
        result = calc.compute(df)

        # Should not crash, all features present
        for feat in ALL_FUNDING_FEATURES:
            assert feat in result.columns
        assert len(result) == 50  # no rows dropped

    def test_single_row(self) -> None:
        """Should handle single-row DataFrames without crashing."""
        calc = FundingFeatures()
        df = pl.DataFrame({
            "time": [datetime(2026, 1, 1, tzinfo=UTC)],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.0],
            "volume": [100.0],
            _SRC_COL: [0.0001],
        })
        result = calc.compute(df)

        assert len(result) == 1
        assert result["funding_rate"][0] == pytest.approx(0.0001, abs=1e-10)

    def test_specs_count(self) -> None:
        """Should register exactly 6 feature specs."""
        calc = FundingFeatures()
        specs = calc.specs()
        assert len(specs) == 6
        spec_names = {s.name for s in specs}
        assert spec_names == set(ALL_FUNDING_FEATURES)

    def test_empty_dataframe(self) -> None:
        """Should handle empty DataFrame gracefully."""
        calc = FundingFeatures()
        df = pl.DataFrame({
            "time": pl.Series([], dtype=pl.Datetime("us", "UTC")),
            "open": pl.Series([], dtype=pl.Float64),
            "high": pl.Series([], dtype=pl.Float64),
            "low": pl.Series([], dtype=pl.Float64),
            "close": pl.Series([], dtype=pl.Float64),
            "volume": pl.Series([], dtype=pl.Float64),
            _SRC_COL: pl.Series([], dtype=pl.Float64),
        })
        result = calc.compute(df)
        assert result.is_empty()
