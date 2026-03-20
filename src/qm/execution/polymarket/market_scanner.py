"""Polymarket market scanner: discovers active binary crypto markets.

Queries the Gamma API by deterministic slug pattern for 5m/15m/1h
crypto Up/Down markets.

Slug formats:
  5m/15m: {asset}-updown-{tf}-{unix_ts}        e.g. btc-updown-5m-1710864000
  1h:     {asset}-up-or-down-{month}-{day}-{year}-{hour}{am/pm}-et
          e.g. bitcoin-up-or-down-march-20-2026-7am-et

The Gamma API returns outcomes/prices as JSON strings (not token arrays),
so this module parses them directly instead of using the recorder's helpers.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import aiohttp

from qm.core.types import Asset, MarketType, PolymarketMarket, Timeframe

logger = logging.getLogger(__name__)

GAMMA_API_URL = "https://gamma-api.polymarket.com/markets"

# ET timezone for 1h slug construction
_ET = ZoneInfo("America/New_York")

_MONTH_NAMES = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]

# Slug prefixes per asset (lowercase) — used for 5m/15m
_SLUG_ASSET: dict[Asset, str] = {
    Asset.BTC: "btc",
    Asset.ETH: "eth",
    Asset.SOL: "sol",
    Asset.XRP: "xrp",
}

# Full asset names for 1h slug format
_SLUG_ASSET_1H: dict[Asset, str] = {
    Asset.BTC: "bitcoin",
    Asset.ETH: "ethereum",
    Asset.SOL: "solana",
    Asset.XRP: "xrp",
}

# Timeframe → (slug suffix, bar_seconds, MarketType)
_TF_CONFIG: dict[Timeframe, tuple[str, int, MarketType]] = {
    Timeframe.M5: ("5m", 300, MarketType.FIVE_MIN),
    Timeframe.M15: ("15m", 900, MarketType.FIFTEEN_MIN),
    Timeframe.H1: ("1h", 3600, MarketType.ONE_HOUR),
}


def _current_bar_start(bar_seconds: int) -> int:
    """Unix timestamp of the current bar's start."""
    now = int(datetime.now(UTC).timestamp())
    return (now // bar_seconds) * bar_seconds


def _hour_to_slug_suffix(hour: int) -> str:
    """Convert 24h hour to '7am'/'12pm' etc."""
    if hour == 0:
        return "12am"
    if hour < 12:
        return f"{hour}am"
    if hour == 12:
        return "12pm"
    return f"{hour - 12}pm"


def _build_1h_slug(asset: Asset, bar_start_utc: datetime) -> str:
    """Build 1h slug: bitcoin-up-or-down-march-20-2026-7am-et."""
    et_time = bar_start_utc.astimezone(_ET)
    asset_name = _SLUG_ASSET_1H.get(asset, asset.value.lower())
    month = _MONTH_NAMES[et_time.month - 1]
    return (
        f"{asset_name}-up-or-down-{month}-{et_time.day}"
        f"-{et_time.year}-{_hour_to_slug_suffix(et_time.hour)}-et"
    )


def _parse_market(
    m: dict[str, Any], asset: Asset, market_type: MarketType,
) -> PolymarketMarket | None:
    """Parse a Gamma API market dict into PolymarketMarket.

    The API returns outcomes/prices/tokenIds as JSON strings, not arrays.
    """
    # Parse outcomes
    outcomes_raw = m.get("outcomes", "[]")
    try:
        outcomes = json.loads(outcomes_raw) if isinstance(outcomes_raw, str) else outcomes_raw
    except (json.JSONDecodeError, TypeError):
        return None

    outcomes_lower = [o.lower() for o in outcomes]
    if "up" not in outcomes_lower or "down" not in outcomes_lower:
        return None

    up_idx = outcomes_lower.index("up")
    down_idx = outcomes_lower.index("down")

    # Parse prices
    prices_raw = m.get("outcomePrices", "[]")
    try:
        prices = json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw
    except (json.JSONDecodeError, TypeError):
        return None

    if len(prices) <= max(up_idx, down_idx):
        return None

    try:
        price_up = float(prices[up_idx])
        price_down = float(prices[down_idx])
    except (ValueError, TypeError, IndexError):
        return None

    # Parse token IDs
    token_ids_raw = m.get("clobTokenIds", "[]")
    try:
        token_ids = json.loads(token_ids_raw) if isinstance(token_ids_raw, str) else token_ids_raw
    except (json.JSONDecodeError, TypeError):
        return None

    if len(token_ids) <= max(up_idx, down_idx):
        return None

    token_id_up = str(token_ids[up_idx])
    token_id_down = str(token_ids[down_idx])

    # Parse timestamps
    end_str = m.get("endDate", "")
    now = datetime.now(UTC)
    try:
        window_end = datetime.fromisoformat(
            end_str.replace("Z", "+00:00"),
        ) if end_str else now + timedelta(minutes=5)
    except (ValueError, TypeError):
        window_end = now + timedelta(minutes=5)

    start_str = m.get("startDate", "")
    try:
        window_start = datetime.fromisoformat(
            start_str.replace("Z", "+00:00"),
        ) if start_str else now
    except (ValueError, TypeError):
        window_start = now

    spread = abs(1.0 - price_up - price_down)
    volume = float(m.get("volume", 0) or 0)

    return PolymarketMarket(
        condition_id=m.get("conditionId", "") or m.get("condition_id", ""),
        token_id_up=token_id_up,
        token_id_down=token_id_down,
        asset=asset,
        market_type=market_type,
        window_start=window_start,
        window_end=window_end,
        mid_up=price_up,
        spread=spread,
        volume=volume,
    )


class MarketScanner:
    """Discovers active Polymarket crypto Up/Down markets by slug.

    Uses deterministic slug pattern: {asset}-updown-{tf}-{bar_start_unix}
    Queries the current bar's market directly instead of filtering from
    a generic active markets list.
    """

    def __init__(
        self,
        assets: set[Asset] | None = None,
        timeframe: Timeframe = Timeframe.M5,
        min_time_remaining_sec: float = 60.0,
        connector_factory=None,
    ) -> None:
        self._assets = assets or {Asset.BTC, Asset.ETH}
        self._timeframe = timeframe
        self._min_time_remaining = min_time_remaining_sec
        self._cache: dict[Asset, PolymarketMarket] = {}
        self._cache_time: float = 0.0
        self._cache_ttl = 10.0  # refresh every 10s
        # Map condition_id → slug for resolution lookups
        self._slug_cache: dict[str, str] = {}
        self._connector_factory = connector_factory

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
        self,
        condition_id: str,
        asset: Asset | None = None,
        entry_time: datetime | None = None,
    ) -> dict[str, Any] | None:
        """Check if a market has resolved via Gamma API slug lookup.

        The Gamma API condition_id query param doesn't reliably return
        the correct market. Uses cached slug from discovery, or derives
        it from asset + entry_time if not cached.
        """
        slug = self._slug_cache.get(condition_id)
        if not slug and asset and entry_time:
            # Derive slug from asset + entry_time
            tf_cfg = _TF_CONFIG.get(self._timeframe)
            if tf_cfg:
                tf_suffix, bar_seconds, _ = tf_cfg
                if self._timeframe == Timeframe.H1:
                    bar_ts = int(entry_time.timestamp())
                    bar_ts = (bar_ts // bar_seconds) * bar_seconds
                    bar_start_dt = datetime.fromtimestamp(bar_ts, tz=UTC)
                    slug = _build_1h_slug(asset, bar_start_dt)
                else:
                    slug_prefix = _SLUG_ASSET.get(asset)
                    if slug_prefix:
                        bar_start = int(entry_time.timestamp())
                        bar_start = (bar_start // bar_seconds) * bar_seconds
                        slug = f"{slug_prefix}-updown-{tf_suffix}-{bar_start}"
                if slug:
                    self._slug_cache[condition_id] = slug
        if not slug:
            logger.debug("No slug for %s", condition_id[:16])
            return None

        try:
            connector = self._connector_factory() if self._connector_factory else None
            async with aiohttp.ClientSession(
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as session, session.get(
                GAMMA_API_URL, params={"slug": slug},
            ) as resp:
                if resp.status != 200:
                    return None
                markets = await resp.json()
                if not markets:
                    return None

                m = markets[0]
                # Translate to resolution format expected by resolution_monitor
                closed = m.get("closed", False)
                if not closed:
                    return m

                # Determine outcome from outcomePrices
                outcomes_raw = m.get("outcomes", "[]")
                prices_raw = m.get("outcomePrices", "[]")
                try:
                    outcomes = (
                        json.loads(outcomes_raw) if isinstance(outcomes_raw, str)
                        else outcomes_raw
                    )
                    prices = (
                        json.loads(prices_raw) if isinstance(prices_raw, str)
                        else prices_raw
                    )
                except (json.JSONDecodeError, TypeError):
                    return m

                # outcomePrices=["1","0"] means first outcome won
                outcome = None
                for i, p in enumerate(prices):
                    if float(p) >= 0.99:
                        outcome = outcomes[i] if i < len(outcomes) else None
                        break

                if outcome:
                    m["resolved"] = True
                    m["outcome"] = outcome
                else:
                    m["resolved"] = closed  # closed but no clear winner?

                return m
        except Exception:
            logger.debug("Failed to check market status for slug=%s", slug)
        return None

    async def _discover(self) -> list[PolymarketMarket]:
        """Query Gamma API for current + next bar markets by slug.

        Checks both the current bar and the next bar, since Polymarket
        creates markets ahead of time. Returns the one with most time left.
        """
        tf_cfg = _TF_CONFIG.get(self._timeframe)
        if tf_cfg is None:
            return []

        tf_suffix, bar_seconds, market_type = tf_cfg
        current_bar = _current_bar_start(bar_seconds)
        next_bar = current_bar + bar_seconds
        now = datetime.now(UTC)

        matched: list[PolymarketMarket] = []

        connector = self._connector_factory() if self._connector_factory else None
        async with aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as session:
            for asset in self._assets:
                slug_prefix = _SLUG_ASSET.get(asset)
                if slug_prefix is None:
                    continue

                best: PolymarketMarket | None = None
                best_slug = ""

                # Try current bar first, then next bar.
                # Prefer current bar when it still has enough time.
                for bar_start in (current_bar, next_bar):
                    if self._timeframe == Timeframe.H1:
                        bar_start_dt = datetime.fromtimestamp(bar_start, tz=UTC)
                        slug = _build_1h_slug(asset, bar_start_dt)
                    else:
                        slug = f"{slug_prefix}-updown-{tf_suffix}-{bar_start}"

                    try:
                        async with session.get(
                            GAMMA_API_URL, params={"slug": slug},
                        ) as resp:
                            if resp.status != 200:
                                continue
                            results = await resp.json()
                    except Exception:
                        logger.debug("Gamma API query failed for slug=%s", slug)
                        continue

                    if not results:
                        continue

                    m = results[0]
                    if not m.get("active", False) or m.get("closed", True):
                        continue

                    # Check time remaining
                    end_str = m.get("endDate", "")
                    remaining = 0.0
                    if end_str:
                        try:
                            window_end = datetime.fromisoformat(
                                end_str.replace("Z", "+00:00"),
                            )
                            remaining = (window_end - now).total_seconds()
                        except (ValueError, TypeError):
                            pass

                    if remaining < self._min_time_remaining:
                        continue

                    market = _parse_market(m, asset, market_type)
                    if market is not None:
                        best = market
                        best_slug = slug
                        # Current bar found with enough time — use it,
                        # don't check next bar
                        break

                if best is not None:
                    matched.append(best)
                    self._slug_cache[best.condition_id] = best_slug

        if matched:
            logger.info(
                "Discovered %d markets: %s",
                len(matched),
                ", ".join(f"{m.asset.value}@{m.mid_up:.3f}" for m in matched),
            )
        return matched
