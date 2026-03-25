"""TabNet trainer with Optuna HPO and walk-forward evaluation.

TabNet uses sequential attention masks to select features per sample,
providing interpretable per-sample feature importance.  This is used
to validate whether alpha features (funding, OI, IV, liquidation)
contain signal that LightGBM structurally cannot exploit.

Requires ``pytorch-tabnet`` (optional gpu dependency).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
import optuna

from qm.backtest.engine import BacktestEngine
from qm.backtest.validation.walk_forward import WalkForwardSplitter

logger = logging.getLogger(__name__)
optuna.logging.set_verbosity(optuna.logging.WARNING)


class TabNetTrainer:
    """TabNet trainer with Optuna HPO and walk-forward evaluation.

    Interface mirrors :class:`LGBMTrainer` so it can be swapped in
    ``train_sentinel.py`` via ``--model-type tabnet``.

    Args:
        n_trials: Optuna HPO trials (default 30 — TabNet is ~5x slower).
        n_splits: Walk-forward splits.
        train_period: Bars per training window.
        test_period: Bars per test window.
        backtest_engine: For fast vectorized evaluation.
        seed: Reproducibility.
    """

    def __init__(
        self,
        n_trials: int = 30,
        n_splits: int = 5,
        train_period: int = 5000,
        test_period: int = 1000,
        backtest_engine: BacktestEngine | None = None,
        seed: int = 42,
        use_gpu: bool = True,
    ) -> None:
        self.n_trials = n_trials
        self.n_splits = n_splits
        self.train_period = train_period
        self.test_period = test_period
        self._engine = backtest_engine or BacktestEngine()
        self.seed = seed
        self.use_gpu = use_gpu
        self._device_name = self._detect_device()
        self._model: Any = None  # TabNetClassifier instance
        self._best_params: dict[str, Any] = {}
        self._feature_names: list[str] = []

    def _detect_device(self) -> str:
        """Detect GPU for TabNet. Returns 'cuda' or 'cpu'."""
        if not self.use_gpu:
            return "cpu"
        try:
            import torch
            if torch.cuda.is_available():
                logger.info("TabNet device: cuda (%s)", torch.cuda.get_device_name(0))
                return "cuda"
        except ImportError:
            pass
        logger.info("TabNet device: cpu")
        return "cpu"

    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        feature_names: list[str] | None = None,
        market_probs: np.ndarray | None = None,
    ) -> dict[str, float]:
        """Full training pipeline: HPO -> retrain -> return metrics."""
        from pytorch_tabnet.tab_model import TabNetClassifier

        if hasattr(X, "to_numpy"):
            X = X.to_numpy()
        if hasattr(y, "to_numpy"):
            y = y.to_numpy()

        X = X.astype(np.float64)
        y = y.astype(np.int64)
        self._feature_names = feature_names or [f"f{i}" for i in range(X.shape[1])]

        splitter = WalkForwardSplitter(
            n_splits=self.n_splits,
            train_period=self.train_period,
            test_period=self.test_period,
            purge_period=12,
            embargo_period=6,
        )

        best_metrics: dict[str, float] = {}

        def objective(trial: optuna.Trial) -> float:
            n_d = trial.suggest_int("n_d", 8, 64)
            params = {
                "n_d": n_d,
                "n_a": n_d,  # tie n_a = n_d (common practice)
                "n_steps": trial.suggest_int("n_steps", 3, 10),
                "gamma": trial.suggest_float("gamma", 1.0, 2.0),
                "lambda_sparse": trial.suggest_float(
                    "lambda_sparse", 1e-6, 1e-2, log=True,
                ),
                "n_independent": trial.suggest_int("n_independent", 1, 5),
                "n_shared": trial.suggest_int("n_shared", 1, 5),
                "momentum": trial.suggest_float("momentum", 0.01, 0.4),
                "mask_type": trial.suggest_categorical(
                    "mask_type", ["sparsemax", "entmax"],
                ),
            }

            all_oos_probs = np.zeros(len(y), dtype=np.float64)
            all_oos_mask = np.zeros(len(y), dtype=bool)

            for train_idx, test_idx in splitter.split(len(y)):
                model = TabNetClassifier(
                    **params,
                    seed=self.seed,
                    verbose=0,
                    device_name=self._device_name,
                    optimizer_params={"lr": 2e-2},
                )
                model.fit(
                    X[train_idx], y[train_idx],
                    eval_set=[(X[test_idx], y[test_idx])],
                    eval_metric=["logloss"],
                    max_epochs=100,
                    patience=10,
                    batch_size=1024,
                    virtual_batch_size=128,
                )
                probs = model.predict_proba(X[test_idx])[:, 1]
                all_oos_probs[test_idx] = probs
                all_oos_mask[test_idx] = True

            if not all_oos_mask.any():
                return 1.0

            oos_idx = np.where(all_oos_mask)[0]
            mp = market_probs[oos_idx] if market_probs is not None else None
            metrics = self._engine.evaluate_model_fast(
                all_oos_probs[oos_idx], y[oos_idx].astype(np.float64), mp,
            )

            nonlocal best_metrics
            brier = metrics["brier"]
            if not best_metrics or brier < best_metrics.get("brier", 1.0):
                best_metrics = metrics

            return brier

        study = optuna.create_study(
            direction="minimize",
            sampler=optuna.samplers.TPESampler(seed=self.seed),
        )
        study.optimize(objective, n_trials=self.n_trials, n_jobs=1)

        self._best_params = study.best_params
        # Tie n_a = n_d
        if "n_d" in self._best_params and "n_a" not in self._best_params:
            self._best_params["n_a"] = self._best_params["n_d"]
        logger.info("TabNet HPO complete. Best Brier: %.4f", study.best_value)

        # Retrain on full data
        final_params = {
            k: v for k, v in self._best_params.items()
            if k not in ("n_a",)  # will be set from n_d
        }
        final_params["n_a"] = final_params.get("n_d", 8)
        self._model = TabNetClassifier(
            **final_params,
            seed=self.seed,
            verbose=0,
            device_name=self._device_name,
            optimizer_params={"lr": 2e-2},
        )
        # Use last 10% as validation for early stopping
        val_size = max(1, len(y) // 10)
        self._model.fit(
            X[:-val_size], y[:-val_size],
            eval_set=[(X[-val_size:], y[-val_size:])],
            eval_metric=["logloss"],
            max_epochs=200,
            patience=15,
            batch_size=1024,
            virtual_batch_size=128,
        )

        return best_metrics

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Predict P(Up) for new data."""
        if self._model is None:
            msg = "Model not trained. Call fit() first."
            raise RuntimeError(msg)
        if hasattr(X, "to_numpy"):
            X = X.to_numpy()
        return self._model.predict_proba(X.astype(np.float64))[:, 1]

    def attention_masks(self, X: np.ndarray) -> np.ndarray:
        """Per-sample feature attention masks.

        Returns:
            Array of shape ``(n_samples, n_features)`` where each row
            sums to approximately 1.0.  Higher values indicate the
            model attended more to that feature for that sample.
        """
        if self._model is None:
            msg = "Model not trained. Call fit() first."
            raise RuntimeError(msg)
        if hasattr(X, "to_numpy"):
            X = X.to_numpy()
        explain_matrix, _ = self._model.explain(X.astype(np.float64))
        return explain_matrix

    def save(self, path: Path) -> None:
        """Save TabNet model to directory."""
        if self._model is None:
            msg = "No model to save"
            raise RuntimeError(msg)
        path.parent.mkdir(parents=True, exist_ok=True)
        # TabNet saves to a zip; we use its native method
        self._model.save_model(str(path))

    def load(self, path: Path) -> None:
        """Load TabNet model from directory."""
        from pytorch_tabnet.tab_model import TabNetClassifier

        self._model = TabNetClassifier()
        # TabNet's load expects path without .zip extension
        load_path = str(path)
        if load_path.endswith(".zip"):
            load_path = load_path[:-4]
        self._model.load_model(load_path + ".zip")

    @property
    def feature_importance(self) -> dict[str, float]:
        """Aggregate attention-based feature importance."""
        if self._model is None:
            return {}
        importances = self._model.feature_importances_
        names = self._feature_names or [f"f{i}" for i in range(len(importances))]
        return dict(sorted(zip(names, importances, strict=False), key=lambda x: -x[1]))

    @property
    def best_params(self) -> dict[str, Any]:
        return self._best_params
