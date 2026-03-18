"""Parquet storage with Hive-style partitioning.

Stores OHLCV data as partitioned parquet files for fast batch analytics.
Layout: data/raw/ohlcv/asset=BTC/timeframe=5m/date=2026-03-18/data.parquet
"""

from __future__ import annotations

import logging
from pathlib import Path

import polars as pl

from qm.core.types import Asset, Bar, Timeframe

logger = logging.getLogger(__name__)


class ParquetStore:
    """Read/write OHLCV data as partitioned Parquet files.

    Uses Hive-style partitioning compatible with DuckDB predicate pushdown.
    """

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def write_bars(self, bars: list[Bar]) -> None:
        """Write a batch of bars to partitioned parquet files."""
        if not bars:
            return

        df = pl.DataFrame(
            {
                "time": [b.timestamp for b in bars],
                "asset": [b.asset.value for b in bars],
                "timeframe": [b.timeframe.value for b in bars],
                "open": [b.open for b in bars],
                "high": [b.high for b in bars],
                "low": [b.low for b in bars],
                "close": [b.close for b in bars],
                "volume": [b.volume for b in bars],
                "trade_count": [b.trade_count for b in bars],
                "vwap": [b.vwap for b in bars],
            }
        ).with_columns(
            pl.col("time").dt.date().alias("date"),
        )

        # Write partitioned by asset/timeframe/date
        for (asset, timeframe, date), group in df.group_by(
            ["asset", "timeframe", "date"]
        ):
            partition_dir = (
                self._base_dir / f"asset={asset}" / f"timeframe={timeframe}" / f"date={date}"
            )
            partition_dir.mkdir(parents=True, exist_ok=True)
            out_path = partition_dir / "data.parquet"

            write_df = group.drop(["asset", "timeframe", "date"])

            if out_path.exists():
                # Append: read existing, concat, deduplicate, write
                existing = pl.read_parquet(out_path)
                merged = pl.concat([existing, write_df]).unique(subset=["time"])
                merged.sort("time").write_parquet(out_path)
            else:
                write_df.sort("time").write_parquet(out_path)

        logger.debug(f"Wrote {len(bars)} bars to parquet")

    def read_bars(
        self,
        asset: Asset,
        timeframe: Timeframe,
        start: str | None = None,
        end: str | None = None,
    ) -> pl.DataFrame:
        """Read bars from parquet. Optionally filter by date range.

        Args:
            asset: Asset to read.
            timeframe: Timeframe to read.
            start: Start date string "YYYY-MM-DD" (inclusive).
            end: End date string "YYYY-MM-DD" (inclusive).
        """
        pattern = self._base_dir / f"asset={asset.value}" / f"timeframe={timeframe.value}"

        if not pattern.exists():
            return pl.DataFrame()

        # Collect all matching parquet files
        parquet_files = sorted(pattern.rglob("*.parquet"))

        if not parquet_files:
            return pl.DataFrame()

        # Filter by date directory if start/end provided
        if start or end:
            filtered = []
            for f in parquet_files:
                date_part = f.parent.name.replace("date=", "")
                if start and date_part < start:
                    continue
                if end and date_part > end:
                    continue
                filtered.append(f)
            parquet_files = filtered

        if not parquet_files:
            return pl.DataFrame()

        dfs = [pl.read_parquet(f) for f in parquet_files]
        return pl.concat(dfs).sort("time")

    def write_df(
        self,
        df: pl.DataFrame,
        asset: Asset,
        timeframe: Timeframe,
    ) -> None:
        """Write a DataFrame directly to partitioned Parquet, bypassing Bar conversion.

        Preserves all columns in the DataFrame (e.g., taker_buy_volume).
        Partitions by date, deduplicates on time column.
        """
        if df.is_empty():
            return

        df = df.with_columns(pl.col("time").dt.date().alias("_date"))

        for (date_val,), group in df.group_by(["_date"]):
            partition_dir = (
                self._base_dir / f"asset={asset.value}" / f"timeframe={timeframe.value}"
                / f"date={date_val}"
            )
            partition_dir.mkdir(parents=True, exist_ok=True)
            out_path = partition_dir / "data.parquet"

            write_data = group.drop("_date")

            if out_path.exists():
                existing = pl.read_parquet(out_path)
                merged = pl.concat([existing, write_data], how="diagonal").unique(subset=["time"])
                merged.sort("time").write_parquet(out_path)
            else:
                write_data.sort("time").write_parquet(out_path)

        logger.debug("Wrote %d rows to parquet for %s/%s", len(df), asset.value, timeframe.value)

    def write_metrics(self, df: pl.DataFrame, asset: Asset) -> None:
        """Write metrics DataFrame with asset/date partitioning (no timeframe)."""
        if df.is_empty():
            return

        df = df.with_columns(pl.col("time").dt.date().alias("_date"))

        for (date_val,), group in df.group_by(["_date"]):
            partition_dir = self._base_dir / f"asset={asset.value}" / f"date={date_val}"
            partition_dir.mkdir(parents=True, exist_ok=True)
            out_path = partition_dir / "data.parquet"

            write_data = group.drop("_date")

            if out_path.exists():
                existing = pl.read_parquet(out_path)
                merged = pl.concat([existing, write_data], how="diagonal").unique(subset=["time"])
                merged.sort("time").write_parquet(out_path)
            else:
                write_data.sort("time").write_parquet(out_path)

        logger.debug("Wrote %d metrics rows for %s", len(df), asset.value)

    def read_metrics(
        self,
        asset: Asset,
        start: str | None = None,
        end: str | None = None,
    ) -> pl.DataFrame:
        """Read metrics from Parquet (asset/date partitioning, no timeframe)."""
        base = self._base_dir / f"asset={asset.value}"

        if not base.exists():
            return pl.DataFrame()

        parquet_files = sorted(base.rglob("*.parquet"))
        if not parquet_files:
            return pl.DataFrame()

        if start or end:
            filtered = []
            for f in parquet_files:
                date_part = f.parent.name.replace("date=", "")
                if start and date_part < start:
                    continue
                if end and date_part > end:
                    continue
                filtered.append(f)
            parquet_files = filtered

        if not parquet_files:
            return pl.DataFrame()

        dfs = [pl.read_parquet(f) for f in parquet_files]
        return pl.concat(dfs).sort("time")

    def list_dates(self, asset: Asset, timeframe: Timeframe) -> list[str]:
        """List available dates for an asset/timeframe combination."""
        base = self._base_dir / f"asset={asset.value}" / f"timeframe={timeframe.value}"
        if not base.exists():
            return []
        return sorted(
            d.name.replace("date=", "")
            for d in base.iterdir()
            if d.is_dir() and d.name.startswith("date=")
        )
