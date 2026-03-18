"""LightGBM trainer with Optuna HPO and walk-forward evaluation.

The objective function uses BacktestEngine.evaluate_model_fast() —
walk-forward backtest evaluation IS the training metric.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import optuna
import polars as pl

from qm.backtest.engine import BacktestEngine
from qm.backtest.validation.walk_forward import WalkForwardSplitter
from qm.model.trainers.device import detect_device

logger = logging.getLogger(__name__)

# Suppress Optuna's verbose logging
optuna.logging.set_verbosity(optuna.logging.WARNING)


class LGBMTrainer:
    """LightGBM trainer with Optuna hyperparameter optimization.

    Training pipeline:
    1. Optuna HPO: each trial trains LightGBM, evaluates via walk-forward backtest
    2. Best params: retrain on full training data
    3. Return model + OOS predictions for calibration

    Args:
        n_trials: Number of Optuna HPO trials.
        n_splits: Walk-forward splits for evaluation.
        train_period: Bars in each training window.
        test_period: Bars in each test window.
        backtest_engine: Engine for fast vectorized evaluation.
        seed: Random seed for reproducibility.
    """

    def __init__(
        self,
        n_trials: int = 100,
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
        self._device = detect_device(prefer_gpu=use_gpu)
        self._model: lgb.Booster | None = None
        self._best_params: dict[str, Any] = {}
        self._feature_names: list[str] = []

    def fit(
        self,
        X: pl.DataFrame | np.ndarray,
        y: pl.Series | np.ndarray,
        feature_names: list[str] | None = None,
        market_probs: np.ndarray | None = None,
    ) -> dict[str, float]:
        """Full training pipeline: HPO → retrain → return metrics.

        Args:
            X: Feature matrix (n_samples, n_features)
            y: Binary target (n_samples,)
            feature_names: Column names for feature importance.
            market_probs: Polymarket implied probs for backtest evaluation.

        Returns:
            Best CV metrics from the HPO.
        """
        X_np = X.to_numpy() if isinstance(X, pl.DataFrame) else X
        y_np = y.to_numpy() if isinstance(y, pl.Series) else y
        self._feature_names = feature_names or [f"f{i}" for i in range(X_np.shape[1])]

        splitter = WalkForwardSplitter(
            n_splits=self.n_splits,
            train_period=self.train_period,
            test_period=self.test_period,
            purge_period=12,
            embargo_period=6,
        )

        best_metrics: dict[str, float] = {}

        def objective(trial: optuna.Trial) -> float:
            params = {
                "objective": "binary",
                "metric": "binary_logloss",
                "verbosity": -1,
                "device": self._device,
                "n_estimators": trial.suggest_int("n_estimators", 100, 2000),
                "learning_rate": trial.suggest_float("lr", 0.005, 0.1, log=True),
                "max_depth": trial.suggest_int("max_depth", 3, 12),
                "num_leaves": trial.suggest_int("num_leaves", 15, 255),
                "min_child_samples": trial.suggest_int("min_child", 10, 200),
                "subsample": trial.suggest_float("subsample", 0.5, 1.0),
                "colsample_bytree": trial.suggest_float("colsample", 0.3, 1.0),
                "reg_alpha": trial.suggest_float("reg_alpha", 1e-8, 10.0, log=True),
                "reg_lambda": trial.suggest_float("reg_lambda", 1e-8, 10.0, log=True),
                "seed": self.seed,
            }

            # Walk-forward evaluation
            all_oos_probs = np.zeros(len(y_np))
            all_oos_mask = np.zeros(len(y_np), dtype=bool)

            for train_idx, test_idx in splitter.split(len(y_np)):
                train_data = lgb.Dataset(
                    X_np[train_idx], y_np[train_idx],
                    feature_name=self._feature_names,
                )
                model = lgb.train(
                    params, train_data,
                    num_boost_round=params["n_estimators"],
                )
                oos_probs = model.predict(X_np[test_idx])
                all_oos_probs[test_idx] = oos_probs
                all_oos_mask[test_idx] = True

            if not all_oos_mask.any():
                return 1.0  # worst possible

            # Evaluate via backtest engine
            oos_idx = np.where(all_oos_mask)[0]
            mp = market_probs[oos_idx] if market_probs is not None else None
            metrics = self._engine.evaluate_model_fast(
                all_oos_probs[oos_idx],
                y_np[oos_idx],
                mp,
            )

            nonlocal best_metrics
            brier = metrics["brier"]
            if not best_metrics or brier < best_metrics.get("brier", 1.0):
                best_metrics = metrics

            # Minimize Brier score (calibration quality)
            return brier

        study = optuna.create_study(
            direction="minimize",
            sampler=optuna.samplers.TPESampler(seed=self.seed),
        )
        study.optimize(objective, n_trials=self.n_trials, n_jobs=1)

        self._best_params = study.best_params
        logger.info(f"HPO complete. Best Brier: {study.best_value:.4f}")

        # Retrain on full data with best params
        final_params = {
            "objective": "binary",
            "metric": "binary_logloss",
            "verbosity": -1,
            "device": self._device,
            "seed": self.seed,
            **self._best_params,
        }
        n_estimators = final_params.pop("n_estimators", 500)
        # Rename optuna param names to lgbm param names
        if "lr" in final_params:
            final_params["learning_rate"] = final_params.pop("lr")
        if "min_child" in final_params:
            final_params["min_child_samples"] = final_params.pop("min_child")
        if "colsample" in final_params:
            final_params["colsample_bytree"] = final_params.pop("colsample")

        train_data = lgb.Dataset(X_np, y_np, feature_name=self._feature_names)
        self._model = lgb.train(final_params, train_data, num_boost_round=n_estimators)

        return best_metrics

    def predict_proba(self, X: pl.DataFrame | np.ndarray) -> np.ndarray:
        """Predict P(Up) for new data."""
        if self._model is None:
            msg = "Model not trained. Call fit() first."
            raise RuntimeError(msg)
        X_np = X.to_numpy() if isinstance(X, pl.DataFrame) else X
        return self._model.predict(X_np)

    def save(self, path: Path) -> None:
        """Save model to file."""
        if self._model is None:
            msg = "No model to save"
            raise RuntimeError(msg)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._model.save_model(str(path))

    def load(self, path: Path) -> None:
        """Load model from file."""
        self._model = lgb.Booster(model_file=str(path))

    @property
    def feature_importance(self) -> dict[str, int]:
        """Feature importance (gain-based)."""
        if self._model is None:
            return {}
        importance = self._model.feature_importance(importance_type="gain")
        names = self._model.feature_name()
        return dict(sorted(zip(names, importance), key=lambda x: -x[1]))

    @property
    def best_params(self) -> dict[str, Any]:
        return self._best_params
