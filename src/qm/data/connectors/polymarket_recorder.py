"""Polymarket odds recorder: polls Gamma API for live 5m market odds.

Records snapshots of Polymarket binary crypto markets (Up/Down) at
configurable intervals. Stores in TimescaleDB (production) or
Parquet fallback (dev without DB).

Usage:
    recorder = PolymarketOddsRecorder(parquet_dir=Path("data/raw/polymarket_snapshots"))
    await recorder.run()  # runs until stopped
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp
import polars as pl

from qm.core.constants import SUPPORTED_ASSETS
from qm.core.types import Asset
from qm.monitoring.metrics import (
    POLYMARKET_ACTIVE_MARKETS,
    POLYMARKET_RECORDER_ERRORS,
    POLYMARKET_SNAPSHOTS_RECORDED,
)

logger = logging.getLogger(__name__)

GAMMA_API_URL = "https://gamma-api.polymarket.com/markets"

# Asset keyword matching for market discovery
_ASSET_KEYWORDS: dict[Asset, list[str]] = {
    Asset.BTC: ["btc", "bitcoin"],
    Asset.ETH: ["eth", "ethereum"],
    Asset.SOL: ["sol", "solana"],
    Asset.XRP: ["xrp", "ripple"],
}


def _match_asset(question: str) -> Asset | None:
    """Match a Polymarket question string to an Asset."""
    q_lower = question.lower()
    for asset, keywords in _ASSET_KEYWORDS.items():
        if any(kw in q_lower for kw in keywords):
            return asset
    return None


def _is_binary_up_down(tokens: list[dict[str, Any]]) -> bool:
    """Check if market has Up/Down token structure."""
    outcomes = {t.get("outcome", "").lower() for t in tokens}
    return "up" in outcomes and "down" in outcomes


def _extract_token_ids(
    tokens: list[dict[str, Any]],
) -> tuple[str, str] | None:
    """Extract (token_id_up, token_id_down) from tokens list."""
    up_id = None
    down_id = None
    for t in tokens:
        outcome = t.get("outcome", "").lower()
        if outcome == "up":
            up_id = t.get("token_id", "")
        elif outcome == "down":
            down_id = t.get("token_id", "")
    if up_id and down_id:
        return up_id, down_id
    return None


def _extract_prices(
    tokens: list[dict[str, Any]],
) -> tuple[float | None, float | None]:
    """Extract (price_up, price_down) from tokens list."""
    price_up = None
    price_down = None
    for t in tokens:
        outcome = t.get("outcome", "").lower()
        price = t.get("price")
        if price is not None:
            try:
                price = float(price)
            except (ValueError, TypeError):
                continue
            if outcome == "up":
                price_up = price
            elif outcome == "down":
                price_down = price
    return price_up, price_down


def _is_short_duration_market(market: dict[str, Any], max_minutes: int = 60) -> bool:
    """Check if market window is short enough to be a 5m/15m/1h market."""
    try:
        end_str = market.get("end_date_iso", "")
        start_str = market.get("game_start_time", "") or market.get("start_date_iso", "")
        if not end_str:
            return False
        end = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
        if start_str:
            start = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
            duration_min = (end - start).total_seconds() / 60
            return 1 <= duration_min <= max_minutes
    except (ValueError, TypeError):
        pass
    # If we can't determine duration, check question for time hints
    question = market.get("question", "").lower()
    return bool(re.search(r"\b(5.?min|15.?min|1.?hour|5m|15m|1h)\b", question))


class PolymarketOddsRecorder:
    """Long-lived async service: discovers and records Polymarket odds.

    Supports two storage backends:
    - TimescaleDB (production): pass a TimescaleWriter instance
    - Parquet (dev fallback): pass a parquet_dir path

    At least one backend must be provided.
    """

    def __init__(
        self,
        timescale: Any | None = None,  # TimescaleWriter (avoid import for portability)
        parquet_dir: Path | None = None,
        poll_interval: float = 15.0,
        assets: list[Asset] | None = None,
        max_market_duration_min: int = 60,
    ) -> None:
        if timescale is None and parquet_dir is None:
            msg = "Provide either timescale or parquet_dir"
            raise ValueError(msg)
        self._timescale = timescale
        self._parquet_dir = parquet_dir
        self._poll_interval = poll_interval
        self._assets = set(assets or SUPPORTED_ASSETS)
        self._max_market_duration_min = max_market_duration_min
        self._running = False
        self._backoff_attempt = 0
        self._max_backoff = 60.0
        self._consecutive_errors = 0
        self._snapshot_count = 0
        self._parquet_buffer: list[dict[str, Any]] = []
        self._parquet_flush_interval = 60  # flush every N snapshots

    async def run(self) -> None:
        """Main recording loop. Runs until stop() is called or interrupted."""
        self._running = True
        logger.info(
            "Polymarket recorder started (poll=%.0fs, assets=%s, storage=%s)",
            self._poll_interval,
            [a.value for a in self._assets],
            "timescale" if self._timescale else f"parquet:{self._parquet_dir}",
        )

        async with aiohttp.ClientSession() as session:
            while self._running:
                try:
                    markets = await self._discover_markets(session)
                    POLYMARKET_ACTIVE_MARKETS.set(len(markets))

                    for market_data in markets:
                        await self._record_snapshot(market_data)

                    self._backoff_attempt = 0
                    self._consecutive_errors = 0

                except aiohttp.ClientError as e:
                    self._consecutive_errors += 1
                    POLYMARKET_RECORDER_ERRORS.labels(error_type="http").inc()
                    delay = self._backoff_seconds()
                    logger.warning(
                        "Recorder HTTP error (%d consecutive): %s. Backing off %.1fs",
                        self._consecutive_errors, e, delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                except Exception:
                    self._consecutive_errors += 1
                    POLYMARKET_RECORDER_ERRORS.labels(error_type="unknown").inc()
                    logger.exception("Recorder unexpected error")
                    await asyncio.sleep(self._backoff_seconds())
                    continue

                await asyncio.sleep(self._poll_interval)

        # Flush remaining buffer on shutdown
        if self._parquet_buffer:
            self._flush_parquet_buffer()

        logger.info(
            "Polymarket recorder stopped. Total snapshots: %d", self._snapshot_count,
        )

    def stop(self) -> None:
        self._running = False

    async def _discover_markets(
        self, session: aiohttp.ClientSession,
    ) -> list[dict[str, Any]]:
        """Query Gamma API and filter for relevant crypto binary markets."""
        async with session.get(
            GAMMA_API_URL,
            params={"active": "true", "closed": "false"},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            resp.raise_for_status()
            all_markets = await resp.json()

        matched = []
        for m in all_markets:
            tokens = m.get("tokens", [])
            if not _is_binary_up_down(tokens):
                continue

            asset = _match_asset(m.get("question", ""))
            if asset is None or asset not in self._assets:
                continue

            if not _is_short_duration_market(m, self._max_market_duration_min):
                continue

            token_ids = _extract_token_ids(tokens)
            if token_ids is None:
                continue

            m["_matched_asset"] = asset
            m["_token_id_up"] = token_ids[0]
            m["_token_id_down"] = token_ids[1]
            matched.append(m)

        return matched

    async def _record_snapshot(self, market_data: dict[str, Any]) -> None:
        """Record a single odds snapshot."""
        now = datetime.now(timezone.utc)
        tokens = market_data.get("tokens", [])
        price_up, price_down = _extract_prices(tokens)
        asset: Asset = market_data["_matched_asset"]

        snapshot = {
            "time": now,
            "condition_id": market_data.get("condition_id", ""),
            "token_id_up": market_data["_token_id_up"],
            "token_id_down": market_data["_token_id_down"],
            "asset": asset.value,
            "market_type": "5m",  # TODO: detect from duration
            "window_start": now,  # TODO: parse from market data
            "window_end": now,  # TODO: parse from market data
            "mid_up": price_up,
            "mid_down": price_down,
            "spread_up": None,  # TODO: compute from orderbook if available
            "volume": _safe_float(market_data.get("volume", 0)),
            "question": market_data.get("question", ""),
        }

        # Write to TimescaleDB
        if self._timescale is not None:
            try:
                await self._timescale.write_polymarket_snapshot(
                    time=snapshot["time"],
                    condition_id=snapshot["condition_id"],
                    token_id_up=snapshot["token_id_up"],
                    token_id_down=snapshot["token_id_down"],
                    asset=snapshot["asset"],
                    market_type=snapshot["market_type"],
                    window_start=snapshot["window_start"],
                    window_end=snapshot["window_end"],
                    mid_up=snapshot["mid_up"],
                    mid_down=snapshot["mid_down"],
                    spread_up=snapshot["spread_up"],
                    volume=snapshot["volume"],
                )
            except Exception:
                POLYMARKET_RECORDER_ERRORS.labels(error_type="db_write").inc()
                logger.exception("Failed to write snapshot to TimescaleDB")

        # Write to Parquet buffer (dev fallback or dual-write)
        if self._parquet_dir is not None:
            self._parquet_buffer.append(snapshot)
            if len(self._parquet_buffer) >= self._parquet_flush_interval:
                self._flush_parquet_buffer()

        self._snapshot_count += 1
        POLYMARKET_SNAPSHOTS_RECORDED.labels(asset=asset.value).inc()
        logger.debug(
            "Recorded %s mid_up=%.4f condition=%s",
            asset.value, price_up or 0, snapshot["condition_id"][:12],
        )

    def _flush_parquet_buffer(self) -> None:
        """Flush accumulated snapshots to Parquet files."""
        if not self._parquet_buffer or self._parquet_dir is None:
            return

        df = pl.DataFrame(self._parquet_buffer)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        out_dir = self._parquet_dir / f"date={today}"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "snapshots.parquet"

        if out_path.exists():
            existing = pl.read_parquet(out_path)
            df = pl.concat([existing, df])

        df.write_parquet(out_path)
        logger.info("Flushed %d snapshots to %s", len(self._parquet_buffer), out_path)
        self._parquet_buffer.clear()

    def _backoff_seconds(self) -> float:
        delay = min(2 ** self._backoff_attempt, self._max_backoff)
        self._backoff_attempt += 1
        return delay


def _safe_float(val: Any) -> float | None:
    """Safely convert to float, return None on failure."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
