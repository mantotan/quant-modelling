"""System-wide constants."""

from qm.core.types import Asset, Timeframe

SUPPORTED_ASSETS: list[Asset] = [Asset.BTC, Asset.ETH, Asset.XRP, Asset.SOL]
SUPPORTED_TIMEFRAMES: list[Timeframe] = [Timeframe.M5, Timeframe.M15, Timeframe.H1]

# Polymarket
POLYMARKET_CHAIN_ID = 137  # Polygon mainnet
POLYMARKET_TZ = "America/New_York"

# Timeframe to minutes mapping
TIMEFRAME_MINUTES: dict[Timeframe, int] = {
    Timeframe.M5: 5,
    Timeframe.M15: 15,
    Timeframe.H1: 60,
}

# Exchange symbols mapping (ccxt format)
EXCHANGE_SYMBOLS: dict[Asset, str] = {
    Asset.BTC: "BTC/USDT",
    Asset.ETH: "ETH/USDT",
    Asset.XRP: "XRP/USDT",
    Asset.SOL: "SOL/USDT",
}
