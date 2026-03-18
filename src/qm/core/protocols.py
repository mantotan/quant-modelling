"""Protocol definitions (structural typing) for pluggable components."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Protocol, runtime_checkable

import numpy as np
import polars as pl


@runtime_checkable
class ExchangeConnector(Protocol):
    """Any exchange data source must implement this."""

    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    async def subscribe_trades(self, symbols: list[str]) -> None: ...
    def is_healthy(self) -> bool: ...


@runtime_checkable
class FeatureCalculator(Protocol):
    """Every feature group implements this."""

    name: str
    lookback: int  # bars needed before first valid output

    def compute(self, bars: pl.DataFrame) -> pl.DataFrame: ...
    def required_columns(self) -> list[str]: ...


@runtime_checkable
class Trainer(Protocol):
    """Any model trainer must conform."""

    def fit(
        self,
        X: pl.DataFrame,
        y: pl.Series,
        cv_splitter: CVSplitter,
    ) -> TrainResult: ...

    def predict_proba(self, X: pl.DataFrame) -> np.ndarray: ...
    def save(self, path: Path) -> None: ...
    def load(self, path: Path) -> None: ...


@runtime_checkable
class CVSplitter(Protocol):
    """Cross-validation splitter for time series."""

    def split(
        self,
        X: pl.DataFrame,
        prediction_times: np.ndarray,
        evaluation_times: np.ndarray,
    ) -> Iterator[tuple[np.ndarray, np.ndarray]]: ...


@runtime_checkable
class Sizer(Protocol):
    """Position sizing."""

    def size(self, edge: float, market_price: float, bankroll: float) -> float: ...


@runtime_checkable
class RiskCheck(Protocol):
    """Pre-trade risk check."""

    def check(
        self,
        signal: object,
        size: float,
        portfolio: object,
    ) -> tuple[bool, str]: ...


class TrainResult:
    """Result of a training run."""

    __slots__ = ("model", "params", "cv_metrics")

    def __init__(
        self,
        model: object,
        params: dict[str, object],
        cv_metrics: dict[str, float],
    ) -> None:
        self.model = model
        self.params = params
        self.cv_metrics = cv_metrics
