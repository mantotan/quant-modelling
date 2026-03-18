"""Base class for feature calculators.

All feature groups inherit from FeatureCalculatorBase and implement
compute() using Polars expressions for speed.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import polars as pl

from qm.features.registry import GLOBAL_REGISTRY, FeatureSpec


class FeatureCalculatorBase(ABC):
    """Base class for feature group calculators.

    Subclasses define:
    - name: group identifier
    - lookback: bars of history needed before first valid output
    - specs(): list of FeatureSpec for registration
    - compute(): Polars DataFrame transformation
    """

    name: str = ""
    lookback: int = 0

    def __init_subclass__(cls, **kwargs: object) -> None:
        """Auto-register feature specs when a subclass is defined."""
        super().__init_subclass__(**kwargs)
        if cls.name:  # skip abstract base
            instance = cls()
            specs = instance.specs()
            GLOBAL_REGISTRY.register_many(specs)

    @abstractmethod
    def specs(self) -> list[FeatureSpec]:
        """Return FeatureSpec definitions for all features in this group."""
        ...

    @abstractmethod
    def compute(self, bars: pl.DataFrame) -> pl.DataFrame:
        """Compute features and return DataFrame with new columns added.

        Args:
            bars: OHLCV DataFrame with columns:
                  time, open, high, low, close, volume, trade_count, vwap

        Returns:
            Same DataFrame with feature columns appended.
        """
        ...

    def required_columns(self) -> list[str]:
        """Columns that must exist in the input DataFrame."""
        return ["time", "open", "high", "low", "close", "volume"]
