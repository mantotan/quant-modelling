#!/usr/bin/env python
"""Realistic backtest with simulated market efficiency.

The first backtest used market_prob=0.5 (assuming market knows nothing).
In reality, Polymarket 5m markets have odds that are already somewhat
efficient. This script simulates varying levels of market efficiency:

- Noise level 0.0: market = 50/50 (our first test, unrealistically easy)
- Noise level 0.1: market is slightly informed (close to reality for thin 5m markets)
- Noise level 0.2: market is moderately informed
- Noise level 0.3: market is well-informed (harder — represents competition)

We test our calibrated model against each noise level to see where edge
disappears, which tells us how efficient the market needs to be before
our model stops being profitable.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from qm.backtest.engine import BacktestEngine
from qm.backtest.metrics.calibration import brier_score, expected_calibration_error
from qm.backtest.report import check_acceptance
from qm.core.types import Asset, Timeframe
from qm.data.storage.parquet import ParquetStore
from qm.features.pipeline import FeaturePipeline
from qm.model.calibration.calibrator import IsotonicCalibrator
from qm.model.targets.binary import BinaryDirectionTarget

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("realistic")


def simulate_market_probs(
    true_labels: np.ndarray,
    noise_level: float,
    seed: int = 42,
) -> np.ndarray:
    """Simulate Polymarket odds at various efficiency levels.

    noise_level controls how much the market "knows":
    - 0.0: market = 0.5 always (knows nothing)
    - 0.5: market = true_prob + noise (moderately efficient)
    - 1.0: market = true_prob (perfectly efficient, no edge possible)

    In reality, 5m Polymarket markets are thin and inefficient — probably
    noise_level ~0.1-0.2 based on observed spreads and volume.
    """
    rng = np.random.RandomState(seed)

    # True probability approximated from local neighborhood
    # (smoothed version of the binary labels)
    from scipy.ndimage import uniform_filter1d
    window = 50  # average over ~4 hours of 5m bars
    smoothed = uniform_filter1d(true_labels.astype(float), size=window, mode="nearest")

    # Market sees a noisy version of the true probability
    # At noise_level=0: market = 0.5
    # At noise_level=1: market = smoothed (perfect)
    market_base = 0.5 + noise_level * (smoothed - 0.5)

    # Add random noise to simulate market microstructure
    noise = rng.normal(0, 0.05 * (1 - noise_level), size=len(true_labels))
    market_probs = np.clip(market_base + noise, 0.05, 0.95)

    return market_probs


def main() -> None:
    logger.info("Loading model and test data...")

    # Load test data
    store = ParquetStore(base_dir=Path("data/raw/ohlcv"))
    bars_df = store.read_bars(Asset.BTC, Timeframe.M5)

    pipeline = FeaturePipeline()
    featured_df = pipeline.compute(bars_df)
    target = BinaryDirectionTarget(horizon_bars=1).compute(featured_df)
    featured_df = featured_df.with_columns(target)

    lookback = pipeline.max_lookback
    clean_df = featured_df.slice(lookback).drop_nulls(subset=["target"])

    # Use last 20% as test
    split_idx = int(len(clean_df) * 0.80)
    test_df = clean_df.slice(split_idx)
    feature_names = pipeline.feature_names

    X_test = test_df.select(feature_names).fill_null(0).to_numpy().astype(np.float64)
    y_test = test_df["target"].to_numpy().astype(np.float64)

    # Load trained model + calibrator
    import lightgbm as lgb
    model = lgb.Booster(model_file=str(Path("data/models/BTC_5m/model.txt")))
    calibrator = IsotonicCalibrator()
    calibrator.load(Path("data/models/BTC_5m/calibrator.pkl"))

    raw_probs = model.predict(X_test)
    cal_probs = calibrator.transform(raw_probs)

    logger.info("Test set: %d bars, model accuracy: %.4f", len(y_test),
                float(np.mean((cal_probs > 0.5) == (y_test == 1))))

    # Test against varying market efficiency levels
    logger.info("")
    logger.info("=" * 90)
    logger.info("%-12s | %8s | %8s | %8s | %8s | %8s | %8s | %s",
                "Noise Level", "PnL", "Sharpe", "Brier", "Trades", "WinRate", "MaxDD", "Accept")
    logger.info("-" * 90)

    for noise in [0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50]:
        market_probs = simulate_market_probs(y_test, noise_level=noise)

        engine = BacktestEngine(fee_bps=0.0, spread=0.02, min_edge=0.03)
        result = engine.run_full_simulation(
            model_probs=cal_probs,
            targets=y_test,
            timestamps=np.arange(len(y_test)),
            market_probs=market_probs,
            initial_bankroll=10_000.0,
            kelly_fraction=0.25,
        )

        m = result.metrics
        passed, _ = check_acceptance(m)

        logger.info(
            "%-12s | %8.0f | %8.2f | %8.4f | %8d | %7.1f%% | %7.1f%% | %s",
            f"noise={noise:.2f}",
            m["total_pnl"],
            m["sharpe"],
            m["brier"],
            int(m["n_trades"]),
            m["win_rate"] * 100,
            m["max_dd"] * 100 if m["max_dd"] < 1 else m["max_dd"] / 100,
            "PASS" if passed else "FAIL",
        )

    logger.info("=" * 90)
    logger.info("")
    logger.info("Interpretation:")
    logger.info("  noise=0.00: Market knows nothing (unrealistic best case)")
    logger.info("  noise=0.10: Thin 5m markets, slightly informed (likely Polymarket reality)")
    logger.info("  noise=0.20: Moderately efficient market")
    logger.info("  noise=0.30+: Well-informed market (edge disappears)")
    logger.info("")
    logger.info("If profitable at noise=0.10-0.15, the model likely has real edge on Polymarket.")


if __name__ == "__main__":
    main()
