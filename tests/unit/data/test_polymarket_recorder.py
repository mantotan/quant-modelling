"""Tests for Polymarket odds recorder."""

import pytest

from qm.core.types import Asset
from qm.data.connectors.polymarket_recorder import (
    _extract_prices,
    _extract_token_ids,
    _is_binary_up_down,
    _is_short_duration_market,
    _match_asset,
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
