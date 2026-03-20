"""Intra-bar backtester with realistic market friction.

Backtests the Pulse model across intra-bar snapshots with:
- Fees on winnings only (Polymarket 2% standard)
- Square-root market impact model
- Daily trade cap
- Dynamic market pricing via MarketOddsSimulator
- Time-segmented ROI reporting
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
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
    """Backtests the Pulse model with realistic market friction.

    Realistic defaults:
    - fee_bps=200: Polymarket 2% fee on winnings only
    - impact_bps=50: Square-root market impact model
    - max_daily_trades=100: Prevent unrealistic trade frequency
    - max_bet_frac=0.03: Conservative Kelly cap
    """

    def __init__(
        self,
        fee_bps: float = 200,
        spread: float = 0.02,
        min_edge: float = 0.02,
        max_elapsed_pct: float = 0.983,
        max_trades_per_bar: int = 3,
        kelly_fraction: float = 0.25,
        max_bet_frac: float = 0.03,
        timeframe: Timeframe = Timeframe.M5,
        impact_bps: float = 50,
        avg_daily_volume: float = 50_000.0,
        max_daily_trades: int = 100,
        fixed_bet_usd: float | None = None,
        trade_selection: str = "all",
    ) -> None:
        self._fee_bps = fee_bps
        self._spread = spread
        self._min_edge = min_edge
        self._max_elapsed_pct = max_elapsed_pct
        self._max_trades_per_bar = max_trades_per_bar
        self._kelly_fraction = kelly_fraction
        self._max_bet_frac = max_bet_frac
        self._annualization = BARS_PER_YEAR[timeframe]
        self._total_seconds = float({
            Timeframe.M1: 60, Timeframe.M5: 300,
            Timeframe.M15: 900, Timeframe.H1: 3600,
        }[timeframe])
        self._impact_bps = impact_bps
        self._avg_daily_volume = avg_daily_volume
        self._max_daily_trades = max_daily_trades
        self._fixed_bet_usd = fixed_bet_usd
        self._bars_per_day = int(86400 / self._total_seconds)
        self._trade_selection = trade_selection  # "all", "best_edge", "first_confident"

    def evaluate_fast(
        self,
        model_probs: np.ndarray,
        targets: np.ndarray,
        market_probs: np.ndarray,
        time_pcts: np.ndarray,
        bar_indices: np.ndarray,
    ) -> dict[str, object]:
        """Fast vectorized evaluation for HPO."""
        n = len(model_probs)
        if n == 0:
            return self._empty_metrics()

        valid = time_pcts <= self._max_elapsed_pct

        half_spread = self._spread / 2
        edge_up = model_probs - market_probs - half_spread
        edge_down = (1 - model_probs) - (1 - market_probs) - half_spread
        bet_up = edge_up > edge_down
        edge = np.where(bet_up, edge_up, edge_down)

        tradeable = valid & (edge >= self._min_edge)

        # Per-bar trade selection
        if self._trade_selection == "best_edge":
            # Two-pass: for each bar, keep only the sample with max edge
            tradeable = self._select_best_edge(tradeable, edge, bar_indices)
        elif self._trade_selection == "first_confident":
            # For each bar, keep the first sample (lowest time_pct) with edge >= min_edge
            tradeable = self._select_first_confident(tradeable, bar_indices)
        elif self._max_trades_per_bar < 10_000:
            # Legacy "all" mode with per-bar cap
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

        # Daily trade limiting
        if self._max_daily_trades < 10_000:
            daily_counts: dict[int, int] = {}
            for i in range(n):
                if not tradeable[i]:
                    continue
                day = int(bar_indices[i]) // self._bars_per_day
                count = daily_counts.get(day, 0)
                if count >= self._max_daily_trades:
                    tradeable[i] = False
                else:
                    daily_counts[day] = count + 1

        if not tradeable.any():
            return self._empty_metrics()

        # Bet sizing
        buy_price = np.where(bet_up, market_probs, 1 - market_probs)
        buy_price = np.clip(buy_price, 0.01, 0.99)
        if self._fixed_bet_usd is not None:
            # Fixed flat bet: normalize as fraction of $10K notional
            bet_size = np.where(tradeable, self._fixed_bet_usd / 10_000.0, 0)
        else:
            kelly_f = edge / (1 - buy_price)
            bet_size = np.clip(kelly_f * self._kelly_fraction, 0, self._max_bet_frac)

        # PnL
        correct = np.where(bet_up, targets == 1, targets == 0)
        gross_pnl = np.where(
            correct,
            (1 - buy_price) * bet_size,
            -buy_price * bet_size,
        )

        # Fee on WINNINGS ONLY (Polymarket model)
        gross_win = np.where(correct, (1 - buy_price) * bet_size, 0)
        fee = gross_win * (self._fee_bps / 10_000)
        pnl_per_bet = gross_pnl - np.where(tradeable, fee, 0)

        pnl_per_bet = np.where(tradeable, pnl_per_bet, 0)
        bet_size = np.where(tradeable, bet_size, 0)

        cum_pnl = np.cumsum(pnl_per_bet)

        traded = tradeable & (bet_size > 0)
        n_trades = int(traded.sum())
        if n_trades == 0:
            return self._empty_metrics()

        traded_pnl = pnl_per_bet[traded]

        # Aggregate to bar level for Sharpe, win_rate, max_dd
        # (same pattern as BothSidesBacktester.evaluate_fast)
        traded_bar_indices = bar_indices[traded]
        unique_traded_bars = np.unique(traded_bar_indices)
        bar_idx_local = np.searchsorted(unique_traded_bars, traded_bar_indices)
        bar_pnl = np.bincount(bar_idx_local, weights=traded_pnl,
                              minlength=len(unique_traded_bars))
        n_bars_traded = len(bar_pnl)

        # Bar-level metrics (correct annualization unit)
        win_rate = float((bar_pnl > 0).mean())
        bar_pnl_std = float(bar_pnl.std())
        sharpe = float(bar_pnl.mean() / (bar_pnl_std + 1e-10) * np.sqrt(self._annualization))

        # Bar-level drawdown (avoid intra-bar noise)
        bar_cum_pnl = np.cumsum(bar_pnl)
        bar_peak = np.maximum.accumulate(bar_cum_pnl)
        max_dd = float((bar_peak - bar_cum_pnl).max())

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
            "n_bars_traded": n_bars_traded,
            "win_rate": win_rate,
            "avg_pnl_per_trade": float(traded_pnl.mean()),
            "avg_pnl_per_bar": float(bar_pnl.mean()),
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
        """Full event-driven simulation with realistic friction."""
        n = len(model_probs)
        bankroll = initial_bankroll
        cum_pnl = 0.0
        pnl_series = np.zeros(n)
        trade_log: list[dict[str, object]] = []
        bar_trade_counts: dict[int, int] = {}
        daily_trade_counts: dict[int, int] = {}

        for i in range(n):
            if time_pcts[i] > self._max_elapsed_pct:
                pnl_series[i] = cum_pnl
                continue

            bi = int(bar_indices[i])
            if bar_trade_counts.get(bi, 0) >= self._max_trades_per_bar:
                pnl_series[i] = cum_pnl
                continue

            day_idx = bi // self._bars_per_day
            if daily_trade_counts.get(day_idx, 0) >= self._max_daily_trades:
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

            if self._fixed_bet_usd is not None:
                bet_usd = self._fixed_bet_usd
            else:
                kelly_f = edge / (1 - buy_price)
                bet_frac = min(kelly_f * self._kelly_fraction, self._max_bet_frac)
                bet_usd = max(0.0, min(bet_frac * bankroll, max_bet_usd))

            if bet_usd < min_bet_usd:
                pnl_series[i] = cum_pnl
                continue

            # Market impact: square-root model
            impact = (
                self._impact_bps / 10_000
                * math.sqrt(bet_usd / (self._avg_daily_volume + 1e-10))
            )
            fill_price = buy_price + half_spread + impact
            fill_price = max(0.01, min(0.99, fill_price))
            shares = bet_usd / fill_price

            target = targets[i]
            correct = (bet_up and target == 1) or (not bet_up and target == 0)

            # Fee on winnings only (Polymarket model)
            if correct:
                gross_pnl = shares * (1 - fill_price)
                fee = gross_pnl * (self._fee_bps / 10_000)
                pnl = gross_pnl - fee
            else:
                pnl = -shares * fill_price

            bankroll += pnl
            cum_pnl += pnl
            pnl_series[i] = cum_pnl

            bar_trade_counts[bi] = bar_trade_counts.get(bi, 0) + 1
            daily_trade_counts[day_idx] = daily_trade_counts.get(day_idx, 0) + 1

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
                "impact": float(impact),
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

        if trade_log:
            traded_pnls = np.array([t["pnl"] for t in trade_log])

            # Aggregate to bar level for Sharpe/win_rate
            bar_pnl_dict: dict[int, float] = defaultdict(float)
            for t in trade_log:
                bar_pnl_dict[t["bar_idx"]] += t["pnl"]
            bar_pnl_arr = np.array(list(bar_pnl_dict.values()))

            bar_pnl_std = float(bar_pnl_arr.std())
            result.metrics = {
                "total_pnl": float(cum_pnl),
                "n_trades": len(trade_log),
                "n_bars_traded": len(bar_pnl_arr),
                "win_rate": float((bar_pnl_arr > 0).mean()),
                "avg_pnl_per_trade": float(traded_pnls.mean()),
                "avg_pnl_per_bar": float(bar_pnl_arr.mean()),
                "sharpe": float(
                    bar_pnl_arr.mean() / (bar_pnl_std + 1e-10)
                    * np.sqrt(self._annualization)
                ),
            }

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
    def _select_best_edge(
        tradeable: np.ndarray, edge: np.ndarray, bar_indices: np.ndarray,
    ) -> np.ndarray:
        """For each bar, keep only the sample with the highest edge."""
        result = np.zeros_like(tradeable)
        tradeable_idx = np.where(tradeable)[0]
        if len(tradeable_idx) == 0:
            return result

        trade_bars = bar_indices[tradeable_idx]
        trade_edges = edge[tradeable_idx]

        unique_bars = np.unique(trade_bars)
        for bar in unique_bars:
            bar_mask = trade_bars == bar
            bar_positions = tradeable_idx[bar_mask]
            best_pos = bar_positions[np.argmax(trade_edges[bar_mask])]
            result[best_pos] = True

        return result

    @staticmethod
    def _select_first_confident(
        tradeable: np.ndarray, bar_indices: np.ndarray,
    ) -> np.ndarray:
        """For each bar, keep only the first tradeable sample (by dataset order = time order)."""
        result = np.zeros_like(tradeable)
        seen_bars: set[int] = set()
        for i in range(len(tradeable)):
            if not tradeable[i]:
                continue
            bi = int(bar_indices[i])
            if bi not in seen_bars:
                result[i] = True
                seen_bars.add(bi)
        return result

    @staticmethod
    def _empty_metrics() -> dict[str, object]:
        return {
            "sharpe": 0.0, "brier": 0.25, "accuracy": 0.5,
            "total_pnl": 0.0, "max_dd": 0.0, "n_trades": 0,
            "n_bars_traded": 0, "win_rate": 0.0,
            "avg_pnl_per_trade": 0.0, "avg_pnl_per_bar": 0.0,
            "time_buckets": {},
        }
