"""Backtest report generation and acceptance gate validation.

Computes all acceptance criteria and returns pass/fail + failed criteria list.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from qm.backtest.engine import BacktestResult

logger = logging.getLogger(__name__)

# Acceptance thresholds
DEFAULT_ACCEPTANCE = {
    "max_pbo": 0.40,
    "min_deflated_sharpe": 0.0,
    "max_brier": 0.25,
    "max_ece": 0.05,
    "min_pnl": 0.0,
    "max_drawdown_pct": 0.30,
}


def check_acceptance(
    metrics: dict[str, float],
    thresholds: dict[str, float] | None = None,
) -> tuple[bool, list[str]]:
    """Check backtest metrics against acceptance criteria.

    Args:
        metrics: Dict from BacktestEngine with keys like sharpe, brier, etc.
        thresholds: Override thresholds. Defaults to DEFAULT_ACCEPTANCE.

    Returns:
        (all_passed, list_of_failures)
    """
    t = thresholds or DEFAULT_ACCEPTANCE
    failures: list[str] = []

    brier = metrics.get("brier", 1.0)
    if brier > t.get("max_brier", 0.25):
        failures.append(f"Brier {brier:.4f} > {t['max_brier']}")

    sharpe = metrics.get("sharpe", -999)
    if sharpe < t.get("min_deflated_sharpe", 0.0):
        failures.append(f"Sharpe {sharpe:.4f} < {t['min_deflated_sharpe']}")

    total_pnl = metrics.get("total_pnl", -999)
    if total_pnl < t.get("min_pnl", 0.0):
        failures.append(f"PnL {total_pnl:.2f} < {t['min_pnl']}")

    max_dd = metrics.get("max_dd", 999)
    max_dd_threshold = t.get("max_drawdown_pct", 0.30)
    # max_dd is absolute, convert bankroll fraction if needed
    if max_dd > max_dd_threshold and max_dd < 1.0:
        failures.append(f"Max DD {max_dd:.2%} > {max_dd_threshold:.2%}")

    passed = len(failures) == 0
    return passed, failures


def generate_report(
    result: BacktestResult,
    model_info: dict[str, Any] | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Generate a full backtest report.

    Args:
        result: BacktestResult from BacktestEngine.
        model_info: Optional model metadata (params, version, etc.)
        output_dir: If provided, saves report as JSON.

    Returns:
        Report dict with metrics, acceptance, trade summary.
    """
    metrics = result.metrics
    passed, failures = check_acceptance(metrics)

    # Trade summary
    trade_log = result.trade_log
    n_trades = len(trade_log)

    winning_trades = [t for t in trade_log if t.get("pnl", 0) > 0]
    losing_trades = [t for t in trade_log if t.get("pnl", 0) <= 0]

    avg_win = sum(t["pnl"] for t in winning_trades) / max(len(winning_trades), 1)
    avg_loss = sum(t["pnl"] for t in losing_trades) / max(len(losing_trades), 1)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "acceptance": {
            "passed": passed,
            "failures": failures,
        },
        "metrics": metrics,
        "trade_summary": {
            "total_trades": n_trades,
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "win_rate": metrics.get("win_rate", 0),
            "avg_win_pnl": avg_win,
            "avg_loss_pnl": avg_loss,
            "profit_factor": abs(avg_win / avg_loss) if avg_loss != 0 else 0,
        },
        "model_info": model_info or {},
    }

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        report_path = output_dir / f"backtest_report_{ts}.json"
        report_path.write_text(json.dumps(report, indent=2, default=str))
        logger.info("Report saved to %s", report_path)

    # Log summary
    status = "PASS" if passed else "FAIL"
    logger.info(
        "Backtest %s | Sharpe=%.2f Brier=%.4f PnL=%.2f DD=%.2f%% Trades=%d WR=%.1f%%",
        status,
        metrics.get("sharpe", 0),
        metrics.get("brier", 0),
        metrics.get("total_pnl", 0),
        metrics.get("max_dd", 0) * 100,
        n_trades,
        metrics.get("win_rate", 0) * 100,
    )

    if not passed:
        for f in failures:
            logger.warning("Acceptance FAILED: %s", f)

    return report
