"""Tests for sequence windowing and normalisation utilities."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from qm.model.trainers.sequence import SequenceNormalizer, create_sequences


class TestCreateSequences:
    def test_basic_shape(self):
        X = np.random.randn(100, 5)
        y = np.random.randint(0, 2, 100).astype(float)
        X_seq, y_seq, vi = create_sequences(X, y, seq_len=10)

        assert X_seq.shape == (91, 10, 5)
        assert y_seq.shape == (91,)
        assert vi.shape == (91,)
        assert vi[0] == 9  # first valid index
        assert vi[-1] == 99

    def test_seq_len_1(self):
        X = np.random.randn(50, 3)
        y = np.random.randint(0, 2, 50).astype(float)
        X_seq, y_seq, vi = create_sequences(X, y, seq_len=1)

        assert X_seq.shape == (50, 1, 3)
        assert len(vi) == 50

    def test_too_few_samples(self):
        X = np.random.randn(5, 3)
        y = np.ones(5)
        X_seq, y_seq, vi = create_sequences(X, y, seq_len=10)

        assert X_seq.shape[0] == 0
        assert y_seq.shape[0] == 0
        assert vi.shape[0] == 0

    def test_invalid_seq_len(self):
        with pytest.raises(ValueError, match="seq_len must be >= 1"):
            create_sequences(np.zeros((10, 3)), np.zeros(10), seq_len=0)

    def test_sequence_content_correct(self):
        """Each sequence should contain the right rows."""
        X = np.arange(20).reshape(10, 2).astype(float)
        y = np.zeros(10)
        X_seq, _, vi = create_sequences(X, y, seq_len=3)

        # First valid sequence: rows 0,1,2 -> index 2
        assert vi[0] == 2
        np.testing.assert_array_equal(X_seq[0], X[0:3])

        # Last sequence: rows 7,8,9 -> index 9
        assert vi[-1] == 9
        np.testing.assert_array_equal(X_seq[-1], X[7:10])

    def test_bar_indices_respects_boundaries(self):
        """Sequences crossing bar boundaries should be dropped."""
        X = np.random.randn(20, 3)
        y = np.zeros(20)
        # Two bars: 0-9 and 10-19
        bar_indices = np.array([0] * 10 + [1] * 10)
        X_seq, y_seq, vi = create_sequences(X, y, seq_len=3, bar_indices=bar_indices)

        # No sequence should span both bars
        for t in vi:
            start = t - 2
            assert bar_indices[start] == bar_indices[t], (
                f"Sequence at {t} crosses bar boundary"
            )

    def test_bar_indices_drops_cross_boundary(self):
        """Samples at bar boundaries should be dropped when seq_len > 1."""
        X = np.random.randn(16, 2)
        y = np.zeros(16)
        # 2 bars of 8 samples each
        bar_indices = np.array([0] * 8 + [1] * 8)
        _, _, vi = create_sequences(X, y, seq_len=4, bar_indices=bar_indices)

        # Within bar 0: valid indices 3..7 (5 sequences)
        # Within bar 1: valid indices 11..15 (5 sequences)
        assert len(vi) == 10
        # No index 8,9,10 (cross-boundary)
        for t in vi:
            assert bar_indices[t - 3] == bar_indices[t]

    def test_valid_indices_map_back(self):
        """valid_indices can be used to map predictions back to flat array."""
        n = 50
        X = np.random.randn(n, 4)
        y = np.random.randint(0, 2, n).astype(float)
        _, y_seq, vi = create_sequences(X, y, seq_len=5)

        # y_seq should equal y at the valid indices
        np.testing.assert_array_equal(y_seq, y[vi])


class TestSequenceNormalizer:
    def test_fit_transform(self):
        X = np.random.randn(100, 5) * 10 + 50
        norm = SequenceNormalizer()
        X_norm = norm.fit_transform(X)

        # Should be approximately zero mean, unit std
        assert abs(X_norm.mean()) < 0.5
        assert abs(X_norm.std() - 1.0) < 0.2

    def test_transform_without_fit_raises(self):
        norm = SequenceNormalizer()
        with pytest.raises(RuntimeError, match="not fitted"):
            norm.transform(np.zeros((10, 3)))

    def test_is_fitted(self):
        norm = SequenceNormalizer()
        assert not norm.is_fitted
        norm.fit(np.random.randn(20, 3))
        assert norm.is_fitted

    def test_zero_std_handled(self):
        """Constant features should not cause division by zero."""
        X = np.ones((50, 3))
        X[:, 1] = 5.0  # constant column
        norm = SequenceNormalizer()
        X_norm = norm.fit_transform(X)
        assert np.all(np.isfinite(X_norm))

    def test_save_load_roundtrip(self, tmp_path: Path):
        X = np.random.randn(100, 4) * 3 + 7
        norm = SequenceNormalizer()
        norm.fit(X)

        path = tmp_path / "normalizer.pkl"
        norm.save(path)

        norm2 = SequenceNormalizer()
        norm2.load(path)

        X_test = np.random.randn(10, 4) * 3 + 7
        np.testing.assert_array_almost_equal(
            norm.transform(X_test),
            norm2.transform(X_test),
        )

    def test_output_dtype_float32(self):
        X = np.random.randn(20, 3).astype(np.float64)
        norm = SequenceNormalizer()
        X_norm = norm.fit_transform(X)
        assert X_norm.dtype == np.float32
