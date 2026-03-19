"""Polymarket market scanner: discovers active binary crypto markets.

Reuses PolymarketOddsRecorder discovery logic, adds depth/liquidity
filtering via CLOB orderbook.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import aiohttp

from qm.core.types import Asset, MarketType, PolymarketMarket
from qm.data.connectors.polymarket_recorder import (
    _extract_prices,
    _extract_token_ids,
    _is_binary_up_down,
    _is_short_duration_market,
    _match_asset,
)

logger = logging.getLogger(__name__)

GAMMA_API_URL = "https://gamma-api.polymarket.com/markets"


class MarketScanner:
    """Discovers and filters active Polymarket binary crypto markets.

    Filters:
    - Asset match (BTC, ETH, SOL, XRP)
    - Binary Up/Down structure
    - Short duration (5m, 15m, 1h)
    - Minimum time remaining (>60s)
    - Minimum volume
    """

    def __init__(
        self,
        assets: set[Asset] | None = None,
        min_time_remaining_sec: float = 60.0,
        min_volume: float = 0.0,
        max_duration_min: int = 60,
    ) -> None:
        self._assets = assets or {Asset.BTC, Asset.ETH}
        self._min_time_remaining = min_time_remaining_sec
        self._min_volume = min_volume
        self._max_duration_min = max_duration_min
        self._cache: dict[Asset, PolymarketMarket] = {}
        self._cache_time: float = 0.0
        self._cache_ttl = 10.0  # refresh every 10s

    async def get_active_market(
        self, asset: Asset,
    ) -> PolymarketMarket | None:
        """Get the best active market for an asset.

        Returns cached result if < 10s old to avoid API spam.
        """
        now = datetime.now(UTC).timestamp()
        if now - self._cache_time < self._cache_ttl and asset in self._cache:
            return self._cache.get(asset)

        markets = await self._discover()
        self._cache = {m.asset: m for m in markets}
        self._cache_time = now
        return self._cache.get(asset)

    async def get_market_status(
        self, condition_id: str,
    ) -> dict[str, Any] | None:
        """Check if a market has resolved via Gamma API."""
        url = f"{GAMMA_API_URL}?condition_id={condition_id}"
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10),
            ) as session, session.get(url) as resp:
                if resp.status != 200:
                    return None
                markets = await resp.json()
                if markets and len(markets) > 0:
                    return markets[0]
        except Exception:
            logger.debug("Failed to check market status %s", condition_id[:12])
        return None

    async def _discover(self) -> list[PolymarketMarket]:
        """Query Gamma API for active crypto binary markets."""
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10),
            ) as session, session.get(
                GAMMA_API_URL,
                params={"active": "true", "closed": "false"},
            ) as resp:
                if resp.status != 200:
                    return []
                all_markets = await resp.json()
        except Exception:
            logger.debug("Gamma API unreachable")
            return []

        matched = []
        now = datetime.now(UTC)

        for m in all_markets:
            tokens = m.get("tokens", [])
            if not _is_binary_up_down(tokens):
                continue

            asset = _match_asset(m.get("question", ""))
            if asset is None or asset not in self._assets:
                continue

            if not _is_short_duration_market(m, self._max_duration_min):
                continue

            token_ids = _extract_token_ids(tokens)
            if token_ids is None:
                continue

            price_up, price_down = _extract_prices(tokens)
            if price_up is None:
                continue

            volume = float(m.get("volume", 0) or 0)
            if volume < self._min_volume:
                continue

            # Parse window end for time-remaining filter
            end_str = m.get("end_date_iso", "")
            if end_str:
                try:
                    window_end = datetime.fromisoformat(
                        end_str.replace("Z", "+00:00"),
                    )
                    remaining = (window_end - now).total_seconds()
                    if remaining < self._min_time_remaining:
                        continue
                except (ValueError, TypeError):
                    pass

            start_str = (
                m.get("game_start_time", "")
                or m.get("start_date_iso", "")
            )
            try:
                window_start = datetime.fromisoformat(
                    start_str.replace("Z", "+00:00"),
                ) if start_str else now
            except (ValueError, TypeError):
                window_start = now

            try:
                window_end_parsed = datetime.fromisoformat(
                    end_str.replace("Z", "+00:00"),
                ) if end_str else now + timedelta(minutes=5)
            except (ValueError, TypeError):
                window_end_parsed = now + timedelta(minutes=5)

            spread = abs(1.0 - price_up - (price_down or (1.0 - price_up)))

            matched.append(PolymarketMarket(
                condition_id=m.get("condition_id", ""),
                token_id_up=token_ids[0],
                token_id_down=token_ids[1],
                asset=asset,
                market_type=MarketType.FIVE_MIN,
                window_start=window_start,
                window_end=window_end_parsed,
                mid_up=price_up,
                spread=spread,
                volume=volume,
            ))

        logger.debug("Discovered %d markets for %s", len(matched), self._assets)
        return matched
