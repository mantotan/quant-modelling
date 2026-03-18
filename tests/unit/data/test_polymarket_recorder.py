"""Tests for Polymarket odds recorder."""

from datetime import UTC, datetime

import pytest

from qm.core.types import Asset
from qm.data.connectors.polymarket_recorder import (
    _compute_spread,
    _detect_market_type,
    _extract_prices,
    _extract_token_ids,
    _is_binary_up_down,
    _is_short_duration_market,
    _match_asset,
    _parse_window_end,
    _parse_window_start,
)


class TestMatchAsset:
    def test_matches_btc(self):
        assert _match_asset("Will BTC 5m candle close up?") == Asset.BTC

    def test_matches_bitcoin(self):
        assert _match_asset("Bitcoin 5-minute candle") == Asset.BTC

    def test_matches_eth(self):
        assert _match_asset("ETH price up in 5 min") == Asset.ETH

    def test_matches_solana(self):
        assert _match_asset("Solana 5m candle") == Asset.SOL

    def test_no_match(self):
        assert _match_asset("US election result") is None

    def test_case_insensitive(self):
        assert _match_asset("btc 5m UP") == Asset.BTC


class TestIsBinaryUpDown:
    def test_valid_up_down(self):
        tokens = [
            {"outcome": "Up", "token_id": "abc", "price": "0.55"},
            {"outcome": "Down", "token_id": "def", "price": "0.45"},
        ]
        assert _is_binary_up_down(tokens) is True

    def test_yes_no_not_binary(self):
        tokens = [
            {"outcome": "Yes", "token_id": "abc"},
            {"outcome": "No", "token_id": "def"},
        ]
        assert _is_binary_up_down(tokens) is False

    def test_empty(self):
        assert _is_binary_up_down([]) is False


class TestExtractTokenIds:
    def test_extracts_ids(self):
        tokens = [
            {"outcome": "Up", "token_id": "token_up_123"},
            {"outcome": "Down", "token_id": "token_down_456"},
        ]
        result = _extract_token_ids(tokens)
        assert result == ("token_up_123", "token_down_456")

    def test_missing_up(self):
        tokens = [{"outcome": "Down", "token_id": "token_down_456"}]
        assert _extract_token_ids(tokens) is None


class TestExtractPrices:
    def test_extracts_prices(self):
        tokens = [
            {"outcome": "Up", "price": "0.55"},
            {"outcome": "Down", "price": "0.45"},
        ]
        up, down = _extract_prices(tokens)
        assert up == pytest.approx(0.55)
        assert down == pytest.approx(0.45)

    def test_handles_none(self):
        tokens = [
            {"outcome": "Up", "price": None},
            {"outcome": "Down", "price": "0.45"},
        ]
        up, down = _extract_prices(tokens)
        assert up is None
        assert down == pytest.approx(0.45)

    def test_handles_invalid(self):
        tokens = [{"outcome": "Up", "price": "invalid"}]
        up, _ = _extract_prices(tokens)
        assert up is None


class TestIsShortDurationMarket:
    def test_5m_from_dates(self):
        market = {
            "game_start_time": "2026-03-19T12:00:00Z",
            "end_date_iso": "2026-03-19T12:05:00Z",
        }
        assert _is_short_duration_market(market) is True

    def test_1h_from_dates(self):
        market = {
            "game_start_time": "2026-03-19T12:00:00Z",
            "end_date_iso": "2026-03-19T13:00:00Z",
        }
        assert _is_short_duration_market(market) is True

    def test_long_market_rejected(self):
        market = {
            "game_start_time": "2026-03-19T00:00:00Z",
            "end_date_iso": "2026-03-20T00:00:00Z",
        }
        assert _is_short_duration_market(market) is False

    def test_fallback_to_question(self):
        market = {"question": "BTC 5m candle up?", "end_date_iso": "2026-03-19T12:05:00Z"}
        assert _is_short_duration_market(market) is True

    def test_no_info(self):
        market = {"question": "Something random"}
        assert _is_short_duration_market(market) is False


class TestDetectMarketType:
    def test_5m_from_duration(self):
        market = {
            "game_start_time": "2026-01-01T00:00:00Z",
            "end_date_iso": "2026-01-01T00:05:00Z",
        }
        assert _detect_market_type(market) == "5m"

    def test_15m_from_duration(self):
        market = {
            "game_start_time": "2026-01-01T00:00:00Z",
            "end_date_iso": "2026-01-01T00:15:00Z",
        }
        assert _detect_market_type(market) == "15m"

    def test_1h_from_duration(self):
        market = {
            "game_start_time": "2026-01-01T00:00:00Z",
            "end_date_iso": "2026-01-01T01:00:00Z",
        }
        assert _detect_market_type(market) == "1h"

    def test_fallback_from_question(self):
        market = {"question": "Will BTC go up in the next 15 minutes?"}
        assert _detect_market_type(market) == "15m"

    def test_default_5m(self):
        market = {"question": "Unknown format"}
        assert _detect_market_type(market) == "5m"


class TestParseWindowStart:
    def test_from_game_start_time(self):
        market = {"game_start_time": "2026-01-01T12:00:00Z"}
        fallback = datetime(2026, 1, 1, tzinfo=UTC)
        result = _parse_window_start(market, fallback)
        assert result.hour == 12

    def test_fallback_on_missing(self):
        fallback = datetime(2026, 1, 1, 8, 0, tzinfo=UTC)
        result = _parse_window_start({}, fallback)
        assert result == fallback


class TestParseWindowEnd:
    def test_from_end_date_iso(self):
        market = {"end_date_iso": "2026-01-01T13:00:00Z"}
        fallback = datetime(2026, 1, 1, tzinfo=UTC)
        result = _parse_window_end(market, fallback)
        assert result.hour == 13

    def test_fallback_on_missing(self):
        fallback = datetime(2026, 1, 1, 8, 0, tzinfo=UTC)
        result = _parse_window_end({}, fallback)
        assert result == fallback


class TestComputeSpread:
    def test_no_spread(self):
        assert _compute_spread(0.55, 0.45) == pytest.approx(0.0)

    def test_positive_spread(self):
        assert _compute_spread(0.55, 0.43) == pytest.approx(0.02)

    def test_none_inputs(self):
        assert _compute_spread(None, 0.45) is None
        assert _compute_spread(0.55, None) is None
