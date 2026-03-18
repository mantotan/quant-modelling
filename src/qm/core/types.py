"""Core domain types used across the entire system."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Asset(str, Enum):
    BTC = "BTC"
    ETH = "ETH"
    XRP = "XRP"
    SOL = "SOL"


class Timeframe(str, Enum):
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    H1 = "1h"


class MarketType(str, Enum):
    ONE_MIN = "1m"
    FIVE_MIN = "5m"
    FIFTEEN_MIN = "15m"
    MONTHLY = "monthly"


class RegimeState(int, Enum):
    """Market volatility regime, matching regime_vol_state feature values."""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRISIS = 3


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class Outcome(str, Enum):
    UP = "Up"
    DOWN = "Down"


@dataclass(frozen=True, slots=True)
class Bar:
    timestamp: datetime
    asset: Asset
    timeframe: Timeframe
    open: float
    high: float
    low: float
    close: float
    volume: float
    trade_count: int
    vwap: float


@dataclass(frozen=True, slots=True)
class PartialBar:
    """Snapshot of an in-progress bar, updated on every tick.

    Frozen -- it's a point-in-time snapshot, not a live-updating object.
    Elapsed/remaining are computed at snapshot time.
    """

    window_start: datetime
    window_end: datetime
    asset: Asset
    timeframe: Timeframe
    open: float
    high_so_far: float
    low_so_far: float
    current_price: float  # latest trade price (NOT final close)
    volume_so_far: float
    trade_count: int
    elapsed_seconds: float  # seconds since window_start
    remaining_seconds: float  # seconds until window_end


@dataclass(frozen=True, slots=True)
class Signal:
    timestamp: datetime
    asset: Asset
    market_type: MarketType
    model_prob_up: float  # calibrated P(Up)
    market_prob_up: float  # Polymarket implied P(Up)
    edge: float  # model_prob - market_prob (after spread)
    confidence: float  # meta-model confidence or distance from 0.5
    recommended_side: Outcome
    recommended_size: float  # Kelly-sized position in USDC


@dataclass(frozen=True, slots=True)
class PolymarketOrder:
    token_id: str
    condition_id: str
    side: Side
    price: float  # 0.01 - 0.99
    size: float  # shares
    order_type: str  # GTC, FOK


@dataclass(frozen=True, slots=True)
class PolymarketMarket:
    condition_id: str
    token_id_up: str
    token_id_down: str
    asset: Asset
    market_type: MarketType
    window_start: datetime
    window_end: datetime
    mid_up: float
    spread: float
    volume: float
