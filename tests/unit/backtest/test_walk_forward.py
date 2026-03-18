"""Tests for walk-forward and CPCV validation splitters."""

import numpy as np
import pytest

from qm.backtest.validation.walk_forward import WalkForwardSplitter
from qm.backtest.validation.cpcv import CombPurgedKFoldCV


class TestWalkForward:
    def test_basic_splits(self):
        splitter = WalkForwardSplitter(
            n_splits=3, train_period=100, test_period=50, purge_period=5
        )
        splits = list(splitter.split(500))
        assert len(splits) == 3

    def test_no_overlap_between_train_test(self):
        splitter = WalkForwardSplitter(
            n_splits=5, train_period=100, test_period=50, purge_period=10
        )
        for train_idx, test_idx in splitter.split(1000):
            overlap = set(train_idx) & set(test_idx)
            assert len(overlap) == 0, "Train and test must not overlap"

    def test_purge_and_embargo_gap_exists(self):
        splitter = WalkForwardSplitter(
            n_splits=3, train_period=100, test_period=50,
            purge_period=10, embargo_period=6,
        )
        for train_idx, test_idx in splitter.split(500):
            train_end = train_idx[-1]
            test_start = test_idx[0]
            gap = test_start - train_end
            # Gap should be at least purge + embargo
            assert gap >= 16, f"Purge+embargo gap {gap} < 16"

    def test_anchored_train_starts_at_zero(self):
        splitter = WalkForwardSplitter(
            n_splits=3, train_period=100, test_period=50,
            purge_period=5, anchored=True,
        )
        for train_idx, _ in splitter.split(500):
            assert train_idx[0] == 0

    def test_sliding_train_moves_forward(self):
        splitter = WalkForwardSplitter(
            n_splits=3, train_period=100, test_period=50,
            purge_period=5, anchored=False,
        )
        starts = [train_idx[0] for train_idx, _ in splitter.split(500)]
        assert starts == sorted(starts)
        assert starts[0] == 0
        if len(starts) > 1:
            assert starts[1] > 0

    def test_embargo_applied_in_anchored_mode(self):
        """Embargo must work in anchored mode (was previously broken)."""
        splitter = WalkForwardSplitter(
            n_splits=3, train_period=100, test_period=50,
            purge_period=5, embargo_period=10, anchored=True,
        )
        for train_idx, test_idx in splitter.split(500):
            train_end = train_idx[-1]
            test_start = test_idx[0]
            # Embargo of 10 removes last 10 training samples, so gap >= purge + embargo
            assert test_start - train_end >= 15

    def test_handles_small_dataset(self):
        splitter = WalkForwardSplitter(
            n_splits=5, train_period=100, test_period=50, purge_period=10
        )
        splits = list(splitter.split(50))  # too small for any split
        assert len(splits) == 0


class TestCPCV:
    def test_correct_number_of_paths(self):
        cv = CombPurgedKFoldCV(n_groups=6, k_test_groups=2)
        # C(6, 2) = 15
        assert cv.n_paths == 15
        splits = list(cv.split(600))
        assert len(splits) == 15

    def test_no_overlap_between_train_test(self):
        cv = CombPurgedKFoldCV(n_groups=5, k_test_groups=2, purge_period=5)
        for train_idx, test_idx in cv.split(500):
            overlap = set(train_idx) & set(test_idx)
            assert len(overlap) == 0

    def test_all_samples_appear_in_test(self):
        cv = CombPurgedKFoldCV(n_groups=5, k_test_groups=1, purge_period=0, embargo_pct=0)
        all_test = set()
        for _, test_idx in cv.split(500):
            all_test.update(test_idx.tolist())
        assert len(all_test) == 500  # every sample tested at least once

    def test_purge_removes_boundary_samples(self):
        cv = CombPurgedKFoldCV(n_groups=5, k_test_groups=1, purge_period=10)
        for train_idx, test_idx in cv.split(500):
            test_min = test_idx.min()
            test_max = test_idx.max()
            # No training sample should be within purge_period of test boundaries
            near_start = set(range(max(0, test_min - 10), test_min))
            near_end = set(range(test_max + 1, min(500, test_max + 11)))
            overlap_start = set(train_idx.tolist()) & near_start
            overlap_end = set(train_idx.tolist()) & near_end
            assert len(overlap_start) == 0, "Purge before test failed"
            assert len(overlap_end) == 0, "Purge after test failed"

    def test_pbo_perfect_model(self):
        """A model that generalizes should have low PBO."""
        cv = CombPurgedKFoldCV()
        n = cv.n_paths
        # IS and OOS agree: best IS is also best OOS
        is_results = np.arange(n, dtype=float)
        oos_results = np.arange(n, dtype=float)  # perfect generalization
        pbo = cv.probability_of_backtest_overfitting(is_results, oos_results)
        assert pbo < 0.1

    def test_pbo_overfit_model(self):
        """A model that overfits should have high PBO."""
        cv = CombPurgedKFoldCV()
        n = cv.n_paths
        is_results = np.arange(n, dtype=float)
        # OOS is reversed: best IS is worst OOS
        oos_results = np.arange(n, dtype=float)[::-1]
        pbo = cv.probability_of_backtest_overfitting(is_results, oos_results)
        assert pbo > 0.5
