"""ONNX export and inference for PyTorch models.

Exports ALSTM / Transformer models to ONNX for production inference
(<5ms on CPU via onnxruntime, no PyTorch dependency at inference time).
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


def export_to_onnx(
    model: object,
    seq_len: int,
    n_features: int,
    path: Path,
    opset_version: int = 18,
) -> None:
    """Export a PyTorch model to ONNX with dynamic batch size.

    Args:
        model: A ``torch.nn.Module`` instance (ALSTM or Transformer).
        seq_len: Sequence length the model expects.
        n_features: Number of input features per time step.
        path: Output ``.onnx`` file path.
        opset_version: ONNX opset version.
    """
    import io
    import sys

    import torch

    path.parent.mkdir(parents=True, exist_ok=True)

    model.eval()  # type: ignore[union-attr]
    model.cpu()  # type: ignore[union-attr]

    dummy = torch.randn(1, seq_len, n_features)

    # torch.onnx prints Unicode emoji (✅) that crash on Windows cp1252.
    # Redirect stdout/stderr to a UTF-8 buffer during export.
    old_stdout, old_stderr = sys.stdout, sys.stderr
    sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    sys.stderr = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    try:
        torch.onnx.export(
            model,  # type: ignore[arg-type]
            dummy,
            str(path),
            opset_version=opset_version,
            input_names=["input"],
            output_names=["output"],
            dynamic_axes={
                "input": {0: "batch_size"},
                "output": {0: "batch_size"},
            },
        )
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr

    # Validate round-trip
    _validate_onnx_parity(model, path, seq_len, n_features)
    logger.info("ONNX model exported to %s", path)


def _validate_onnx_parity(
    model: object,
    onnx_path: Path,
    seq_len: int,
    n_features: int,
    n_tests: int = 10,
    atol: float = 1e-5,
) -> None:
    """Compare PyTorch and ONNX outputs on random inputs."""
    import onnxruntime as ort
    import torch

    session = ort.InferenceSession(str(onnx_path))
    model.eval()  # type: ignore[union-attr]

    for _ in range(n_tests):
        x_np = np.random.randn(1, seq_len, n_features).astype(np.float32)

        # PyTorch
        with torch.no_grad():
            pt_out = model(torch.tensor(x_np)).numpy()  # type: ignore[union-attr]

        # ONNX
        ort_out = session.run(None, {"input": x_np})[0]

        max_diff = np.max(np.abs(pt_out - ort_out))
        if max_diff > atol:
            msg = f"ONNX parity check failed: max diff {max_diff:.6f} > {atol}"
            raise ValueError(msg)

    logger.debug("ONNX parity validated (%d tests, atol=%s)", n_tests, atol)


class OnnxPredictor:
    """Wraps ``onnxruntime.InferenceSession`` for fast inference.

    Typical latency: <5ms for batch=1 on CPU.
    """

    def __init__(self, path: Path) -> None:
        import onnxruntime as ort

        opts = ort.SessionOptions()
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self._session = ort.InferenceSession(str(path), opts)
        self._input_name = self._session.get_inputs()[0].name
        logger.info("OnnxPredictor loaded from %s", path)

    def predict_proba(self, X_seq: np.ndarray) -> np.ndarray:
        """Run inference on 3-D sequence array.

        Args:
            X_seq: Shape ``(batch, seq_len, n_features)``, dtype float32.

        Returns:
            Probabilities, shape ``(batch,)``.
        """
        if X_seq.dtype != np.float32:
            X_seq = X_seq.astype(np.float32)
        result = self._session.run(None, {self._input_name: X_seq})
        return result[0].flatten()
