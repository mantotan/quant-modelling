"""Tests for Polymarket CLOB client wrapper.

Covers: PolymarketClient (retry, rate limiting, secret redaction),
OrderManager (heartbeat, timeout, reprice), LiveExecutor (signal routing),
PositionTracker (local/API reconciliation), MarketScanner (slug discovery),
reconcile_on_startup (crash recovery).
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from qm.core.types import Asset, MarketType, Outcome, PolymarketMarket, Signal, Timeframe
from qm.execution.loop import Fill
from qm.execution.polymarket.client import PolymarketClient, _redact
from qm.execution.polymarket.order_manager import (
    ManagedOrder,
    OrderManager,
    OrderStatus,
)
from qm.execution.polymarket.live_executor import LiveExecutor
from qm.execution.polymarket.market_scanner import (
    MarketScanner,
    _current_bar_start,
    _parse_market,
)
from qm.execution.polymarket.position_tracker import PositionTracker
from qm.execution.polymarket.reconciliation import reconcile_on_startup
from qm.risk.bankroll import Bankroll
from qm.strategy.portfolio import Portfolio, Position


# ── Helpers ──────────────────────────────────────────────────


def _make_market(
    asset: Asset = Asset.ETH,
    mid_up: float = 0.55,
    spread: float = 0.02,
) -> PolymarketMarket:
    now = datetime.now(UTC)
    return PolymarketMarket(
        condition_id="cond-123",
        token_id_up="token-up-abc",
        token_id_down="token-down-xyz",
        asset=asset,
        market_type=MarketType.FIVE_MIN,
        window_start=now,
        window_end=now + timedelta(minutes=5),
        mid_up=mid_up,
        spread=spread,
        volume=10000.0,
    )


def _make_signal(
    asset: Asset = Asset.ETH,
    side: Outcome = Outcome.UP,
    model_prob: float = 0.65,
    market_prob: float = 0.55,
) -> Signal:
    return Signal(
        timestamp=datetime.now(UTC),
        asset=asset,
        market_type=MarketType.FIVE_MIN,
        model_prob_up=model_prob,
        market_prob_up=market_prob,
        edge=abs(model_prob - market_prob),
        confidence=0.7,
        recommended_side=side,
        recommended_size=100.0,
    )


# ── _redact tests ───────────────────────────────────────────


class TestRedact:
    def test_short_string_fully_redacted(self):
        assert _redact("abc") == "***"
        assert _redact("") == "***"

    def test_long_string_shows_ends(self):
        result = _redact("0x1234567890abcdef")
        assert result.startswith("0x12")
        assert result.endswith("cdef")
        assert "..." in result

    def test_exact_8_chars(self):
        result = _redact("12345678")
        assert result == "1234...5678"


# ── PolymarketClient tests ──────────────────────────────────


class TestPolymarketClient:
    @patch.dict("os.environ", {}, clear=True)
    @patch("qm.execution.polymarket.client.ClobClient")
    def test_init_no_credentials_l0(self, mock_clob_cls):
        """Client initializes at L0 when no env vars set."""
        client = PolymarketClient()
        # Should have been called with key=None, creds=None
        call_kwargs = mock_clob_cls.call_args
        assert call_kwargs[1].get("key") is None or call_kwargs.kwargs.get("key") is None

    @patch.dict(
        "os.environ",
        {
            "POLYMARKET_PRIVATE_KEY": "0xdeadbeef1234567890",
            "POLYMARKET_API_KEY": "api-key-123",
            "POLYMARKET_API_SECRET": "api-secret-456",
            "POLYMARKET_PASSPHRASE": "passphrase-789",
        },
    )
    @patch("qm.execution.polymarket.client.ClobClient")
    def test_init_full_credentials_l2(self, mock_clob_cls):
        """Client initializes at L2 with all env vars."""
        client = PolymarketClient()
        call_args = mock_clob_cls.call_args
        # creds should be an ApiCreds instance
        assert call_args.kwargs.get("creds") is not None or call_args[1].get("creds") is not None

    @patch.dict("os.environ", {"POLYMARKET_PRIVATE_KEY": "0xdeadbeef"})
    @patch("qm.execution.polymarket.client.ClobClient")
    def test_rate_limiting(self, mock_clob_cls):
        """Rate limiting enforces minimum interval between calls."""
        mock_inner = MagicMock()
        mock_inner.get_order_book.return_value = {"bids": [], "asks": []}
        mock_clob_cls.return_value = mock_inner

        client = PolymarketClient()
        t0 = time.monotonic()
        client.get_order_book("token-1")
        client.get_order_book("token-2")
        elapsed = time.monotonic() - t0
        # Should have at least one rate limit sleep (0.1s)
        assert elapsed >= 0.09

    @patch.dict("os.environ", {"POLYMARKET_PRIVATE_KEY": "0xdeadbeef"})
    @patch("qm.execution.polymarket.client.ClobClient")
    def test_retry_on_failure(self, mock_clob_cls):
        """Retry logic with exponential backoff."""
        mock_inner = MagicMock()
        mock_inner.get_order_book.side_effect = [
            ConnectionError("timeout"),
            {"bids": [], "asks": []},
        ]
        mock_clob_cls.return_value = mock_inner

        client = PolymarketClient()
        result = client.get_order_book("token-1")
        assert result == {"bids": [], "asks": []}
        assert mock_inner.get_order_book.call_count == 2

    @patch.dict("os.environ", {"POLYMARKET_PRIVATE_KEY": "0xdeadbeef"})
    @patch("qm.execution.polymarket.client.ClobClient")
    def test_retry_exhaustion_raises(self, mock_clob_cls):
        """After max retries, the exception propagates."""
        mock_inner = MagicMock()
        mock_inner.get_order_book.side_effect = ConnectionError("persistent failure")
        mock_clob_cls.return_value = mock_inner

        client = PolymarketClient()
        with pytest.raises(ConnectionError, match="persistent failure"):
            client.get_order_book("token-1")
        assert mock_inner.get_order_book.call_count == 3  # _MAX_RETRIES

    @patch.dict("os.environ", {"POLYMARKET_PRIVATE_KEY": "0xdeadbeef"})
    @patch("qm.execution.polymarket.client.ClobClient")
    def test_cancel_order(self, mock_clob_cls):
        mock_inner = MagicMock()
        mock_inner.cancel_orders.return_value = {"cancelled": ["order-1"]}
        mock_clob_cls.return_value = mock_inner

        client = PolymarketClient()
        result = client.cancel_order("order-1")
        mock_inner.cancel_orders.assert_called_with(["order-1"])

    @patch.dict("os.environ", {"POLYMARKET_PRIVATE_KEY": "0xdeadbeef"})
    @patch("qm.execution.polymarket.client.ClobClient")
    def test_cancel_all(self, mock_clob_cls):
        mock_inner = MagicMock()
        mock_inner.cancel_all.return_value = {"cancelled": 5}
        mock_clob_cls.return_value = mock_inner

        client = PolymarketClient()
        result = client.cancel_all()
        mock_inner.cancel_all.assert_called_once()

    @patch.dict("os.environ", {"POLYMARKET_PRIVATE_KEY": "0xdeadbeef"})
    @patch("qm.execution.polymarket.client.ClobClient")
    def test_get_open_orders_returns_list(self, mock_clob_cls):
        mock_inner = MagicMock()
        mock_inner.get_orders.return_value = [{"id": "1"}, {"id": "2"}]
        mock_clob_cls.return_value = mock_inner

        client = PolymarketClient()
        result = client.get_open_orders()
        assert isinstance(result, list)
        assert len(result) == 2

    @patch.dict("os.environ", {"POLYMARKET_PRIVATE_KEY": "0xdeadbeef"})
    @patch("qm.execution.polymarket.client.ClobClient")
    def test_get_open_orders_non_list_returns_empty(self, mock_clob_cls):
        mock_inner = MagicMock()
        mock_inner.get_orders.return_value = None
        mock_clob_cls.return_value = mock_inner

        client = PolymarketClient()
        result = client.get_open_orders()
        assert result == []

    @patch.dict("os.environ", {"POLYMARKET_PRIVATE_KEY": "0xdeadbeef"})
    @patch("qm.execution.polymarket.client.ClobClient")
    def test_get_mid_price(self, mock_clob_cls):
        mock_inner = MagicMock()
        mock_inner.get_midpoint.return_value = {"mid": "0.55"}
        mock_clob_cls.return_value = mock_inner

        client = PolymarketClient()
        result = client.get_mid_price("token-1")
        assert result == 0.55

    @patch.dict("os.environ", {"POLYMARKET_PRIVATE_KEY": "0xdeadbeef"})
    @patch("qm.execution.polymarket.client.ClobClient")
    def test_get_mid_price_failure_returns_none(self, mock_clob_cls):
        mock_inner = MagicMock()
        mock_inner.get_midpoint.side_effect = Exception("api error")
        mock_clob_cls.return_value = mock_inner

        client = PolymarketClient()
        result = client.get_mid_price("token-1")
        assert result is None

    @patch.dict("os.environ", {"POLYMARKET_PRIVATE_KEY": "0xdeadbeef"})
    @patch("qm.execution.polymarket.client.ClobClient")
    def test_get_spread(self, mock_clob_cls):
        mock_inner = MagicMock()
        mock_inner.get_spread.return_value = {"spread": "0.03"}
        mock_clob_cls.return_value = mock_inner

        client = PolymarketClient()
        result = client.get_spread("token-1")
        assert result == 0.03


# ── OrderManager tests ───────────────────────────────────────


class TestOrderManager:
    def _mock_client(self) -> MagicMock:
        client = MagicMock(spec=PolymarketClient)
        client.create_and_post_order.return_value = {"orderID": "order-abc-123"}
        client.get_order.return_value = {"status": "MATCHED", "size_matched": "100"}
        client.cancel_order.return_value = {}
        return client

    @pytest.mark.asyncio
    async def test_submit_dry_run(self):
        """Dry run mode returns filled without API call."""
        client = self._mock_client()
        mgr = OrderManager(client)
        order = await mgr.submit(
            token_id="token-1", price=0.55, size=100,
            side="BUY", submit=False,
        )
        assert order.status == OrderStatus.FILLED
        assert order.filled_size == 100
        assert order.order_id.startswith("dry-run-")
        client.create_and_post_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_submit_immediate_fill(self):
        """Order that fills immediately on first status check."""
        client = self._mock_client()
        mgr = OrderManager(client, heartbeat_interval=0.01)
        order = await mgr.submit(
            token_id="token-1", price=0.55, size=100,
            side="BUY", submit=True,
        )
        assert order.status == OrderStatus.FILLED
        assert order.order_id == "order-abc-123"
        assert mgr.fill_count == 1

    @pytest.mark.asyncio
    async def test_submit_timeout_expires(self):
        """Order that never fills gets expired after timeout."""
        client = self._mock_client()
        client.get_order.return_value = {"status": "LIVE"}
        mgr = OrderManager(
            client,
            heartbeat_interval=0.01,
            cancel_timeout=0.05,
        )
        order = await mgr.submit(
            token_id="token-1", price=0.55, size=100,
            side="BUY", submit=True,
        )
        assert order.status == OrderStatus.EXPIRED
        assert mgr.active_count == 0

    @pytest.mark.asyncio
    async def test_submit_failure_returns_failed(self):
        """API failure on order submission returns FAILED status."""
        client = self._mock_client()
        client.create_and_post_order.side_effect = Exception("API down")
        mgr = OrderManager(client)
        order = await mgr.submit(
            token_id="token-1", price=0.55, size=100,
            side="BUY", submit=True,
        )
        assert order.status == OrderStatus.FAILED

    @pytest.mark.asyncio
    async def test_submit_cancelled_by_api(self):
        """Order cancelled externally on API side."""
        client = self._mock_client()
        client.get_order.return_value = {"status": "CANCELED"}
        mgr = OrderManager(client, heartbeat_interval=0.01)
        order = await mgr.submit(
            token_id="token-1", price=0.55, size=100,
            side="BUY", submit=True,
        )
        assert order.status == OrderStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_stop_exits_monitor_loop(self):
        """Calling stop() causes the monitoring loop to exit."""
        client = self._mock_client()
        client.get_order.return_value = {"status": "LIVE"}
        mgr = OrderManager(client, heartbeat_interval=0.01, cancel_timeout=10.0)

        async def stop_soon():
            await asyncio.sleep(0.05)
            mgr.stop()

        asyncio.get_event_loop().create_task(stop_soon())
        order = await mgr.submit(
            token_id="token-1", price=0.55, size=100,
            side="BUY", submit=True,
        )
        # Should exit without reaching timeout
        assert order.status in (OrderStatus.PLACED, OrderStatus.PARTIALLY_FILLED)

    def test_compute_reprice_buy_tightens(self):
        """Buy reprice moves price up."""
        client = self._mock_client()
        mgr = OrderManager(client)
        new = mgr._compute_reprice(0.50, "BUY", 0.50)
        assert new is not None
        assert new > 0.50

    def test_compute_reprice_sell_tightens(self):
        """Sell reprice moves price down."""
        client = self._mock_client()
        mgr = OrderManager(client)
        new = mgr._compute_reprice(0.50, "SELL", 0.50)
        assert new is not None
        assert new < 0.50

    def test_compute_reprice_buy_max_slippage(self):
        """Reprice returns None when max slippage would be exceeded."""
        client = self._mock_client()
        mgr = OrderManager(client, max_slippage=0.01)
        # Already at original + 0.01, next step would exceed
        new = mgr._compute_reprice(0.51, "BUY", 0.50)
        assert new is None

    def test_compute_reprice_clamps_to_bounds(self):
        """Price never goes below 0.01 or above 0.99."""
        client = self._mock_client()
        mgr = OrderManager(client, max_slippage=0.10)
        # Sell at very low price: max(0.01, 0.01 - 0.005) = 0.01
        new = mgr._compute_reprice(0.01, "SELL", 0.05)
        assert new == 0.01
        # Buy at very high price: min(0.99, 0.99 + 0.005) = 0.99
        # 0.995 < 0.95 + 0.10 = 1.05 so slippage not exceeded
        new = mgr._compute_reprice(0.99, "BUY", 0.95)
        assert new == 0.99  # clamped to 0.99 ceiling
        # But if max_slippage is tiny, it returns None
        mgr2 = OrderManager(client, max_slippage=0.01)
        new = mgr2._compute_reprice(0.96, "BUY", 0.95)
        assert new is None  # 0.965 > 0.95 + 0.01 = 0.96

    @pytest.mark.asyncio
    async def test_partial_fill_tracking(self):
        """Partial fills are tracked before full fill."""
        client = self._mock_client()
        call_count = 0

        def status_sequence(order_id):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"status": "LIVE", "size_matched": "50"}
            return {"status": "MATCHED", "size_matched": "100"}

        client.get_order.side_effect = status_sequence
        mgr = OrderManager(client, heartbeat_interval=0.01)
        order = await mgr.submit(
            token_id="token-1", price=0.55, size=100,
            side="BUY", submit=True,
        )
        assert order.status == OrderStatus.FILLED


# ── MarketScanner tests ─────────────────────────────────────


class TestMarketScanner:
    def test_current_bar_start_aligns(self):
        """Bar start aligns to bar boundary."""
        bar_start = _current_bar_start(300)  # 5m bars
        assert bar_start % 300 == 0

    def test_parse_market_valid(self):
        """Parse a well-formed Gamma API response."""
        now = datetime.now(UTC)
        m = {
            "conditionId": "cond-abc",
            "outcomes": '["Up", "Down"]',
            "outcomePrices": '["0.55", "0.45"]',
            "clobTokenIds": '["token-up", "token-down"]',
            "startDate": now.isoformat(),
            "endDate": (now + timedelta(minutes=5)).isoformat(),
            "volume": 50000,
            "active": True,
        }
        result = _parse_market(m, Asset.BTC, MarketType.FIVE_MIN)
        assert result is not None
        assert result.condition_id == "cond-abc"
        assert result.token_id_up == "token-up"
        assert result.token_id_down == "token-down"
        assert result.asset == Asset.BTC
        assert result.mid_up == 0.55
        assert result.volume == 50000

    def test_parse_market_missing_outcomes(self):
        """Returns None when outcomes can't be parsed."""
        result = _parse_market(
            {"outcomes": "invalid json", "outcomePrices": "[]", "clobTokenIds": "[]"},
            Asset.BTC, MarketType.FIVE_MIN,
        )
        assert result is None

    def test_parse_market_no_up_down(self):
        """Returns None when Up/Down outcomes not present."""
        m = {
            "outcomes": '["Yes", "No"]',
            "outcomePrices": '["0.55", "0.45"]',
            "clobTokenIds": '["token-yes", "token-no"]',
        }
        result = _parse_market(m, Asset.BTC, MarketType.FIVE_MIN)
        assert result is None

    def test_parse_market_price_index_mismatch(self):
        """Returns None when price array is shorter than outcome index."""
        m = {
            "outcomes": '["Up", "Down"]',
            "outcomePrices": '["0.55"]',  # only 1 price for 2 outcomes
            "clobTokenIds": '["token-up", "token-down"]',
        }
        result = _parse_market(m, Asset.BTC, MarketType.FIVE_MIN)
        assert result is None

    def test_parse_market_array_outcomes(self):
        """Handles outcomes as native arrays (not JSON strings)."""
        now = datetime.now(UTC)
        m = {
            "conditionId": "cond-xyz",
            "outcomes": ["Up", "Down"],
            "outcomePrices": [0.60, 0.40],
            "clobTokenIds": ["t-up", "t-down"],
            "startDate": now.isoformat(),
            "endDate": (now + timedelta(minutes=5)).isoformat(),
            "volume": 1000,
        }
        result = _parse_market(m, Asset.ETH, MarketType.FIVE_MIN)
        assert result is not None
        assert result.mid_up == 0.60

    def test_parse_market_spread_calculation(self):
        """Spread is abs(1 - up - down)."""
        now = datetime.now(UTC)
        m = {
            "conditionId": "cond-1",
            "outcomes": '["Up", "Down"]',
            "outcomePrices": '["0.52", "0.46"]',
            "clobTokenIds": '["t-u", "t-d"]',
            "startDate": now.isoformat(),
            "endDate": (now + timedelta(minutes=5)).isoformat(),
            "volume": 0,
        }
        result = _parse_market(m, Asset.SOL, MarketType.FIVE_MIN)
        assert result is not None
        assert abs(result.spread - 0.02) < 1e-9

    @pytest.mark.asyncio
    async def test_scanner_caching(self):
        """Repeated calls within TTL use cache, not re-discover."""
        scanner = MarketScanner(assets={Asset.BTC})
        market = _make_market(Asset.BTC)
        scanner._cache = {Asset.BTC: market}
        scanner._cache_time = datetime.now(UTC).timestamp()

        result = await scanner.get_active_market(Asset.BTC)
        assert result is not None
        assert result.asset == Asset.BTC

    @pytest.mark.asyncio
    async def test_scanner_cache_miss_returns_none(self):
        """Non-cached asset returns None without network call when cache is fresh."""
        scanner = MarketScanner(assets={Asset.BTC})
        scanner._cache = {Asset.BTC: _make_market(Asset.BTC)}
        scanner._cache_time = datetime.now(UTC).timestamp()

        result = await scanner.get_active_market(Asset.ETH)
        assert result is None


# ── LiveExecutor tests ───────────────────────────────────────


class TestLiveExecutor:
    @pytest.mark.asyncio
    async def test_execute_no_market_rejected(self):
        """No market returns rejected fill."""
        client = MagicMock(spec=PolymarketClient)
        mgr = MagicMock(spec=OrderManager)
        executor = LiveExecutor(client, mgr)

        signal = _make_signal()
        fill = await executor.execute(signal, 100.0, market=None)
        assert fill.status == "rejected"
        assert fill.size_usd == 0.0

    @pytest.mark.asyncio
    async def test_execute_up_side_uses_up_token(self):
        """UP signal routes to token_id_up."""
        client = MagicMock(spec=PolymarketClient)
        mgr = MagicMock(spec=OrderManager)

        filled_order = ManagedOrder(
            order_id="fill-1", token_id="token-up-abc",
            side="BUY", price=0.54, size=185.19,
            filled_size=185.19, status=OrderStatus.FILLED,
        )
        mgr.submit = AsyncMock(return_value=filled_order)

        executor = LiveExecutor(client, mgr)
        signal = _make_signal(side=Outcome.UP, market_prob=0.55)
        market = _make_market(mid_up=0.55, spread=0.02)

        fill = await executor.execute(signal, 100.0, market=market)
        assert fill.status == "filled"
        # Verify submit was called with the UP token
        call_args = mgr.submit.call_args
        assert call_args.kwargs["token_id"] == "token-up-abc"

    @pytest.mark.asyncio
    async def test_execute_down_side_uses_down_token(self):
        """DOWN signal routes to token_id_down."""
        client = MagicMock(spec=PolymarketClient)
        mgr = MagicMock(spec=OrderManager)

        filled_order = ManagedOrder(
            order_id="fill-2", token_id="token-down-xyz",
            side="BUY", price=0.44, size=227.27,
            filled_size=227.27, status=OrderStatus.FILLED,
        )
        mgr.submit = AsyncMock(return_value=filled_order)

        executor = LiveExecutor(client, mgr)
        signal = _make_signal(side=Outcome.DOWN, market_prob=0.55)
        market = _make_market(mid_up=0.55, spread=0.02)

        fill = await executor.execute(signal, 100.0, market=market)
        assert fill.status == "filled"
        call_args = mgr.submit.call_args
        assert call_args.kwargs["token_id"] == "token-down-xyz"

    @pytest.mark.asyncio
    async def test_execute_partial_fill(self):
        """Partial fill returns filled status with partial size."""
        client = MagicMock(spec=PolymarketClient)
        mgr = MagicMock(spec=OrderManager)

        partial_order = ManagedOrder(
            order_id="partial-1", token_id="token-up-abc",
            side="BUY", price=0.54, size=185.19,
            filled_size=92.6, status=OrderStatus.PARTIALLY_FILLED,
        )
        mgr.submit = AsyncMock(return_value=partial_order)

        executor = LiveExecutor(client, mgr)
        signal = _make_signal(side=Outcome.UP)
        market = _make_market()

        fill = await executor.execute(signal, 100.0, market=market)
        assert fill.status == "filled"
        assert fill.size_usd == pytest.approx(92.6 * 0.54, rel=1e-2)

    @pytest.mark.asyncio
    async def test_execute_expired_order(self):
        """Expired order returns expired status."""
        client = MagicMock(spec=PolymarketClient)
        mgr = MagicMock(spec=OrderManager)

        expired_order = ManagedOrder(
            order_id="expired-1", token_id="token-up-abc",
            side="BUY", price=0.54, size=185.19,
            filled_size=0, status=OrderStatus.EXPIRED,
        )
        mgr.submit = AsyncMock(return_value=expired_order)

        executor = LiveExecutor(client, mgr)
        signal = _make_signal(side=Outcome.UP)
        market = _make_market()

        fill = await executor.execute(signal, 100.0, market=market)
        assert fill.status == "expired"
        assert fill.size_usd == 0.0

    @pytest.mark.asyncio
    async def test_fill_counter_increments(self):
        """Total fills counter tracks successful fills."""
        client = MagicMock(spec=PolymarketClient)
        mgr = MagicMock(spec=OrderManager)

        filled = ManagedOrder(
            order_id="fill-x", token_id="t",
            side="BUY", price=0.50, size=100,
            filled_size=100, status=OrderStatus.FILLED,
        )
        mgr.submit = AsyncMock(return_value=filled)

        executor = LiveExecutor(client, mgr)
        signal = _make_signal()
        market = _make_market()

        await executor.execute(signal, 100.0, market=market)
        await executor.execute(signal, 100.0, market=market)
        assert executor.total_fills == 2

    @pytest.mark.asyncio
    async def test_maker_pricing_below_mid(self):
        """Limit price should be at or below the mid price (maker-only)."""
        client = MagicMock(spec=PolymarketClient)
        mgr = MagicMock(spec=OrderManager)

        filled = ManagedOrder(
            order_id="fill-y", token_id="t",
            side="BUY", price=0.50, size=100,
            filled_size=100, status=OrderStatus.FILLED,
        )
        mgr.submit = AsyncMock(return_value=filled)

        executor = LiveExecutor(client, mgr)
        signal = _make_signal(side=Outcome.UP, market_prob=0.55)
        market = _make_market(mid_up=0.55, spread=0.04)

        await executor.execute(signal, 100.0, market=market)
        call_args = mgr.submit.call_args
        limit_price = call_args.kwargs["price"]
        # Price should be mid - spread/2 = 0.55 - 0.02 = 0.53
        assert limit_price == pytest.approx(0.53, abs=0.001)


# ── PositionTracker tests ───────────────────────────────────


class TestPositionTracker:
    def test_reconcile_all_matched(self):
        """All local positions found on API."""
        client = MagicMock(spec=PolymarketClient)
        client.get_open_orders.return_value = [
            {"id": "pos-1"},
            {"id": "pos-2"},
        ]

        bankroll = Bankroll(initial=10000)
        portfolio = Portfolio(bankroll)
        # Add positions matching the API
        portfolio._positions["p1"] = Position(
            id="p1", asset=Asset.BTC, side=Outcome.UP,
            entry_price=0.55, size_usd=100, shares=181.82,
            entry_time=datetime.now(UTC), condition_id="pos-1",
        )
        portfolio._positions["p2"] = Position(
            id="p2", asset=Asset.ETH, side=Outcome.DOWN,
            entry_price=0.45, size_usd=50, shares=111.11,
            entry_time=datetime.now(UTC), condition_id="pos-2",
        )

        tracker = PositionTracker(client, portfolio)
        stats = tracker.reconcile()
        assert stats["matched"] == 2
        assert stats["stale"] == 0
        assert stats["orphaned"] == 0

    def test_reconcile_stale_local_position(self):
        """Local position not on API detected as stale."""
        client = MagicMock(spec=PolymarketClient)
        client.get_open_orders.return_value = []  # empty API

        bankroll = Bankroll(initial=10000)
        portfolio = Portfolio(bankroll)
        portfolio._positions["p1"] = Position(
            id="p1", asset=Asset.BTC, side=Outcome.UP,
            entry_price=0.55, size_usd=100, shares=181.82,
            entry_time=datetime.now(UTC), condition_id="stale-cond",
        )

        tracker = PositionTracker(client, portfolio)
        stats = tracker.reconcile()
        assert stats["stale"] == 1

    def test_reconcile_orphaned_api_order(self):
        """API order not in local portfolio detected as orphaned."""
        client = MagicMock(spec=PolymarketClient)
        client.get_open_orders.return_value = [
            {"id": "orphan-order"},
        ]

        bankroll = Bankroll(initial=10000)
        portfolio = Portfolio(bankroll)

        tracker = PositionTracker(client, portfolio)
        stats = tracker.reconcile()
        assert stats["orphaned"] == 1

    def test_reconcile_api_failure(self):
        """API failure returns zeroed stats."""
        client = MagicMock(spec=PolymarketClient)
        client.get_open_orders.side_effect = Exception("API error")

        bankroll = Bankroll(initial=10000)
        portfolio = Portfolio(bankroll)

        tracker = PositionTracker(client, portfolio)
        stats = tracker.reconcile()
        assert stats == {"matched": 0, "orphaned": 0, "stale": 0, "resolved": 0}


# ── reconcile_on_startup tests ──────────────────────────────


class TestReconcileOnStartup:
    @pytest.mark.asyncio
    async def test_fresh_start_no_state_file(self, tmp_path):
        """No state file starts fresh with zero stats."""
        bankroll = Bankroll(initial=10000)
        portfolio = Portfolio(bankroll)

        stats = await reconcile_on_startup(
            state_file=tmp_path / "nonexistent.json",
            portfolio=portfolio,
        )
        assert stats["loaded"] == 0

    @pytest.mark.asyncio
    async def test_restore_bankroll_from_state(self, tmp_path):
        """Bankroll restored from JSON state file."""
        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps({
            "bankroll": {
                "initial": 10000,
                "current": 10500,
                "high_water_mark": 10800,
                "daily_pnl": 50,
                "total_realized_pnl": 500,
            },
        }))

        bankroll = Bankroll(initial=10000)
        portfolio = Portfolio(bankroll)

        stats = await reconcile_on_startup(
            state_file=state_file,
            portfolio=portfolio,
        )
        assert stats["loaded"] == 1
        assert portfolio.bankroll.current == 10500
        assert portfolio.bankroll.high_water_mark == 10800

    @pytest.mark.asyncio
    async def test_corrupt_state_file_no_crash(self, tmp_path):
        """Corrupt JSON doesn't crash, starts fresh."""
        state_file = tmp_path / "state.json"
        state_file.write_text("not valid json {{{")

        bankroll = Bankroll(initial=10000)
        portfolio = Portfolio(bankroll)

        stats = await reconcile_on_startup(
            state_file=state_file,
            portfolio=portfolio,
        )
        assert stats["loaded"] == 0

    @pytest.mark.asyncio
    async def test_with_tracker_reconciliation(self, tmp_path):
        """Reconcile with tracker."""
        state_file = tmp_path / "state.json"

        bankroll = Bankroll(initial=10000)
        portfolio = Portfolio(bankroll)

        tracker = MagicMock(spec=PositionTracker)
        tracker.reconcile.return_value = {"matched": 3, "orphaned": 1, "stale": 0}

        stats = await reconcile_on_startup(
            state_file=state_file,
            portfolio=portfolio,
            tracker=tracker,
        )
        assert stats["reconciled"] == 3
        tracker.reconcile.assert_called_once()

    @pytest.mark.asyncio
    async def test_offline_resolution_detection(self, tmp_path):
        """Markets that resolved while offline are detected."""
        state_file = tmp_path / "state.json"

        bankroll = Bankroll(initial=10000)
        portfolio = Portfolio(bankroll)
        portfolio._positions["p1"] = Position(
            id="p1", asset=Asset.BTC, side=Outcome.UP,
            entry_price=0.55, size_usd=100, shares=181.82,
            entry_time=datetime.now(UTC), condition_id="resolved-cond",
        )

        scanner = MagicMock(spec=MarketScanner)
        scanner.get_market_status = AsyncMock(return_value={
            "resolved": True,
            "outcome": "Up",
        })

        stats = await reconcile_on_startup(
            state_file=state_file,
            portfolio=portfolio,
            scanner=scanner,
        )
        assert stats["resolved"] == 1
