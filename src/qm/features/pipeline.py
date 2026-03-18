"""Feature computation pipeline with dependency ordering.

Orchestrates all feature groups, computing them in topological order
so that dependent features (e.g., vol_of_vol depends on realized_vol)
are computed after their inputs are ready.
"""

from __future__ import annotations

import logging

import polars as pl

from qm.features.base import FeatureCalculatorBase
from qm.features.registry import GLOBAL_REGISTRY

logger = logging.getLogger(__name__)

# Import all feature groups to trigger auto-registration
import qm.features.groups.price  # noqa: F401
import qm.features.groups.volatility  # noqa: F401
import qm.features.groups.momentum  # noqa: F401
import qm.features.groups.volume  # noqa: F401
import qm.features.groups.time_features  # noqa: F401


def _get_calculators() -> dict[str, FeatureCalculatorBase]:
    """Collect all instantiated feature calculators by group name."""
    calculators: dict[str, FeatureCalculatorBase] = {}
    for cls in FeatureCalculatorBase.__subclasses__():
        if cls.name:
            calculators[cls.name] = cls()
    return calculators


class FeaturePipeline:
    """Computes all registered features on an OHLCV DataFrame.

    Usage:
        pipeline = FeaturePipeline()
        featured_df = pipeline.compute(bars_df)
    """

    def __init__(self, groups: list[str] | None = None) -> None:
        """Initialize pipeline.

        Args:
            groups: Optional list of group names to include.
                    If None, all registered groups are used.
        """
        all_calcs = _get_calculators()
        if groups:
            self._calculators = {k: v for k, v in all_calcs.items() if k in groups}
        else:
            self._calculators = all_calcs

        self._compute_order = self._resolve_order()

    def _resolve_order(self) -> list[str]:
        """Resolve computation order based on feature dependencies."""
        ordered_specs = GLOBAL_REGISTRY.compute_order()
        seen_groups: list[str] = []
        for spec in ordered_specs:
            if spec.group in self._calculators and spec.group not in seen_groups:
                seen_groups.append(spec.group)
        return seen_groups

    def compute(self, bars: pl.DataFrame) -> pl.DataFrame:
        """Run all feature groups in dependency order.

        Args:
            bars: OHLCV DataFrame with columns:
                  time, open, high, low, close, volume, trade_count, vwap

        Returns:
            DataFrame with all feature columns appended.
        """
        df = bars.clone()

        for group_name in self._compute_order:
            calc = self._calculators[group_name]
            try:
                df = calc.compute(df)
            except Exception:
                logger.exception(f"Feature group '{group_name}' computation failed")
                raise

        n_features = len(df.columns) - len(bars.columns)
        logger.debug(f"Computed {n_features} features from {len(self._compute_order)} groups")
        return df

    @property
    def feature_names(self) -> list[str]:
        """Names of all features that will be computed."""
        return [s.name for s in GLOBAL_REGISTRY.get_enabled()
                if s.group in self._calculators]

    @property
    def max_lookback(self) -> int:
        """Max lookback across all included feature groups."""
        return max(
            (c.lookback for c in self._calculators.values()),
            default=0,
        )
