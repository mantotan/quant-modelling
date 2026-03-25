"""Tests for ONNX export and inference.

Skipped if torch or onnxruntime are not installed.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

torch = pytest.importorskip("torch")
ort = pytest.importorskip("onnxruntime")


class TestOnnxExport:
    def test_export_alstm(self, tmp_path: Path):
        from qm.model.trainers.alstm_trainer import _build_alstm_model
        from qm.model.trainers.onnx_export import OnnxPredictor, export_to_onnx

        model = _build_alstm_model(
            n_features=5, hidden_size=16, num_layers=1, dropout=0.0,
        )
        model.eval()

        onnx_path = tmp_path / "alstm.onnx"
        export_to_onnx(model, seq_len=10, n_features=5, path=onnx_path)

        assert onnx_path.exists()

        # Test OnnxPredictor
        predictor = OnnxPredictor(onnx_path)
        X = np.random.randn(3, 10, 5).astype(np.float32)
        probs = predictor.predict_proba(X)
        assert probs.shape == (3,)
        assert probs.min() >= 0.0
        assert probs.max() <= 1.0

    @pytest.mark.skipif(
        True,  # torch 2.11 dynamo ONNX exporter produces invalid reshape for TransformerEncoder
        reason="torch.onnx.export + TransformerEncoder reshape incompatibility (torch 2.11)",
    )
    def test_export_transformer(self, tmp_path: Path):
        from qm.model.trainers.onnx_export import OnnxPredictor, export_to_onnx
        from qm.model.trainers.transformer_trainer import _build_transformer_model

        model = _build_transformer_model(
            n_features=5, d_model=16, n_heads=2, n_layers=1,
            dim_feedforward=32, dropout=0.0,
        )
        model.eval()

        onnx_path = tmp_path / "transformer.onnx"
        export_to_onnx(model, seq_len=10, n_features=5, path=onnx_path)

        assert onnx_path.exists()

        predictor = OnnxPredictor(onnx_path)
        X = np.random.randn(3, 10, 5).astype(np.float32)
        probs = predictor.predict_proba(X)
        assert probs.shape == (3,)

    def test_parity_within_tolerance(self, tmp_path: Path):
        """PyTorch and ONNX outputs should match within 1e-5."""
        from qm.model.trainers.alstm_trainer import _build_alstm_model
        from qm.model.trainers.onnx_export import OnnxPredictor, export_to_onnx

        model = _build_alstm_model(
            n_features=4, hidden_size=8, num_layers=1, dropout=0.0,
        )
        model.eval()

        onnx_path = tmp_path / "parity.onnx"
        export_to_onnx(model, seq_len=5, n_features=4, path=onnx_path)

        predictor = OnnxPredictor(onnx_path)

        for _ in range(5):
            x_np = np.random.randn(2, 5, 4).astype(np.float32)
            with torch.no_grad():
                pt_out = model(torch.tensor(x_np)).numpy()
            onnx_out = predictor.predict_proba(x_np)
            np.testing.assert_allclose(pt_out, onnx_out, atol=1e-5)
