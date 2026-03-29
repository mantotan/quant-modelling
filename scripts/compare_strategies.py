"""Compare trading strategies on recorded paper trading tick data.

Replays tick JSONL through multiple strategy engines and compares PnL.
Uses existing cal_prob + book state from tick data (no model inference needed).

Usage:
    uv run scripts/compare_strategies.py --pair BTC_15m
    uv run scripts/compare_strategies.py --all-pairs
    uv run scripts/compare_strategies.py --all-pairs --output results/comparison.tsv
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from qm.data.connectors.polymarket_ws import TokenBook  # noqa: E402
from qm.strategy.dutch.engine import DutchBarSummary  # noqa: E402
from qm.strategy.dutch.fill_simulator import LimitOrderSimulator  # noqa: E402
from qm.strategy.engines import create_engine  # noqa: E402

TICK_DIR = Path("data/dutch_paper")
BAR_SECONDS = {"5m": 300.0, "15m": 900.0, "1h": 3600.0}

# Default configs per strategy
DEFAULT_CONFIGS = {
    "dutch": {
        "max_marginal_pair_cost": 1.02,
        "risk_ceil": 0.25,
        "risk_t_start": 0.05,
        "max_onesided_cost": 20.0,
        "conviction_buy_skip": 0.0,
        "min_unmatched_shares": 8.0,
        "unmatched_ratio": 0.20,
    },
    "directional": {
        "prob_threshold": 0.55,
        "magnitude_threshold": 0.0,
        "kelly_fraction": 0.25,
        "order_size": 5.0,
    },
    "selective": {
        "prob_threshold": 0.55,
        "magnitude_threshold": 0.08,
        "kelly_fraction": 0.25,
        "order_size": 5.0,
    },
    "divergence": {
        "min_edge": 0.03,
        "kelly_fraction": 0.25,
        "order_size": 5.0,
    },
    "late_snipe": {
        "min_time_pct": 0.80,
        "prob_threshold": 0.55,
        "kelly_fraction": 0.35,
        "order_size": 10.0,
        "max_orders": 3,
    },
    "hybrid": {
        "max_marginal_pair_cost": 1.02,
        "switch_time_pct": 0.70,
        "directional_prob_threshold": 0.55,
        "directional_kelly_fraction": 0.30,
    },
}

STRATEGIES = list(DEFAULT_CONFIGS.keys())


def load_ticks_and_outcomes(pair: str) -> list[dict]:
    """Load tick and bar JSONL files for a pair, merge outcomes."""
    pair_dir = TICK_DIR / pair

    # Load outcomes from bar files
    outcomes: dict[int, str] = {}
    for bar_file in sorted(pair_dir.glob("bars_*.jsonl")):
        with open(bar_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    b = json.loads(line)
                    bar_id = b.get("bar_id", 0)
                    outcome = b.get("outcome", "")
                    if bar_id and outcome:
                        outcomes[bar_id] = outcome
                except Exception:
                    continue

    # Load ticks
    ticks: list[dict] = []
    for tick_file in sorted(pair_dir.glob("ticks_*.jsonl")):
        with open(tick_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    t = json.loads(line)
                    ticks.append(t)
                except Exception:
                    continue

    return ticks, outcomes


def tick_to_books(t: dict) -> tuple[TokenBook, TokenBook]:
    """Convert tick dict to TokenBook pair."""
    bid_up = t.get("bid_up", 0.01)
    ask_up = t.get("ask_up", 0.99)
    bid_dn = t.get("bid_dn", 0.01)
    ask_dn = t.get("ask_dn", 0.99)

    # Realistic depth: scale with price distance from extremes.
    # Near 0.50 (balanced): ~50 shares depth (liquid).
    # Near 0.01/0.99 (extreme): ~5 shares depth (thin).
    def _depth(price: float) -> float:
        dist_from_edge = min(price, 1.0 - price)
        return max(5.0, 50.0 * dist_from_edge / 0.5)

    book_up = TokenBook(token_id="up")
    book_up.best_bid = bid_up
    book_up.best_ask = ask_up
    if bid_up > 0:
        book_up.bids = {bid_up: _depth(bid_up)}
    if ask_up < 1.0:
        book_up.asks = {ask_up: _depth(ask_up)}

    book_dn = TokenBook(token_id="dn")
    book_dn.best_bid = bid_dn
    book_dn.best_ask = ask_dn
    if bid_dn > 0:
        book_dn.bids = {bid_dn: _depth(bid_dn)}
    if ask_dn < 1.0:
        book_dn.asks = {ask_dn: _depth(ask_dn)}

    return book_up, book_dn


def replay_strategy(
    strategy_name: str,
    config: dict,
    ticks: list[dict],
    outcomes: dict[int, str],
    bar_seconds: float,
) -> list[DutchBarSummary]:
    """Replay ticks through a strategy engine, return per-bar summaries."""
    engine = create_engine(strategy_name, config, bar_seconds)

    sim_kwargs = config.get("fill_simulator", {})
    sim = LimitOrderSimulator(
        fill_ticks=sim_kwargs.get("fill_ticks", 1),
        chase_threshold=sim_kwargs.get("chase_threshold", 0.03),
        max_chase=sim_kwargs.get("max_chase", 2),
        spread_offset=sim_kwargs.get("spread_offset", 0.01),
        cancel_distance=sim_kwargs.get("cancel_distance", 0.05),
    )

    summaries: list[DutchBarSummary] = []
    current_bar_id: int | None = None

    for tick in ticks:
        bar_id = tick.get("bar_id", 0)
        time_pct = tick.get("time_pct", 0)
        cal_prob = tick.get("cal_prob", 0.5)

        if not tick.get("has_book", False):
            continue

        # Bar transition
        if bar_id != current_bar_id:
            if current_bar_id is not None:
                # Finalize previous bar
                for c in sim.cancel_all():
                    engine.on_order_cancelled(c)
                outcome = outcomes.get(current_bar_id, "")
                summary = engine.resolve(outcome)
                if outcome:
                    summary.compute_pnl(outcome)
                if summary.cost.get("total", 0) > 0:
                    summaries.append(summary)

            # Start new bar
            engine.reset()
            sim = LimitOrderSimulator(
                fill_ticks=sim_kwargs.get("fill_ticks", 1),
                chase_threshold=sim_kwargs.get("chase_threshold", 0.03),
                max_chase=sim_kwargs.get("max_chase", 2),
                spread_offset=sim_kwargs.get("spread_offset", 0.01),
                cancel_distance=sim_kwargs.get("cancel_distance", 0.05),
            )
            engine.set_bar_info(bar_id, "", "", "")
            current_bar_id = bar_id

        book_up, book_dn = tick_to_books(tick)

        # Run engine
        orders = engine.on_tick(time_pct, cal_prob, book_up, book_dn)

        # Cancel on flip kill
        if engine.flip_killed and not orders:
            for c in sim.cancel_all():
                engine.on_order_cancelled(c)

        for order in orders:
            sim.place(order)

        fills = sim.on_tick(time_pct, book_up, book_dn)
        for fill in fills:
            engine.on_fill(fill.order, fill.fill_price, fill.filled_shares)

    # Finalize last bar
    if current_bar_id is not None:
        for c in sim.cancel_all():
            engine.on_order_cancelled(c)
        outcome = outcomes.get(current_bar_id, "")
        summary = engine.resolve(outcome)
        if outcome:
            summary.compute_pnl(outcome)
        if summary.cost.get("total", 0) > 0:
            summaries.append(summary)

    return summaries


def compute_comparison_metrics(summaries: list[DutchBarSummary]) -> dict:
    """Compute comparison metrics from bar summaries."""
    if not summaries:
        return {
            "bars": 0, "total_pnl": 0, "avg_pnl": 0, "win_rate": 0,
            "sharpe": 0, "max_dd_pct": 0, "avg_pair_cost": 0,
            "total_matched": 0, "bars_traded": 0,
        }

    profits = [s.pnl.get("profit", 0) for s in summaries if s.pnl]

    total_pnl = sum(profits)
    avg_pnl = total_pnl / len(profits) if profits else 0
    wins = sum(1 for p in profits if p > 0)
    losses = sum(1 for p in profits if p < 0)
    win_rate = wins / len(profits) * 100 if profits else 0

    # Avg winner / avg loser
    winners = [p for p in profits if p > 0]
    losers = [p for p in profits if p < 0]
    avg_win = sum(winners) / len(winners) if winners else 0
    avg_loss = sum(losers) / len(losers) if losers else 0
    profit_factor = abs(sum(winners) / sum(losers)) if losers and sum(losers) != 0 else 999.0

    # Sharpe (annualized, assuming ~96 bars/day for 15m)
    if len(profits) > 1:
        mean_p = sum(profits) / len(profits)
        var_p = sum((p - mean_p) ** 2 for p in profits) / (len(profits) - 1)
        std_p = math.sqrt(var_p) if var_p > 0 else 1e-9
        sharpe = (mean_p / std_p) * math.sqrt(96)  # annualize
    else:
        sharpe = 0

    # Max drawdown (absolute $ and %)
    equity = 0
    peak = 0
    max_dd = 0
    for p in profits:
        equity += p
        peak = max(peak, equity)
        dd = peak - equity
        max_dd = max(max_dd, dd)
    max_dd_pct = (max_dd / 200) * 100 if max_dd > 0 else 0

    # Max consecutive losses
    max_consec_loss = 0
    curr_streak = 0
    for p in profits:
        if p < 0:
            curr_streak += 1
            max_consec_loss = max(max_consec_loss, curr_streak)
        else:
            curr_streak = 0

    # Total cost (capital deployed)
    total_cost = sum(s.cost.get("total", 0) for s in summaries)
    roi_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0

    # Avg pair cost (for Dutch)
    pair_costs = [
        s.cost.get("avg_pair_cost", 0)
        for s in summaries
        if s.inventory.get("matched", 0) > 0
    ]
    avg_pc = sum(pair_costs) / len(pair_costs) if pair_costs else 0
    total_matched = sum(s.inventory.get("matched", 0) for s in summaries)

    # Pairs profitable count
    profitable_pairs = sum(1 for s in summaries if s.pnl.get("profit", 0) > 0)

    return {
        "bars": len(summaries),
        "total_pnl": round(total_pnl, 2),
        "avg_pnl": round(avg_pnl, 2),
        "win_rate": round(win_rate, 1),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "profit_factor": round(min(profit_factor, 99.9), 2),
        "sharpe": round(sharpe, 2),
        "max_dd": round(max_dd, 2),
        "max_dd_pct": round(max_dd_pct, 1),
        "max_consec_loss": max_consec_loss,
        "total_cost": round(total_cost, 2),
        "roi_pct": round(roi_pct, 2),
        "avg_pair_cost": round(avg_pc, 4),
        "total_matched": round(total_matched, 1),
        "bars_traded": len([s for s in summaries if len(s.orders) > 0]),
    }


def run_comparison(pair: str) -> dict[str, dict]:
    """Run all strategies on one pair and return metrics per strategy."""
    asset, tf = pair.split("_")
    bar_seconds = BAR_SECONDS.get(tf, 900.0)

    print(f"  Loading {pair} ticks...", end=" ", flush=True)
    ticks, outcomes = load_ticks_and_outcomes(pair)
    resolved_outcomes = {k: v for k, v in outcomes.items() if v}
    print(f"{len(ticks)} ticks, {len(resolved_outcomes)} resolved bars")

    if not ticks or not resolved_outcomes:
        return {}

    results = {}
    for strategy_name in STRATEGIES:
        config = dict(DEFAULT_CONFIGS[strategy_name])
        print(f"    {strategy_name:15s}...", end=" ", flush=True)
        summaries = replay_strategy(strategy_name, config, ticks, outcomes, bar_seconds)
        metrics = compute_comparison_metrics(summaries)
        results[strategy_name] = metrics
        sign = "+" if metrics["total_pnl"] >= 0 else ""
        print(
            f"{sign}${metrics['total_pnl']:>8.2f}  "
            f"win={metrics['win_rate']:>4.1f}%  "
            f"sharpe={metrics['sharpe']:>+6.2f}  "
            f"bars={metrics['bars']}"
        )

    return results


def print_comparison_table(pair: str, results: dict[str, dict]) -> None:
    """Print formatted comparison table for one pair."""
    print(f"\n{'=' * 95}")
    print(f"  {pair}")
    print(f"{'=' * 95}")
    print(
        f"  {'Strategy':<15s} {'TotalPnL':>10s} {'ROI%':>7s} {'WinRate':>8s} "
        f"{'AvgWin':>8s} {'AvgLoss':>8s} {'PF':>6s} {'Sharpe':>7s} "
        f"{'MaxDD$':>8s} {'Streak':>6s} {'AvgPC':>7s} {'Bars':>5s}"
    )
    print("-" * 110)

    best_pnl = max(m["total_pnl"] for m in results.values()) if results else 0

    for name in STRATEGIES:
        m = results.get(name)
        if not m:
            continue
        sign = "+" if m["total_pnl"] >= 0 else ""
        marker = " *" if m["total_pnl"] == best_pnl and best_pnl > 0 else "  "
        pc_str = f"{m['avg_pair_cost']:.4f}" if m["avg_pair_cost"] > 0 else "  -   "
        print(
            f"  {name:<15s} {sign}${m['total_pnl']:>8.2f} {m['roi_pct']:>+6.1f}% "
            f"{m['win_rate']:>6.1f}% ${m['avg_win']:>6.2f} ${m['avg_loss']:>6.2f} "
            f"{m['profit_factor']:>5.2f} {m['sharpe']:>+6.2f} "
            f"${m['max_dd']:>7.0f} {m['max_consec_loss']:>5d} "
            f"{pc_str:>7s} {m['bars']:>5d}{marker}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare trading strategies")
    parser.add_argument("--pair", help="Single pair (e.g., BTC_15m)")
    parser.add_argument("--all-pairs", action="store_true", help="Run all pairs")
    parser.add_argument("--output", type=Path, help="Output TSV file")
    parser.add_argument(
        "--strategies",
        nargs="+",
        default=STRATEGIES,
        help="Strategies to compare",
    )
    args = parser.parse_args()

    if args.pair:
        pairs = [args.pair]
    elif args.all_pairs:
        pairs = sorted(
            d.name
            for d in TICK_DIR.iterdir()
            if d.is_dir() and "_" in d.name
        )
    else:
        parser.print_help()
        return

    all_results: dict[str, dict[str, dict]] = {}
    tsv_rows: list[str] = []

    print(f"Comparing {len(STRATEGIES)} strategies on {len(pairs)} pairs\n")

    for pair in pairs:
        results = run_comparison(pair)
        if results:
            all_results[pair] = results
            print_comparison_table(pair, results)

            for strategy_name, metrics in results.items():
                tsv_rows.append(
                    f"{pair}\t{strategy_name}\t{metrics['total_pnl']}\t"
                    f"{metrics['avg_pnl']}\t{metrics['win_rate']}\t"
                    f"{metrics['sharpe']}\t{metrics['max_dd_pct']}\t"
                    f"{metrics['avg_pair_cost']}\t{metrics['total_matched']}\t"
                    f"{metrics['bars']}"
                )

    # Grand summary
    if len(all_results) > 1:
        print(f"\n{'=' * 130}")
        print("  PORTFOLIO TOTAL (all pairs combined)")
        print(f"{'=' * 130}")
        print(
            f"  {'Strategy':<15s} {'TotalPnL':>10s} {'TotalCost':>10s} {'ROI%':>7s} "
            f"{'WinRate':>8s} {'AvgWin':>8s} {'AvgLoss':>8s} {'PF':>6s} "
            f"{'Sharpe':>7s} {'MaxDD$':>8s} {'MaxDD%':>7s} {'MaxLoss':>8s} "
            f"{'Pairs+':>7s} {'Bars':>6s}"
        )
        print("-" * 130)
        for strategy_name in STRATEGIES:
            per_pair = [
                r.get(strategy_name, {})
                for r in all_results.values()
                if strategy_name in r
            ]
            if not per_pair:
                continue

            total_pnl = sum(m.get("total_pnl", 0) for m in per_pair)
            total_cost = sum(m.get("total_cost", 0) for m in per_pair)
            roi = (total_pnl / total_cost * 100) if total_cost > 0 else 0

            avg_wr = sum(m.get("win_rate", 0) for m in per_pair) / len(per_pair)

            all_avg_wins = [m.get("avg_win", 0) for m in per_pair if m.get("avg_win", 0) > 0]
            all_avg_losses = [m.get("avg_loss", 0) for m in per_pair if m.get("avg_loss", 0) < 0]
            port_avg_win = sum(all_avg_wins) / len(all_avg_wins) if all_avg_wins else 0
            port_avg_loss = sum(all_avg_losses) / len(all_avg_losses) if all_avg_losses else 0

            total_wins = sum(sum(1 for _ in range(1)) for m in per_pair)  # placeholder
            gross_win = sum(m.get("avg_win", 0) * m.get("bars", 0) * m.get("win_rate", 0) / 100 for m in per_pair)
            gross_loss = sum(m.get("avg_loss", 0) * m.get("bars", 0) * (100 - m.get("win_rate", 0)) / 100 for m in per_pair)
            pf = abs(gross_win / gross_loss) if gross_loss != 0 else 99.9
            pf = min(pf, 99.9)

            avg_sharpe = sum(m.get("sharpe", 0) for m in per_pair) / len(per_pair)
            max_dd = max(m.get("max_dd", 0) for m in per_pair)
            max_dd_pct = max(m.get("max_dd_pct", 0) for m in per_pair)
            max_consec = max(m.get("max_consec_loss", 0) for m in per_pair)
            total_bars = sum(m.get("bars", 0) for m in per_pair)

            pairs_profitable = sum(1 for m in per_pair if m.get("total_pnl", 0) > 0)

            sign = "+" if total_pnl >= 0 else ""
            print(
                f"  {strategy_name:<15s} {sign}${total_pnl:>8.2f} ${total_cost:>9.0f} {roi:>+6.1f}% "
                f"{avg_wr:>6.1f}% ${port_avg_win:>6.2f} ${port_avg_loss:>6.2f} {pf:>5.2f} "
                f"{avg_sharpe:>+6.2f} ${max_dd:>7.0f} {max_dd_pct:>6.1f}% {max_consec:>7d} "
                f"{pairs_profitable:>4d}/{len(per_pair):<2d} {total_bars:>6d}"
            )

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        header = "pair\tstrategy\ttotal_pnl\tavg_pnl\twin_rate\tsharpe\tmax_dd_pct\tavg_pair_cost\ttotal_matched\tbars"
        args.output.write_text(header + "\n" + "\n".join(tsv_rows) + "\n")
        print(f"\nResults saved to {args.output}")


if __name__ == "__main__":
    main()
