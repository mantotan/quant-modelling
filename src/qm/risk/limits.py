"""Individual risk limit checks.

Each check is a pure function: (signal, size, portfolio_state) → (pass, reason).
The RiskManager chains these in order.
"""

from __future__ import annotations

from qm.core.types import Asset, RegimeState, Signal
from qm.risk.bankroll import Bankroll

# Default asset correlations (hardcoded, can be overridden via config)
ASSET_CORRELATIONS: dict[tuple[Asset, Asset], float] = {
    (Asset.BTC, Asset.ETH): 0.85,
    (Asset.BTC, Asset.SOL): 0.75,
    (Asset.BTC, Asset.XRP): 0.65,
    (Asset.ETH, Asset.SOL): 0.80,
    (Asset.ETH, Asset.XRP): 0.60,
    (Asset.SOL, Asset.XRP): 0.55,
}

# Correlation multipliers per regime — crisis drives correlations toward 1.0
_REGIME_CORR_MULTIPLIER: dict[RegimeState, float] = {
    RegimeState.LOW: 0.90,     # slightly lower in calm markets
    RegimeState.NORMAL: 1.00,  # baseline
    RegimeState.HIGH: 1.10,    # tighter in volatile markets
    RegimeState.CRISIS: 1.25,  # near-1.0 correlations in panic
}


def get_regime_correlations(
    regime: RegimeState,
) -> dict[tuple[Asset, Asset], float]:
    """Return asset correlations adjusted for the current regime.

    In crisis regimes, correlations increase (everything sells together).
    In low-vol regimes, correlations decrease slightly.
    Correlations are clamped to [0, 1].
    """
    multiplier = _REGIME_CORR_MULTIPLIER.get(regime, 1.0)
    return {
        pair: min(1.0, corr * multiplier)
        for pair, corr in ASSET_CORRELATIONS.items()
    }


def check_concurrent_limit(
    open_position_count: int, max_concurrent: int
) -> tuple[bool, str]:
    """Reject if too many concurrent bets."""
    if open_position_count >= max_concurrent:
        return False, f"concurrent_limit: {open_position_count}/{max_concurrent}"
    return True, ""


def check_single_bet_size(
    size_usd: float, bankroll: Bankroll, max_pct: float
) -> tuple[bool, str]:
    """Reject if single bet exceeds % of bankroll."""
    max_allowed = bankroll.current * max_pct
    if size_usd > max_allowed:
        return False, f"single_bet_size: ${size_usd:.0f} > {max_pct*100:.0f}% of ${bankroll.current:.0f}"
    return True, ""


def check_daily_loss(bankroll: Bankroll, max_daily_loss_pct: float) -> tuple[bool, str]:
    """Reject if daily loss exceeds threshold."""
    if bankroll.daily_loss_pct >= max_daily_loss_pct:
        return False, f"daily_loss: {bankroll.daily_loss_pct:.1%} >= {max_daily_loss_pct:.1%}"
    return True, ""


def check_drawdown(bankroll: Bankroll, max_drawdown_pct: float) -> tuple[bool, str]:
    """Reject if drawdown from HWM exceeds threshold."""
    if bankroll.drawdown >= max_drawdown_pct:
        return False, f"drawdown: {bankroll.drawdown:.1%} >= {max_drawdown_pct:.1%}"
    return True, ""


def check_asset_concentration(
    signal_asset: Asset,
    size_usd: float,
    asset_exposures: dict[Asset, float],
    total_value: float,
    max_concentration: float,
) -> tuple[bool, str]:
    """Reject if too much capital in one asset."""
    current_exposure = asset_exposures.get(signal_asset, 0.0)
    new_exposure = current_exposure + size_usd
    if total_value > 0 and new_exposure / total_value > max_concentration:
        return False, f"asset_concentration: {signal_asset.value} {new_exposure/total_value:.1%} > {max_concentration:.1%}"
    return True, ""


def check_correlated_exposure(
    signal: Signal,
    size_usd: float,
    open_positions: list[dict],
    total_value: float,
    max_correlated: float,
    correlations: dict[tuple[Asset, Asset], float] | None = None,
) -> tuple[bool, str]:
    """Reject if correlated directional exposure is too high.

    BTC and ETH are highly correlated. Betting $500 Up on BTC and $500 Up on ETH
    is effectively ~$925 of correlated directional exposure (at 0.85 correlation).

    Args:
        correlations: Optional regime-adjusted correlations. Defaults to
            static ASSET_CORRELATIONS if not provided.
    """
    if total_value <= 0:
        return True, ""

    corr_table = correlations if correlations is not None else ASSET_CORRELATIONS

    corr_exposure = size_usd
    for pos in open_positions:
        pos_asset = pos.get("asset")
        pos_side = pos.get("side")
        pos_size = pos.get("size_usd", 0.0)

        if pos_asset is None:
            continue

        # Get correlation
        pair = tuple(sorted([signal.asset, pos_asset], key=lambda a: a.value))
        corr = corr_table.get(pair, 0.3)

        # Same direction amplifies risk
        same_direction = (
            (signal.recommended_side.value == "Up" and pos_side == "Up")
            or (signal.recommended_side.value == "Down" and pos_side == "Down")
        )

        if same_direction:
            corr_exposure += pos_size * corr
        else:
            corr_exposure -= pos_size * corr * 0.5  # partial offset

    if corr_exposure / total_value > max_correlated:
        return False, f"correlated_exposure: {corr_exposure/total_value:.1%} > {max_correlated:.1%}"
    return True, ""
