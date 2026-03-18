"""Walk-forward validation with purge and embargo.

Anchored (expanding) and sliding window modes.
Purge: gap between train end and test start prevents label leakage.
Embargo: removes training samples at the END of the training window
         that are within embargo_period of the test start. This prevents
         information from the test period's labels bleeding into training
         features (since features use lagged data that may overlap test labels).
"""

from __future__ import annotations

from collections.abc import Iterator

import numpy as np


class WalkForwardSplitter:
    """Walk-forward cross-validation splitter with purge + embargo.

    Args:
        n_splits: Number of train/test splits.
        train_period: Training window size in bars.
        test_period: Test window size in bars.
        purge_period: Bars to remove between train end and test start.
        embargo_period: Bars to remove from the end of the training window
                        (before the purge gap) to further prevent leakage.
        anchored: If True, training window grows (anchored). If False, slides.
    """

    def __init__(
        self,
        n_splits: int = 5,
        train_period: int = 5000,
        test_period: int = 1000,
        purge_period: int = 12,
        embargo_period: int = 6,
        anchored: bool = True,
    ) -> None:
        self.n_splits = n_splits
        self.train_period = train_period
        self.test_period = test_period
        self.purge_period = purge_period
        self.embargo_period = embargo_period
        self.anchored = anchored

    def split(
        self,
        n_samples: int,
        prediction_times: np.ndarray | None = None,
        evaluation_times: np.ndarray | None = None,
    ) -> Iterator[tuple[np.ndarray, np.ndarray]]:
        """Yield (train_indices, test_indices) tuples.

        Args:
            n_samples: Total number of samples.
            prediction_times: Not used in basic mode, reserved for CPCV.
            evaluation_times: Not used in basic mode, reserved for CPCV.
        """
        for i in range(self.n_splits):
            if self.anchored:
                train_start = 0
                # Anchored: training window grows to include all data up to the boundary
                train_end = self.train_period + i * self.test_period
            else:
                # Sliding: fixed-size training window slides forward
                train_start = i * self.test_period
                train_end = train_start + self.train_period
            test_start = train_end + self.purge_period
            test_end = test_start + self.test_period

            if test_end > n_samples:
                break

            # Apply embargo: remove samples from the END of training window
            # that are within embargo_period of the purge boundary.
            # This applies in BOTH anchored and sliding modes.
            effective_train_end = train_end - self.embargo_period
            if effective_train_end <= train_start:
                effective_train_end = train_start + 1  # keep at least 1 sample

            train_idx = np.arange(train_start, effective_train_end)
            test_idx = np.arange(test_start, test_end)

            yield train_idx, test_idx

    def get_n_splits(self, n_samples: int) -> int:
        """Calculate how many splits are actually possible given data size."""
        count = 0
        for _ in self.split(n_samples):
            count += 1
        return count
