"""Dual-mode backtesting engine.

Mode 1 (evaluate_model_fast): Vectorized PnL calculation for Optuna HPO.
  - No order simulation, no portfolio tracking
  - Returns aggregate metrics (Sharpe, Brier, accuracy)
  - Used inside the training loop, called thousands of times

Mode 2 (run_full_simulation): Event-driven simulation for final validation.
  - Realistic order fills, spread, portfolio tracking
  - Detailed per-trade log for analysis
  - Used once after training for acceptance testing
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import polars as pl

from qm.core.constants import BARS_PER_YEAR
from qm.core.types import Timeframe

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    """Full backtest output."""

    pnl_series: np.ndarray  # cumulative PnL at each decision point
    trade_log: list[dict[str, object]] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    n_trades: int = 0


class BacktestEngine:
    """Dual-mode backtesting engine for Polymarket prediction strategies.

    For Polymarket binary markets:
    - We bet on "Up" or "Down" at the market price (probability)
    - If correct: we receive $1 per share (profit = 1 - price_paid)
    - If wrong: we lose the price_paid per share
    - Edge = model_prob - market_prob (after spread adjustment)
    """

    def __init__(
        self,
        fee_bps: float = 0.0,
        spread: float = 0.02,
        min_edge: float = 0.05,
        timeframe: Timeframe = Timeframe.M5,
    ) -> None:
        self._fee_bps = fee_bps
        self._spread = spread
        self._min_edge = min_edge
        self._annualization = BARS_PER_YEAR[timeframe]

    def evaluate_model_fast(
        self,
        model_probs: np.ndarray,
        targets: np.ndarray,
        market_probs: np.ndarray | None = None,
        kelly_fraction: float = 0.25,
        max_bet_frac: float = 0.05,
    ) -> dict[str, float]:
        """Fast vectorized evaluation for HPO objective function.

        Args:
            model_probs: Calibrated P(Up) from model, shape (n,)
            targets: Actual outcomes (1=Up, 0=Down), shape (n,)
            market_probs: Polymarket implied P(Up). If None, uses 0.5
            kelly_fraction: Fraction of Kelly for sizing
            max_bet_frac: Max fraction of bankroll per bet

        Returns:
            Dict with keys: sharpe, brier, accuracy, total_pnl, max_dd,
                            n_trades, win_rate, avg_edge
        """
        n = len(model_probs)
        if n == 0:
            return self._empty_metrics()

        if market_probs is None:
            market_probs = np.full(n, 0.5)

        # Calculate edge for both sides
        edge_up = model_probs - market_probs - self._spread / 2
        edge_down = (1 - model_probs) - (1 - market_probs) - self._spread / 2

        # Choose best side
        bet_up = edge_up > edge_down
        edge = np.where(bet_up, edge_up, edge_down)

        # Only trade when edge exceeds minimum
        tradeable = edge >= self._min_edge

        if not tradeable.any():
            return self._empty_metrics()

        # Kelly sizing (simplified)
        buy_price = np.where(bet_up, market_probs, 1 - market_probs)
        buy_price = np.clip(buy_price, 0.01, 0.99)
        kelly_f = edge / (1 - buy_price)
        bet_size = np.clip(kelly_f * kelly_fraction, 0, max_bet_frac)

        # PnL calculation
        # If we bet on Up and target=1: profit = (1 - buy_price) * size
        # If we bet on Up and target=0: loss = -buy_price * size
        correct = np.where(bet_up, targets == 1, targets == 0)
        pnl_per_bet = np.where(
            correct,
            (1 - buy_price) * bet_size,
            -buy_price * bet_size,
        )

        # Apply trading filter
        pnl_per_bet = np.where(tradeable, pnl_per_bet, 0)
        bet_size = np.where(tradeable, bet_size, 0)

        # Fee
        fee_cost = buy_price * bet_size * (self._fee_bps / 10_000)
        pnl_per_bet -= np.where(tradeable, fee_cost, 0)

        # Cumulative PnL
        cum_pnl = np.cumsum(pnl_per_bet)

        # Metrics
        traded = tradeable & (bet_size > 0)
        n_trades = int(traded.sum())

        if n_trades == 0:
            return self._empty_metrics()

        traded_pnl = pnl_per_bet[traded]
        win_rate = float((traded_pnl > 0).mean())

        # Sharpe (annualized)
        pnl_std = traded_pnl.std()
        sharpe = float(traded_pnl.mean() / (pnl_std + 1e-10) * np.sqrt(self._annualization))

        # Max drawdown on cumulative PnL
        peak = np.maximum.accumulate(cum_pnl)
        drawdown = peak - cum_pnl
        max_dd = float(drawdown.max()) if len(drawdown) > 0 else 0.0

        # Brier score (on all predictions, not just traded)
        brier = float(np.mean((model_probs - targets) ** 2))

        # Accuracy (overall directional accuracy)
        predicted_up = model_probs > 0.5
        accuracy = float(np.mean(predicted_up == (targets == 1)))

        # Sortino (downside deviation)
        negative_pnls = traded_pnl[traded_pnl < 0]
        downside_std = negative_pnls.std() if len(negative_pnls) > 1 else 1e-10
        sortino = float(traded_pnl.mean() / (downside_std + 1e-10) * np.sqrt(self._annualization))

        # Calmar
        calmar = float(cum_pnl[-1] / (max_dd + 1e-10)) if max_dd > 0 else 0.0

        return {
            "sharpe": sharpe,
            "sortino": sortino,
            "calmar": calmar,
            "brier": brier,
            "accuracy": accuracy,
            "total_pnl": float(cum_pnl[-1]),
            "max_dd": max_dd,
            "n_trades": n_trades,
            "win_rate": win_rate,
            "avg_pnl_per_trade": float(traded_pnl.mean()),
        }

    def run_full_simulation(
        self,
        model_probs: np.ndarray,
        targets: np.ndarray,
        timestamps: np.ndarray,
        market_probs: np.ndarray | None = None,
        initial_bankroll: float = 10_000.0,
        kelly_fraction: float = 0.25,
        max_bet_usd: float = 500.0,
        min_bet_usd: float = 5.0,
    ) -> BacktestResult:
        """Full event-driven simulation with portfolio tracking.

        Simulates placing bets on Polymarket, tracking bankroll, positions,
        and generating a detailed trade log.
        """
        n = len(model_probs)
        if market_probs is None:
            market_probs = np.full(n, 0.5)

        bankroll = initial_bankroll
        pnl_series = np.zeros(n)
        trade_log: list[dict[str, object]] = []
        cum_pnl = 0.0

        for i in range(n):
            mp = model_probs[i]
            mkt = market_probs[i]
            target = targets[i]

            # Edge calculation
            edge_up = mp - mkt - self._spread / 2
            edge_down = (1 - mp) - (1 - mkt) - self._spread / 2

            bet_up = edge_up > edge_down
            edge = edge_up if bet_up else edge_down

            if edge < self._min_edge:
                pnl_series[i] = cum_pnl
                continue

            # Kelly sizing on current bankroll
            buy_price = mkt if bet_up else (1 - mkt)
            buy_price = max(0.01, min(0.99, buy_price))
            kelly_f = edge / (1 - buy_price)
            bet_frac = min(kelly_f * kelly_fraction, 0.05)
            bet_usd = max(0.0, min(bet_frac * bankroll, max_bet_usd))

            if bet_usd < min_bet_usd:
                pnl_series[i] = cum_pnl
                continue

            # Simulate fill (pessimistic: cross the spread)
            fill_price = buy_price + self._spread / 2
            fill_price = max(0.01, min(0.99, fill_price))
            shares = bet_usd / fill_price

            # Fee
            fee = bet_usd * (self._fee_bps / 10_000)

            # Resolution
            correct = (bet_up and target == 1) or (not bet_up and target == 0)
            if correct:
                pnl = shares * (1 - fill_price) - fee  # win: receive $1/share
            else:
                pnl = -shares * fill_price - fee  # lose: lose cost

            bankroll += pnl
            cum_pnl += pnl
            pnl_series[i] = cum_pnl

            trade_log.append({
                "timestamp": timestamps[i] if i < len(timestamps) else i,
                "side": "Up" if bet_up else "Down",
                "model_prob": float(mp),
                "market_prob": float(mkt),
                "edge": float(edge),
                "bet_usd": float(bet_usd),
                "fill_price": float(fill_price),
                "correct": correct,
                "pnl": float(pnl),
                "bankroll": float(bankroll),
            })

            # Circuit breaker: stop if bankroll drops below 10% of initial
            if bankroll < initial_bankroll * 0.10:
                logger.warning("Backtest circuit breaker: bankroll < 10% of initial")
                pnl_series[i:] = cum_pnl
                break

        # Compute final metrics
        result = BacktestResult(
            pnl_series=pnl_series,
            trade_log=trade_log,
            n_trades=len(trade_log),
        )
        result.metrics = self._compute_metrics(pnl_series, model_probs, targets, trade_log)
        return result

    def _compute_metrics(
        self,
        pnl_series: np.ndarray,
        model_probs: np.ndarray,
        targets: np.ndarray,
        trade_log: list[dict[str, object]],
    ) -> dict[str, float]:
        """Compute comprehensive backtest metrics."""
        if not trade_log:
            return self._empty_metrics()

        trade_pnls = np.array([t["pnl"] for t in trade_log])
        n_trades = len(trade_pnls)

        # Win rate
        win_rate = float((trade_pnls > 0).mean())

        # Sharpe
        pnl_std = trade_pnls.std()
        sharpe = float(trade_pnls.mean() / (pnl_std + 1e-10) * np.sqrt(self._annualization))

        # Max drawdown
        peak = np.maximum.accumulate(pnl_series)
        drawdown = peak - pnl_series
        max_dd = float(drawdown.max())

        # Brier score
        brier = float(np.mean((model_probs - targets) ** 2))

        # Accuracy
        accuracy = float(np.mean((model_probs > 0.5) == (targets == 1)))

        # Sortino (downside deviation)
        negative_pnls = trade_pnls[trade_pnls < 0]
        downside_std = negative_pnls.std() if len(negative_pnls) > 0 else 1e-10
        sortino = float(trade_pnls.mean() / (downside_std + 1e-10) * np.sqrt(self._annualization))

        # Calmar
        calmar = float(pnl_series[-1] / (max_dd + 1e-10)) if max_dd > 0 else 0.0

        return {
            "sharpe": sharpe,
            "sortino": sortino,
            "calmar": calmar,
            "brier": brier,
            "accuracy": accuracy,
            "total_pnl": float(pnl_series[-1]),
            "max_dd": max_dd,
            "n_trades": n_trades,
            "win_rate": win_rate,
            "avg_pnl_per_trade": float(trade_pnls.mean()),
        }

    @staticmethod
    def _empty_metrics() -> dict[str, float]:
        return {
            "sharpe": 0.0, "sortino": 0.0, "calmar": 0.0,
            "brier": 0.25, "accuracy": 0.5,
            "total_pnl": 0.0, "max_dd": 0.0, "n_trades": 0,
            "win_rate": 0.0, "avg_pnl_per_trade": 0.0,
        }
