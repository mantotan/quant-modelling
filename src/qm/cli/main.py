"""CLI entry point — Hydra-powered command dispatcher."""

from __future__ import annotations

import sys


def main() -> None:
    """Main entry point for `python -m qm` or `qm` command."""
    if len(sys.argv) < 2:
        print("Usage: qm <command> [options]")
        print()
        print("Commands:")
        print("  ingest     Start real-time data collection")
        print("  backfill   Download historical data")
        print("  features   Compute feature store")
        print("  train      Train model pipeline")
        print("  backtest   Run full backtest validation")
        print("  paper      Paper trading mode")
        print("  live       Live trading mode")
        print("  report     Generate backtest/performance reports")
        sys.exit(1)

    command = sys.argv[1]
    # Remove the command from argv so Hydra sees clean args
    sys.argv = [sys.argv[0]] + sys.argv[2:]

    if command == "ingest":
        from qm.cli.commands.ingest import run
        run()
    elif command == "backfill":
        from qm.cli.commands.backfill import run
        run()
    elif command == "features":
        from qm.cli.commands.features import run
        run()
    elif command == "train":
        from qm.cli.commands.train import run
        run()
    elif command == "backtest":
        from qm.cli.commands.backtest import run
        run()
    elif command == "paper":
        from qm.cli.commands.paper import run
        run()
    elif command == "live":
        from qm.cli.commands.live import run
        run()
    elif command == "report":
        from qm.cli.commands.report import run
        run()
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
