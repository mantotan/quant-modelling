"""Combinatorial Purged Cross-Validation (CPCV).

Generates C(N, k) backtest paths for statistical validation.
Computes Probability of Backtest Overfitting (PBO).

Reference: Bailey, Borwein, Lopez de Prado, Zhu (2017)
"""

from __future__ import annotations

from collections.abc import Iterator
from itertools import combinations

import numpy as np


class CombPurgedKFoldCV:
    """Combinatorial Purged K-Fold Cross-Validation.

    Splits data into N groups, tests on k groups at a time,
    yielding C(N, k) unique train/test combinations.

    Each split has purge + embargo applied to prevent leakage.

    Args:
        n_groups: Number of groups to split data into.
        k_test_groups: Number of groups in each test set.
        purge_period: Bars to purge between train and test boundaries.
        embargo_pct: Fraction of data to embargo after test periods.
    """

    def __init__(
        self,
        n_groups: int = 10,
        k_test_groups: int = 2,
        purge_period: int = 12,
        embargo_pct: float = 0.01,
    ) -> None:
        self.n_groups = n_groups
        self.k_test_groups = k_test_groups
        self.purge_period = purge_period
        self.embargo_pct = embargo_pct

    @property
    def n_paths(self) -> int:
        """Number of unique backtest paths: C(n_groups, k_test_groups)."""
        from math import comb
        return comb(self.n_groups, self.k_test_groups)

    def split(
        self,
        n_samples: int,
        prediction_times: np.ndarray | None = None,
        evaluation_times: np.ndarray | None = None,
    ) -> Iterator[tuple[np.ndarray, np.ndarray]]:
        """Yield all C(N, k) train/test splits with purge + embargo.

        Args:
            n_samples: Total number of samples.
            prediction_times: Unused, for API compatibility.
            evaluation_times: Unused, for API compatibility.
        """
        # Split indices into N roughly equal groups
        all_indices = np.arange(n_samples)
        groups = np.array_split(all_indices, self.n_groups)
        embargo_size = max(1, int(n_samples * self.embargo_pct))

        for test_combo in combinations(range(self.n_groups), self.k_test_groups):
            test_idx = np.concatenate([groups[g] for g in test_combo])
            train_groups = [g for g in range(self.n_groups) if g not in test_combo]
            train_idx = np.concatenate([groups[g] for g in train_groups])

            # Purge: remove training samples within purge_period of EACH test group boundary
            # (not just global min/max — interior boundaries matter for non-contiguous test sets)
            if self.purge_period > 0:
                purge_set: set[int] = set()
                for g in test_combo:
                    g_min = int(groups[g][0])
                    g_max = int(groups[g][-1])
                    purge_set.update(range(max(0, g_min - self.purge_period), g_min))
                    purge_set.update(range(g_max + 1, min(n_samples, g_max + 1 + self.purge_period)))
                train_idx = np.array([i for i in train_idx if i not in purge_set])

            # Embargo: remove training samples immediately after each test group
            if embargo_size > 0:
                embargo_set: set[int] = set()
                for g in test_combo:
                    group_end = int(groups[g][-1])
                    for j in range(1, embargo_size + 1):
                        embargo_set.add(group_end + j)
                train_idx = np.array([i for i in train_idx if i not in embargo_set])

            yield train_idx, test_idx

    def probability_of_backtest_overfitting(
        self,
        is_results: np.ndarray,
        oos_results: np.ndarray,
    ) -> float:
        """Compute PBO from CPCV results.

        PBO = proportion of paths where the best in-sample combination
        ranks below median out-of-sample.

        Args:
            is_results: In-sample metric for each path, shape (n_paths,)
            oos_results: Out-of-sample metric for each path, shape (n_paths,)

        Returns:
            PBO in [0, 1]. Lower is better. PBO < 0.5 suggests not overfit.
        """
        if len(is_results) == 0:
            return 1.0

        # Rank each path by IS performance
        is_ranks = np.argsort(np.argsort(-is_results))  # 0 = best IS

        # For the best IS path, what's its OOS rank?
        best_is_idx = np.argmin(is_ranks)
        oos_rank_of_best_is = np.searchsorted(
            np.sort(oos_results), oos_results[best_is_idx]
        )

        # PBO = fraction of OOS results that are better
        n = len(oos_results)
        pbo = 1.0 - (oos_rank_of_best_is / n)
        return float(pbo)
