"""Tests for DeribitIVDownloader._parse_records."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from qm.data.historical.deribit_iv import DeribitIVDownloader


class TestParseRecords:
    """Test the static _parse_records method."""

    def test_basic_parsing(self) -> None:
        records = [
            [1609459200000, 65.5],  # 2021-01-01 00:00 UTC, 65.5%
            [1609545600000, 70.2],  # 2021-01-02 00:00 UTC, 70.2%
        ]
        df = DeribitIVDownloader._parse_records(
            records, date(2021, 1, 1), date(2021, 12, 31),
        )
        assert len(df) == 2
        assert "time" in df.columns
        assert "iv_index" in df.columns
        # Values should be decimals, not percentages
        assert df["iv_index"][0] == pytest.approx(0.655, abs=0.001)
        assert df["iv_index"][1] == pytest.approx(0.702, abs=0.001)

    def test_date_filtering(self) -> None:
        records = [
            [1609459200000, 65.0],  # 2021-01-01
            [1640995200000, 70.0],  # 2022-01-01
        ]
        df = DeribitIVDownloader._parse_records(
            records, date(2021, 6, 1), date(2021, 12, 31),
        )
        # Only second record should be filtered out (2022)
        # First record (2021-01-01) is also outside range
        assert len(df) == 0

    def test_empty_records(self) -> None:
        df = DeribitIVDownloader._parse_records([], date(2021, 1, 1), date(2021, 12, 31))
        assert df.is_empty()

    def test_sorted_by_time(self) -> None:
        records = [
            [1609545600000, 70.0],  # 2021-01-02
            [1609459200000, 65.0],  # 2021-01-01
        ]
        df = DeribitIVDownloader._parse_records(
            records, date(2021, 1, 1), date(2021, 12, 31),
        )
        times = df["time"].to_list()
        assert times[0] < times[1]

    def test_deduplication(self) -> None:
        records = [
            [1609459200000, 65.0],
            [1609459200000, 65.0],
        ]
        df = DeribitIVDownloader._parse_records(
            records, date(2021, 1, 1), date(2021, 12, 31),
        )
        assert len(df) == 1

    def test_malformed_records_skipped(self) -> None:
        records = [
            [1609459200000, 65.0],
            [1609545600000],  # missing IV value
            [],  # empty
        ]
        df = DeribitIVDownloader._parse_records(
            records, date(2021, 1, 1), date(2021, 12, 31),
        )
        assert len(df) == 1

    def test_output_dtypes(self) -> None:
        records = [[1609459200000, 65.0]]
        df = DeribitIVDownloader._parse_records(
            records, date(2021, 1, 1), date(2021, 12, 31),
        )
        assert df["iv_index"].dtype == pl.Float64
        assert df["time"].dtype == pl.Datetime("us", "UTC")
