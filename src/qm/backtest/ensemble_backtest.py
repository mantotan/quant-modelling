"""Ensemble backtester: evaluates Sentinel + Pulse combination.

Replays pre-computed predictions from both models in temporal order:
1. Sentinel predicts at bar open (static for entire bar)
2. Pulse predicts at each time_pct snapshot
3. CombinationStrategy combines them
4. Trading decision when ensemble edge exceeds threshold

Produces side-by-side comparison: Sentinel-alone vs Pulse-alone vs Ensemble.
"""

from __future__ import annotations

import logging
from enum import Enum

import numpy as np

from qm.backtest.intrabar_backtest import IntraBarBacktester
from qm.core.types import Timeframe
from qm.model.ensemble.predictor import (
    CombinationStrategy,
    combine_predictions_batch,
)

logger = logging.getLogger(__name__)


class DecisionMode(str, Enum):
    """When to trigger a trade within each bar."""

    FIRST_EDGE = "first_edge"  # Bet when ensemble edge first exceeds threshold
    MAX_EDGE = "max_edge"      # Wait for peak edge within bar, bet at end
    LATE_ONLY = "late_only"    # Only trade after time_pct >= 0.40


class EnsembleBacktester:
    """Joint backtest evaluating the Sentinel+Pulse ensemble.

    Accepts pre-computed calibrated predictions from both models.
    Uses the same market friction model as IntraBarBacktester for
    apples-to-apples comparison.
    """

    def __init__(
        self,
        fee_bps: float = 200,
        spread: float = 0.02,
        min_edge: float = 0.02,
        max_trades_per_bar: int = 3,
        impact_bps: float = 50,
        avg_daily_volume: float = 50_000.0,
        max_daily_trades: int = 100,
        fixed_bet_usd: float = 50.0,
        timeframe: Timeframe = Timeframe.M5,
    ) -> None:
        self._backtester = IntraBarBacktester(
            fee_bps=fee_bps,
            spread=spread,
            min_edge=min_edge,
            max_trades_per_bar=max_trades_per_bar,
            impact_bps=impact_bps,
            avg_daily_volume=avg_daily_volume,
            max_daily_trades=max_daily_trades,
            fixed_bet_usd=fixed_bet_usd,
            timeframe=timeframe,
        )

    def evaluate(
        self,
        sentinel_probs: np.ndarray,
        pulse_probs: np.ndarray,
        targets: np.ndarray,
        market_probs: np.ndarray,
        time_pcts: np.ndarray,
        bar_indices: np.ndarray,
        strategy: CombinationStrategy,
        decision_mode: DecisionMode = DecisionMode.FIRST_EDGE,
    ) -> dict[str, object]:
        """Evaluate ensemble and produce comparison metrics.

        Args:
            sentinel_probs: (n_bars,) calibrated Sentinel predictions, one per bar.
            pulse_probs: (n_samples,) calibrated Pulse predictions.
            targets: (n_samples,) binary targets (1=Up, 0=Down).
            market_probs: (n_samples,) market-implied P(Up).
            time_pcts: (n_samples,) elapsed fraction per sample.
            bar_indices: (n_samples,) which bar each sample belongs to.
            strategy: CombinationStrategy to use.
            decision_mode: When to trigger trades within each bar.

        Returns:
            Dict with keys: 'sentinel', 'pulse', 'ensemble' — each containing
            the same metrics dict from IntraBarBacktester.evaluate_fast().
        """
        n_samples = len(pulse_probs)
        if n_samples == 0:
            empty = self._backtester._empty_metrics()
            return {"sentinel": empty, "pulse": empty, "ensemble": empty}

        # 1. Sentinel-alone: expand bar-level probs to sample level
        sentinel_expanded = sentinel_probs[bar_indices]
        sentinel_metrics = self._backtester.evaluate_fast(
            sentinel_expanded, targets, market_probs, time_pcts, bar_indices,
        )

        # 2. Pulse-alone: as-is
        pulse_metrics = self._backtester.evaluate_fast(
            pulse_probs, targets, market_probs, time_pcts, bar_indices,
        )

        # 3. Ensemble: combine predictions
        ensemble_probs = combine_predictions_batch(
            sentinel_probs, pulse_probs, time_pcts, bar_indices,
            market_probs, strategy,
        )

        # Apply decision mode filtering
        if decision_mode == DecisionMode.LATE_ONLY:
            # Mask out early samples
            late_mask = time_pcts >= 0.40
            ensemble_probs_filtered = np.where(late_mask, ensemble_probs, 0.5)
        else:
            ensemble_probs_filtered = ensemble_probs

        ensemble_metrics = self._backtester.evaluate_fast(
            ensemble_probs_filtered, targets, market_probs, time_pcts, bar_indices,
        )

        # Add model disagreement stats
        disagreement = np.abs(sentinel_expanded - pulse_probs)
        ensemble_metrics["avg_disagreement"] = float(disagreement.mean())
        ensemble_metrics["max_disagreement"] = float(disagreement.max())
        ensemble_metrics["pct_high_disagreement"] = float(
            (disagreement > 0.30).mean() * 100
        )

        return {
            "sentinel": sentinel_metrics,
            "pulse": pulse_metrics,
            "ensemble": ensemble_metrics,
        }

    def evaluate_all_modes(
        self,
        sentinel_probs: np.ndarray,
        pulse_probs: np.ndarray,
        targets: np.ndarray,
        market_probs: np.ndarray,
        time_pcts: np.ndarray,
        bar_indices: np.ndarray,
        strategy: CombinationStrategy,
    ) -> dict[str, dict[str, object]]:
        """Evaluate ensemble across all decision modes.

        Returns:
            Dict keyed by decision mode name, each containing the
            full comparison dict from evaluate().
        """
        results = {}
        for mode in DecisionMode:
            results[mode.value] = self.evaluate(
                sentinel_probs, pulse_probs, targets, market_probs,
                time_pcts, bar_indices, strategy, decision_mode=mode,
            )
        return results


def format_comparison(results: dict[str, object]) -> str:
    """Format comparison results as a human-readable table."""
    lines = []
    lines.append(f"{'Model':<15} {'Sharpe':>8} {'PnL':>10} {'Trades':>8} {'Win%':>8} {'Brier':>8}")
    lines.append("-" * 60)

    for model_name in ["sentinel", "pulse", "ensemble"]:
        m = results.get(model_name, {})
        lines.append(
            f"{model_name:<15} "
            f"{m.get('sharpe', 0):>8.2f} "
            f"{m.get('total_pnl', 0):>10.2f} "
            f"{m.get('n_trades', 0):>8d} "
            f"{m.get('win_rate', 0) * 100:>7.1f}% "
            f"{m.get('brier', 0.25):>8.4f}"
        )

    return "\n".join(lines)
