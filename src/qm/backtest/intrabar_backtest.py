"""Intra-bar backtester with dynamic market pricing.

Backtests the Pulse model across simulated intra-bar snapshots.
Uses MarketOddsSimulator for realistic market odds evolution.
Supports trading from first tick (no min_elapsed_pct).
Only skips last 5 seconds (resolution risk).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

from qm.core.constants import BARS_PER_YEAR
from qm.core.types import Timeframe

logger = logging.getLogger(__name__)

# Time bucket boundaries in seconds (for 5m bars)
TIME_BUCKETS = [
    ("0-30s", 0.0, 30.0),
    ("30-60s", 30.0, 60.0),
    ("60-120s", 60.0, 120.0),
    ("120-180s", 120.0, 180.0),
    ("180-295s", 180.0, 295.0),
]


@dataclass
class IntraBarBacktestResult:
    """Result from intra-bar backtesting."""

    pnl_series: np.ndarray
    trade_log: list[dict[str, object]] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    metrics_by_time_bucket: dict[str, dict[str, float]] = field(default_factory=dict)
    n_trades: int = 0


class IntraBarBacktester:
    """Backtests the Pulse model with dynamic market pricing.

    Key differences from BacktestEngine:
    - No min_elapsed_pct: trade from first tick
    - Dynamic market_prob at each snapshot (not static per bar)
    - max_trades_per_bar to prevent overtrading
    - Time-segmented reporting to validate early-bar ROI thesis
    """

    def __init__(
        self,
        fee_bps: float = 0.0,
        spread: float = 0.02,
        min_edge: float = 0.02,
        max_elapsed_pct: float = 0.983,
        max_trades_per_bar: int = 3,
        kelly_fraction: float = 0.25,
        max_bet_frac: float = 0.05,
        timeframe: Timeframe = Timeframe.M5,
    ) -> None:
        self._fee_bps = fee_bps
        self._spread = spread
        self._min_edge = min_edge
        self._max_elapsed_pct = max_elapsed_pct
        self._max_trades_per_bar = max_trades_per_bar
        self._kelly_fraction = kelly_fraction
        self._max_bet_frac = max_bet_frac
        self._annualization = BARS_PER_YEAR[timeframe]
        self._total_seconds = {
            Timeframe.M1: 60.0, Timeframe.M5: 300.0,
            Timeframe.M15: 900.0, Timeframe.H1: 3600.0,
        }[timeframe]

    def evaluate_fast(
        self,
        model_probs: np.ndarray,
        targets: np.ndarray,
        market_probs: np.ndarray,
        time_pcts: np.ndarray,
        bar_indices: np.ndarray,
    ) -> dict[str, float]:
        """Fast vectorized evaluation for HPO.

        Args:
            model_probs: Calibrated P(Up) from model, shape (n,).
            targets: Actual outcomes (1=Up, 0=Down), shape (n,).
            market_probs: Simulated market P(Up), shape (n,).
            time_pcts: Elapsed fraction per sample, shape (n,).
            bar_indices: Bar index per sample, shape (n,).

        Returns:
            Dict with aggregate metrics.
        """
        n = len(model_probs)
        if n == 0:
            return self._empty_metrics()

        # Filter: skip samples past max_elapsed_pct
        valid = time_pcts <= self._max_elapsed_pct

        # Edge calculation (both sides)
        half_spread = self._spread / 2
        edge_up = model_probs - market_probs - half_spread
        edge_down = (1 - model_probs) - (1 - market_probs) - half_spread
        bet_up = edge_up > edge_down
        edge = np.where(bet_up, edge_up, edge_down)

        tradeable = valid & (edge >= self._min_edge)

        # Per-bar trade limiting
        if self._max_trades_per_bar < 16:
            bar_trade_count: dict[int, int] = {}
            for i in range(n):
                if not tradeable[i]:
                    continue
                bi = int(bar_indices[i])
                count = bar_trade_count.get(bi, 0)
                if count >= self._max_trades_per_bar:
                    tradeable[i] = False
                else:
                    bar_trade_count[bi] = count + 1

        if not tradeable.any():
            return self._empty_metrics()

        # Kelly sizing
        buy_price = np.where(bet_up, market_probs, 1 - market_probs)
        buy_price = np.clip(buy_price, 0.01, 0.99)
        kelly_f = edge / (1 - buy_price)
        bet_size = np.clip(kelly_f * self._kelly_fraction, 0, self._max_bet_frac)

        # PnL
        correct = np.where(bet_up, targets == 1, targets == 0)
        pnl_per_bet = np.where(
            correct,
            (1 - buy_price) * bet_size,
            -buy_price * bet_size,
        )
        pnl_per_bet = np.where(tradeable, pnl_per_bet, 0)
        bet_size = np.where(tradeable, bet_size, 0)

        # Fee
        fee = buy_price * bet_size * (self._fee_bps / 10_000)
        pnl_per_bet -= np.where(tradeable, fee, 0)

        cum_pnl = np.cumsum(pnl_per_bet)

        traded = tradeable & (bet_size > 0)
        n_trades = int(traded.sum())
        if n_trades == 0:
            return self._empty_metrics()

        traded_pnl = pnl_per_bet[traded]
        win_rate = float((traded_pnl > 0).mean())
        pnl_std = traded_pnl.std()
        sharpe = float(traded_pnl.mean() / (pnl_std + 1e-10) * np.sqrt(self._annualization))

        peak = np.maximum.accumulate(cum_pnl)
        max_dd = float((peak - cum_pnl).max())

        brier = float(np.mean((model_probs - targets) ** 2))
        accuracy = float(np.mean((model_probs > 0.5) == (targets == 1)))

        # Time-segmented metrics
        time_bucket_metrics = {}
        elapsed_seconds = time_pcts * self._total_seconds
        for bucket_name, t_start, t_end in TIME_BUCKETS:
            bucket_mask = traded & (elapsed_seconds >= t_start) & (elapsed_seconds < t_end)
            bucket_n = int(bucket_mask.sum())
            if bucket_n > 0:
                bucket_pnl = pnl_per_bet[bucket_mask]
                bucket_buy = buy_price[bucket_mask]
                roi = float(bucket_pnl.mean() / (bucket_buy.mean() + 1e-10))
                time_bucket_metrics[bucket_name] = {
                    "n_trades": bucket_n,
                    "avg_pnl": float(bucket_pnl.mean()),
                    "roi_per_trade": roi,
                    "win_rate": float((bucket_pnl > 0).mean()),
                }
            else:
                time_bucket_metrics[bucket_name] = {
                    "n_trades": 0, "avg_pnl": 0.0,
                    "roi_per_trade": 0.0, "win_rate": 0.0,
                }

        return {
            "sharpe": sharpe,
            "brier": brier,
            "accuracy": accuracy,
            "total_pnl": float(cum_pnl[-1]),
            "max_dd": max_dd,
            "n_trades": n_trades,
            "win_rate": win_rate,
            "avg_pnl_per_trade": float(traded_pnl.mean()),
            "time_buckets": time_bucket_metrics,
        }

    def run_full(
        self,
        model_probs: np.ndarray,
        targets: np.ndarray,
        market_probs: np.ndarray,
        time_pcts: np.ndarray,
        bar_indices: np.ndarray,
        initial_bankroll: float = 10_000.0,
        max_bet_usd: float = 500.0,
        min_bet_usd: float = 5.0,
    ) -> IntraBarBacktestResult:
        """Full event-driven simulation with trade log.

        Used once after training for final validation.
        """
        n = len(model_probs)
        bankroll = initial_bankroll
        cum_pnl = 0.0
        pnl_series = np.zeros(n)
        trade_log: list[dict[str, object]] = []
        bar_trade_counts: dict[int, int] = {}

        for i in range(n):
            if time_pcts[i] > self._max_elapsed_pct:
                pnl_series[i] = cum_pnl
                continue

            bi = int(bar_indices[i])
            if bar_trade_counts.get(bi, 0) >= self._max_trades_per_bar:
                pnl_series[i] = cum_pnl
                continue

            mp = model_probs[i]
            mkt = market_probs[i]

            half_spread = self._spread / 2
            edge_up = mp - mkt - half_spread
            edge_down = (1 - mp) - (1 - mkt) - half_spread
            bet_up = edge_up > edge_down
            edge = edge_up if bet_up else edge_down

            if edge < self._min_edge:
                pnl_series[i] = cum_pnl
                continue

            buy_price = mkt if bet_up else (1 - mkt)
            buy_price = max(0.01, min(0.99, buy_price))
            kelly_f = edge / (1 - buy_price)
            bet_frac = min(kelly_f * self._kelly_fraction, self._max_bet_frac)
            bet_usd = max(0.0, min(bet_frac * bankroll, max_bet_usd))

            if bet_usd < min_bet_usd:
                pnl_series[i] = cum_pnl
                continue

            fill_price = buy_price + half_spread
            fill_price = max(0.01, min(0.99, fill_price))
            shares = bet_usd / fill_price
            fee = bet_usd * (self._fee_bps / 10_000)

            target = targets[i]
            correct = (bet_up and target == 1) or (not bet_up and target == 0)
            pnl = (shares * (1 - fill_price) - fee) if correct else (-shares * fill_price - fee)

            bankroll += pnl
            cum_pnl += pnl
            pnl_series[i] = cum_pnl

            bar_trade_counts[bi] = bar_trade_counts.get(bi, 0) + 1

            trade_log.append({
                "sample_idx": i,
                "bar_idx": bi,
                "time_pct": float(time_pcts[i]),
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

            if bankroll < initial_bankroll * 0.10:
                logger.warning("Intra-bar backtest circuit breaker triggered")
                pnl_series[i:] = cum_pnl
                break

        result = IntraBarBacktestResult(
            pnl_series=pnl_series,
            trade_log=trade_log,
            n_trades=len(trade_log),
        )

        # Compute metrics
        if trade_log:
            traded_pnls = np.array([t["pnl"] for t in trade_log])
            result.metrics = {
                "total_pnl": float(cum_pnl),
                "n_trades": len(trade_log),
                "win_rate": float((traded_pnls > 0).mean()),
                "avg_pnl_per_trade": float(traded_pnls.mean()),
                "sharpe": float(
                    traded_pnls.mean() / (traded_pnls.std() + 1e-10)
                    * np.sqrt(self._annualization)
                ),
            }

            # Time-segmented
            for bucket_name, t_start, t_end in TIME_BUCKETS:
                bucket_trades = [
                    t for t in trade_log
                    if t_start <= t["time_pct"] * self._total_seconds < t_end
                ]
                if bucket_trades:
                    bucket_pnls = np.array([t["pnl"] for t in bucket_trades])
                    bucket_buy = np.array([
                        t["market_prob"] if t["side"] == "Up"
                        else 1 - t["market_prob"]
                        for t in bucket_trades
                    ])
                    result.metrics_by_time_bucket[bucket_name] = {
                        "n_trades": len(bucket_trades),
                        "avg_pnl": float(bucket_pnls.mean()),
                        "roi_per_trade": float(
                            bucket_pnls.mean() / (bucket_buy.mean() + 1e-10)
                        ),
                        "win_rate": float((bucket_pnls > 0).mean()),
                    }
        else:
            result.metrics = self._empty_metrics()

        return result

    @staticmethod
    def _empty_metrics() -> dict[str, object]:
        return {
            "sharpe": 0.0, "brier": 0.25, "accuracy": 0.5,
            "total_pnl": 0.0, "max_dd": 0.0, "n_trades": 0,
            "win_rate": 0.0, "avg_pnl_per_trade": 0.0,
            "time_buckets": {},
        }
