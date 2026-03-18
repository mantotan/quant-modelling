"""Tests for BinanceFundingRateDownloader."""

from __future__ import annotations

from datetime import UTC, datetime

import polars as pl
import pytest

from qm.data.historical.funding_rate import BinanceFundingRateDownloader


class TestParseRecords:
    """Test the static _parse_records method."""

    def test_basic_parsing(self) -> None:
        records = [
            {
                "symbol": "BTCUSDT",
                "fundingTime": 1569801600000,  # 2019-09-30 00:00:00 UTC
                "fundingRate": "0.00010000",
                "markPrice": "8310.17514214",
            },
            {
                "symbol": "BTCUSDT",
                "fundingTime": 1569830400000,  # 2019-09-30 08:00:00 UTC
                "fundingRate": "-0.00020000",
                "markPrice": "8250.50000000",
            },
        ]

        df = BinanceFundingRateDownloader._parse_records(records)

        assert len(df) == 2
        assert "time" in df.columns
        assert "funding_rate" in df.columns
        assert "mark_price" in df.columns
        assert df["funding_rate"][0] == pytest.approx(0.0001)
        assert df["funding_rate"][1] == pytest.approx(-0.0002)
        assert df["mark_price"][0] == pytest.approx(8310.17514214)

    def test_sorted_by_time(self) -> None:
        records = [
            {"symbol": "BTCUSDT", "fundingTime": 1569830400000,
             "fundingRate": "0.0001", "markPrice": "8000"},
            {"symbol": "BTCUSDT", "fundingTime": 1569801600000,
             "fundingRate": "0.0002", "markPrice": "8100"},
        ]

        df = BinanceFundingRateDownloader._parse_records(records)

        # Should be sorted ascending by time
        times = df["time"].to_list()
        assert times[0] < times[1]

    def test_deduplication(self) -> None:
        records = [
            {"symbol": "BTCUSDT", "fundingTime": 1569801600000,
             "fundingRate": "0.0001", "markPrice": "8000"},
            {"symbol": "BTCUSDT", "fundingTime": 1569801600000,
             "fundingRate": "0.0001", "markPrice": "8000"},
        ]

        df = BinanceFundingRateDownloader._parse_records(records)
        assert len(df) == 1

    def test_empty_records(self) -> None:
        df = BinanceFundingRateDownloader._parse_records([])
        assert df.is_empty()

    def test_missing_mark_price(self) -> None:
        records = [
            {"symbol": "BTCUSDT", "fundingTime": 1569801600000,
             "fundingRate": "0.0001"},
        ]

        df = BinanceFundingRateDownloader._parse_records(records)
        assert len(df) == 1
        assert df["funding_rate"][0] == pytest.approx(0.0001)
        assert df["mark_price"][0] is None

    def test_negative_funding_rate(self) -> None:
        records = [
            {"symbol": "BTCUSDT", "fundingTime": 1569801600000,
             "fundingRate": "-0.00075000", "markPrice": "8000"},
        ]

        df = BinanceFundingRateDownloader._parse_records(records)
        assert df["funding_rate"][0] == pytest.approx(-0.00075)

    def test_datetime_utc(self) -> None:
        records = [
            {"symbol": "BTCUSDT", "fundingTime": 1569801600000,
             "fundingRate": "0.0001", "markPrice": "8000"},
        ]

        df = BinanceFundingRateDownloader._parse_records(records)
        ts = df["time"][0]
        expected = datetime(2019, 9, 30, 0, 0, 0, tzinfo=UTC)
        assert ts == expected

    def test_output_dtypes(self) -> None:
        records = [
            {"symbol": "BTCUSDT", "fundingTime": 1569801600000,
             "fundingRate": "0.0001", "markPrice": "8000"},
        ]

        df = BinanceFundingRateDownloader._parse_records(records)
        assert df["funding_rate"].dtype == pl.Float64
        assert df["time"].dtype == pl.Datetime("us", "UTC")
