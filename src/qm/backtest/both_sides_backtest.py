"""Both-sides limit order backtester (trader_a-style market making).

Places limit orders on BOTH Up and Down sides simultaneously.
Profits when the market fills orders at prices cheaper than fair value.

Key insight from trader_a trader analysis:
- 87% of windows: trades BOTH Up and Down
- 25.8 trades/window average
- Buys at mid-range prices (0.30-0.50)
- 100% maker (limit orders, 0% fees)
"""

from __future__ import annotations

import logging
from collections import defaultdict

import numpy as np

from qm.core.constants import BARS_PER_YEAR
from qm.core.types import Timeframe

logger = logging.getLogger(__name__)


class BothSidesBacktester:
    """Backtests a both-sides limit order strategy.

    For each intra-bar snapshot:
    - Computes limit prices for Up and Down based on model probability
    - Fills limit orders when market price crosses the limit
    - Settles all positions at bar resolution

    In Polymarket:
    - market_prob = price of an Up share
    - (1 - market_prob) = price of a Down share
    - Up share pays $1 if target=1, $0 otherwise
    - Down share pays $1 if target=0, $0 otherwise
    """

    def __init__(
        self,
        margin: float = 0.03,
        fixed_bet_usd: float = 100.0,
        max_trades_per_bar: int = 26,
        fee_bps: float = 0.0,
        timeframe: Timeframe = Timeframe.M5,
    ) -> None:
        self._margin = margin
        self._fixed_bet_usd = fixed_bet_usd
        self._max_trades_per_bar = max_trades_per_bar
        self._fee_bps = fee_bps
        self._annualization = BARS_PER_YEAR[timeframe]
        self._total_seconds = float({
            Timeframe.M1: 60, Timeframe.M5: 300,
            Timeframe.M15: 900, Timeframe.H1: 3600,
        }[timeframe])

    def evaluate_fast(
        self,
        model_probs: np.ndarray,
        targets: np.ndarray,
        market_probs: np.ndarray,
        time_pcts: np.ndarray,
        bar_indices: np.ndarray,
    ) -> dict[str, object]:
        """Fast evaluation: iterate bar-by-bar, fill limit orders."""
        n = len(model_probs)
        if n == 0:
            return self._empty_metrics()

        # Group samples by bar
        bar_groups: dict[int, list[int]] = defaultdict(list)
        for i in range(n):
            bar_groups[int(bar_indices[i])].append(i)

        bar_pnls = []
        total_trades = 0
        total_wins = 0

        for bar_idx in sorted(bar_groups.keys()):
            indices = bar_groups[bar_idx]
            # Sort by time_pct (chronological within bar)
            indices.sort(key=lambda i: time_pcts[i])

            target = targets[indices[0]]  # same for all samples in bar
            bar_up_cost = 0.0  # total cost of Up shares bought
            bar_down_cost = 0.0  # total cost of Down shares bought
            bar_up_shares = 0.0
            bar_down_shares = 0.0
            trades_this_bar = 0

            for i in indices:
                if trades_this_bar >= self._max_trades_per_bar:
                    break

                mp = model_probs[i]
                mkt = market_probs[i]

                # Limit prices: buy only if market offers cheaper than model estimate
                up_limit = mp - self._margin
                down_limit = (1.0 - mp) - self._margin

                up_market_price = mkt
                down_market_price = 1.0 - mkt

                # Check Up fill
                up_filled = (up_limit > 0.01) and (up_market_price <= up_limit)
                # Check Down fill
                down_filled = (down_limit > 0.01) and (down_market_price <= down_limit)

                # Safety: if both would fill, check combined cost < 1.0
                if up_filled and down_filled:
                    if up_market_price + down_market_price >= 1.0:
                        # Can't profit from arb — skip both
                        up_filled = False
                        down_filled = False

                elapsed_s = time_pcts[i] * self._total_seconds

                if up_filled:
                    fill_price = up_market_price
                    shares = self._fixed_bet_usd / max(fill_price, 0.01)
                    bar_up_cost += self._fixed_bet_usd
                    bar_up_shares += shares
                    trades_this_bar += 1

                if down_filled:
                    fill_price = down_market_price
                    shares = self._fixed_bet_usd / max(fill_price, 0.01)
                    bar_down_cost += self._fixed_bet_usd
                    bar_down_shares += shares
                    trades_this_bar += 1

            # Settlement at bar end
            if trades_this_bar == 0:
                continue

            # Up shares pay $1 if target=1, Down shares pay $1 if target=0
            up_payout = bar_up_shares * (1.0 if target == 1 else 0.0)
            down_payout = bar_down_shares * (1.0 if target == 0 else 0.0)

            gross_pnl = (up_payout + down_payout) - (bar_up_cost + bar_down_cost)

            # Fee on winnings only
            winnings = max(0.0, up_payout - bar_up_cost) + max(0.0, down_payout - bar_down_cost)
            fee = winnings * (self._fee_bps / 10_000)
            net_pnl = gross_pnl - fee

            bar_pnls.append(net_pnl)
            total_trades += trades_this_bar
            if net_pnl > 0:
                total_wins += 1

        if not bar_pnls:
            return self._empty_metrics()

        pnl_arr = np.array(bar_pnls)
        cum_pnl = np.cumsum(pnl_arr)
        peak = np.maximum.accumulate(cum_pnl)
        max_dd = float((peak - cum_pnl).max())

        pnl_std = pnl_arr.std()
        sharpe = float(
            pnl_arr.mean() / (pnl_std + 1e-10) * np.sqrt(self._annualization)
        )

        brier = float(np.mean((model_probs - targets) ** 2))
        accuracy = float(np.mean((model_probs > 0.5) == (targets == 1)))

        return {
            "sharpe": sharpe,
            "brier": brier,
            "accuracy": accuracy,
            "total_pnl": float(cum_pnl[-1]),
            "max_dd": max_dd,
            "n_trades": total_trades,
            "n_bars_traded": len(bar_pnls),
            "win_rate": float(total_wins / len(bar_pnls)),
            "avg_pnl_per_trade": float(pnl_arr.sum() / total_trades),
            "avg_pnl_per_bar": float(pnl_arr.mean()),
            "time_buckets": {},
        }

    @staticmethod
    def _empty_metrics() -> dict[str, object]:
        return {
            "sharpe": 0.0, "brier": 0.25, "accuracy": 0.5,
            "total_pnl": 0.0, "max_dd": 0.0, "n_trades": 0,
            "n_bars_traded": 0,
            "win_rate": 0.0, "avg_pnl_per_trade": 0.0,
            "avg_pnl_per_bar": 0.0,
            "time_buckets": {},
        }
