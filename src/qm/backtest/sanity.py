"""Backtest sanity checker — validates results against acceptance criteria.

Provides a structured check of backtest metrics against configurable
thresholds. Used by the autoresearch loop to determine whether a model
iteration meets minimum quality standards before KEEP/DISCARD decisions.

Acceptance criteria (from CLAUDE.md):
- PBO < 0.40
- Deflated Sharpe > 0.0
- OOS Brier < 0.25
- OOS ECE < 0.05
- Net PnL after costs > 0
- Max drawdown < 30%

Additional checks for sanity:
- Minimum number of trades (avoid overfitting to rare events)
- Win rate in plausible range (not suspiciously high)
- Sharpe in plausible range (detect data leakage)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AcceptanceCriteria:
    """Thresholds for backtest acceptance.

    All thresholds have sensible defaults matching the project's
    acceptance criteria. Override for tighter or looser checks.
    """

    max_brier: float = 0.25
    max_ece: float = 0.05
    min_sharpe: float = 0.0
    max_drawdown: float = 0.30
    min_pnl: float = 0.0
    max_pbo: float = 0.40
    min_trades: int = 50
    max_win_rate: float = 0.85  # suspiciously high → data leakage
    max_sharpe: float = 5.0     # suspiciously high → data leakage


@dataclass(frozen=True, slots=True)
class CheckResult:
    """Result of a single sanity check."""

    name: str
    passed: bool
    value: float
    threshold: float
    message: str


class BacktestSanityChecker:
    """Validates backtest metrics against acceptance criteria.

    Usage:
        checker = BacktestSanityChecker()
        results = checker.check(metrics)
        if checker.all_passed(results):
            # model meets acceptance
        else:
            for r in checker.failures(results):
                print(r.message)
    """

    def __init__(self, criteria: AcceptanceCriteria | None = None) -> None:
        self.criteria = criteria or AcceptanceCriteria()

    def check(self, metrics: dict[str, float]) -> list[CheckResult]:
        """Run all sanity checks against the provided metrics.

        Args:
            metrics: Dict from BacktestEngine with keys like
                ``brier``, ``sharpe``, ``total_pnl``, ``max_dd``,
                ``n_trades``, ``win_rate``, ``ece``, ``pbo``.

        Returns:
            List of CheckResult, one per check.
        """
        c = self.criteria
        results: list[CheckResult] = []

        # Brier score (lower is better)
        brier = metrics.get("brier", 1.0)
        results.append(CheckResult(
            "brier", brier <= c.max_brier, brier, c.max_brier,
            f"Brier {brier:.4f} {'<=' if brier <= c.max_brier else '>'} {c.max_brier}",
        ))

        # ECE (lower is better)
        ece = metrics.get("ece", 1.0)
        results.append(CheckResult(
            "ece", ece <= c.max_ece, ece, c.max_ece,
            f"ECE {ece:.4f} {'<=' if ece <= c.max_ece else '>'} {c.max_ece}",
        ))

        # Sharpe (higher is better)
        sharpe = metrics.get("sharpe", 0.0)
        results.append(CheckResult(
            "sharpe", sharpe >= c.min_sharpe, sharpe, c.min_sharpe,
            f"Sharpe {sharpe:.4f} {'>=' if sharpe >= c.min_sharpe else '<'} {c.min_sharpe}",
        ))

        # Max drawdown (lower is better)
        max_dd = metrics.get("max_dd", 1.0)
        results.append(CheckResult(
            "max_dd", max_dd <= c.max_drawdown, max_dd, c.max_drawdown,
            f"MaxDD {max_dd:.2%} {'<=' if max_dd <= c.max_drawdown else '>'} {c.max_drawdown:.0%}",
        ))

        # Net PnL (higher is better)
        pnl = metrics.get("total_pnl", 0.0)
        results.append(CheckResult(
            "pnl", pnl >= c.min_pnl, pnl, c.min_pnl,
            f"PnL {pnl:.2f} {'>=' if pnl >= c.min_pnl else '<'} {c.min_pnl}",
        ))

        # PBO (lower is better) — optional, may not be in metrics
        if "pbo" in metrics:
            pbo = metrics["pbo"]
            results.append(CheckResult(
                "pbo", pbo <= c.max_pbo, pbo, c.max_pbo,
                f"PBO {pbo:.4f} {'<=' if pbo <= c.max_pbo else '>'} {c.max_pbo}",
            ))

        # Trade count (higher is better)
        n_trades = metrics.get("n_trades", 0)
        results.append(CheckResult(
            "n_trades", n_trades >= c.min_trades, n_trades, c.min_trades,
            f"Trades {n_trades:.0f} {'>=' if n_trades >= c.min_trades else '<'} {c.min_trades}",
        ))

        # Sanity: win rate not suspiciously high
        win_rate = metrics.get("win_rate", 0.0)
        results.append(CheckResult(
            "win_rate_sanity", win_rate <= c.max_win_rate,
            win_rate, c.max_win_rate,
            f"WinRate {win_rate:.2%} {'<=' if win_rate <= c.max_win_rate else '>'} "
            f"{c.max_win_rate:.0%} (leakage check)",
        ))

        # Sanity: sharpe not suspiciously high
        results.append(CheckResult(
            "sharpe_sanity", sharpe <= c.max_sharpe,
            sharpe, c.max_sharpe,
            f"Sharpe {sharpe:.4f} {'<=' if sharpe <= c.max_sharpe else '>'} "
            f"{c.max_sharpe} (leakage check)",
        ))

        return results

    @staticmethod
    def all_passed(results: list[CheckResult]) -> bool:
        """Return True if all checks passed."""
        return all(r.passed for r in results)

    @staticmethod
    def failures(results: list[CheckResult]) -> list[CheckResult]:
        """Return only the failed checks."""
        return [r for r in results if not r.passed]

    @staticmethod
    def summary(results: list[CheckResult]) -> str:
        """Human-readable summary of check results."""
        lines = []
        for r in results:
            status = "PASS" if r.passed else "FAIL"
            lines.append(f"  [{status}] {r.message}")
        n_pass = sum(1 for r in results if r.passed)
        lines.insert(0, f"Sanity check: {n_pass}/{len(results)} passed")
        return "\n".join(lines)
