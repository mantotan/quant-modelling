"""treelite model compilation for sub-millisecond inference.

Compiles LightGBM tree ensemble to optimized C code → shared library.
Production inference: ~0.3-0.5ms vs LightGBM Python API ~3-5ms.

Fallback: if compilation fails, returns None and caller uses LightGBM directly.
"""

from __future__ import annotations

import logging
import platform
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


def compile_lightgbm_model(
    model_path: Path,
    output_dir: Path,
    model_name: str = "model",
) -> Path | None:
    """Compile a LightGBM model to a treelite shared library.

    Args:
        model_path: Path to LightGBM model.txt file.
        output_dir: Directory to write the compiled library.
        model_name: Base name for the output file.

    Returns:
        Path to compiled .so/.dll, or None if compilation fails.
    """
    try:
        import treelite
    except ImportError:
        logger.warning("treelite not installed, skipping model compilation")
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    ext = ".dll" if platform.system() == "Windows" else ".so"
    output_path = output_dir / f"{model_name}{ext}"

    try:
        model = treelite.frontend.load_lightgbm_model(str(model_path))
        model.export_lib(
            toolchain="msvc" if platform.system() == "Windows" else "gcc",
            libpath=str(output_path),
            verbose=False,
        )
        logger.info(f"Compiled treelite model to {output_path}")
        return output_path

    except Exception:
        logger.exception("treelite compilation failed — will use LightGBM Python fallback")
        return None


def validate_compiled_model(
    lgbm_model_path: Path,
    treelite_lib_path: Path,
    n_samples: int = 1000,
    tolerance: float = 1e-6,
) -> bool:
    """Validate that compiled model produces identical outputs to LightGBM.

    Runs n_samples random predictions through both, asserts max diff < tolerance.
    """
    try:
        import lightgbm as lgb
        import treelite_runtime

        lgbm = lgb.Booster(model_file=str(lgbm_model_path))
        n_features = lgbm.num_feature()

        predictor = treelite_runtime.Predictor(str(treelite_lib_path))

        rng = np.random.RandomState(42)
        X = rng.randn(n_samples, n_features).astype(np.float32)

        lgbm_preds = lgbm.predict(X)
        tl_preds = predictor.predict(treelite_runtime.DMatrix(X))

        max_diff = np.max(np.abs(lgbm_preds - tl_preds))

        if max_diff > tolerance:
            logger.error(f"treelite validation failed: max diff = {max_diff:.8f}")
            return False

        logger.info(f"treelite validation passed: max diff = {max_diff:.2e}")
        return True

    except Exception:
        logger.exception("treelite validation error")
        return False


class CompiledPredictor:
    """Wrapper that tries treelite first, falls back to LightGBM.

    This is the production inference path. On the hot path:
    - treelite: ~0.3-0.5ms per prediction
    - LightGBM fallback: ~3-5ms per prediction
    """

    def __init__(
        self,
        lgbm_model_path: Path,
        treelite_lib_path: Path | None = None,
    ) -> None:
        import lightgbm as lgb
        self._lgbm = lgb.Booster(model_file=str(lgbm_model_path))
        self._treelite = None

        if treelite_lib_path and treelite_lib_path.exists():
            try:
                import treelite_runtime
                self._treelite = treelite_runtime.Predictor(str(treelite_lib_path))
                logger.info("Using treelite compiled model for inference")
            except Exception:
                logger.warning("treelite runtime unavailable, using LightGBM fallback")

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict P(Up). Uses treelite if available, LightGBM otherwise."""
        if self._treelite is not None:
            try:
                import treelite_runtime
                return self._treelite.predict(treelite_runtime.DMatrix(X.astype(np.float32)))
            except Exception:
                logger.warning("treelite prediction failed, falling back to LightGBM")

        return self._lgbm.predict(X)

    @property
    def using_treelite(self) -> bool:
        return self._treelite is not None
