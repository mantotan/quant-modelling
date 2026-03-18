"""Performance metrics for backtest evaluation."""

from __future__ import annotations

import numpy as np


def sharpe_ratio(returns: np.ndarray, annualization: float = 105_000) -> float:
    """Annualized Sharpe ratio. Default assumes 5-min bars (~105k/year)."""
    if len(returns) < 2:
        return 0.0
    mean = returns.mean()
    std = returns.std()
    if std < 1e-10:
        return 0.0
    return float(mean / std * np.sqrt(min(len(returns), annualization)))


def sortino_ratio(returns: np.ndarray, annualization: float = 105_000) -> float:
    """Annualized Sortino ratio (downside deviation only)."""
    if len(returns) < 2:
        return 0.0
    downside = returns[returns < 0]
    if len(downside) < 2:
        return float("inf") if returns.mean() > 0 else 0.0
    dd_std = downside.std()
    if dd_std < 1e-10:
        return 0.0
    return float(returns.mean() / dd_std * np.sqrt(min(len(returns), annualization)))


def max_drawdown(cumulative_pnl: np.ndarray) -> float:
    """Maximum drawdown from peak cumulative PnL."""
    if len(cumulative_pnl) == 0:
        return 0.0
    peak = np.maximum.accumulate(cumulative_pnl)
    dd = peak - cumulative_pnl
    return float(dd.max())


def calmar_ratio(cumulative_pnl: np.ndarray) -> float:
    """Total return / max drawdown."""
    mdd = max_drawdown(cumulative_pnl)
    if mdd < 1e-10:
        return 0.0
    total_return = cumulative_pnl[-1] if len(cumulative_pnl) > 0 else 0.0
    return float(total_return / mdd)


def win_rate(trade_pnls: np.ndarray) -> float:
    """Fraction of profitable trades."""
    if len(trade_pnls) == 0:
        return 0.0
    return float((trade_pnls > 0).mean())


def profit_factor(trade_pnls: np.ndarray) -> float:
    """Sum of wins / sum of losses."""
    wins = trade_pnls[trade_pnls > 0].sum()
    losses = abs(trade_pnls[trade_pnls < 0].sum())
    if losses < 1e-10:
        return float("inf") if wins > 0 else 0.0
    return float(wins / losses)
