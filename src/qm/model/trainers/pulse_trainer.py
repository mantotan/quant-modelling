"""Pulse model trainer: LightGBM + Optuna with bar-level walk-forward.

Follows the same structure as LGBMTrainer but critical differences:
- Walk-forward splits at the BAR level (not sample level)
- 16 correlated samples per bar -> higher min_child_samples
- Shallower trees (max_depth 2-6) to prevent tick noise overfit
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import optuna

from qm.backtest.validation.walk_forward import WalkForwardSplitter
from qm.model.targets.intrabar import IntraBarDataset
from qm.model.trainers.device import detect_device

logger = logging.getLogger(__name__)

optuna.logging.set_verbosity(optuna.logging.WARNING)


class PulseTrainer:
    """LightGBM trainer for the Pulse intra-bar model.

    Training pipeline:
    1. Optuna HPO: each trial trains LightGBM, evaluates via bar-level
       walk-forward. Splits at bar level to avoid correlated-sample leakage.
    2. Best params: retrain on full training data.
    3. Return model + OOS predictions for calibration.

    Args:
        n_trials: Number of Optuna HPO trials.
        n_splits: Walk-forward splits.
        train_bars: Number of bars in each training window.
        test_bars: Number of bars in each test window.
        seed: Random seed.
    """

    def __init__(
        self,
        n_trials: int = 80,
        n_splits: int = 8,
        train_bars: int = 5000,
        test_bars: int = 2000,
        purge_period: int = 12,
        embargo_period: int = 6,
        seed: int = 42,
        use_gpu: bool = True,
    ) -> None:
        self.n_trials = n_trials
        self.n_splits = n_splits
        self.train_bars = train_bars
        self.test_bars = test_bars
        self.purge_period = purge_period
        self.embargo_period = embargo_period
        self.seed = seed
        self._device = detect_device(prefer_gpu=use_gpu)
        self._model: lgb.Booster | None = None
        self._best_params: dict[str, Any] = {}
        self._feature_names: list[str] = []

    def fit(
        self,
        dataset: IntraBarDataset,
    ) -> dict[str, float]:
        """Full training pipeline: HPO -> retrain -> return metrics.

        Args:
            dataset: IntraBarDataset with X, y, market_probs, bar_indices.

        Returns:
            Best CV metrics from HPO.
        """
        X = dataset.X
        y = dataset.y
        bar_indices = dataset.bar_indices
        self._feature_names = dataset.feature_names

        unique_bars = np.unique(bar_indices)
        n_bars = len(unique_bars)

        splitter = WalkForwardSplitter(
            n_splits=self.n_splits,
            train_period=self.train_bars,
            test_period=self.test_bars,
            purge_period=self.purge_period,
            embargo_period=self.embargo_period,
        )

        best_metrics: dict[str, float] = {}

        def objective(trial: optuna.Trial) -> float:
            params = {
                "objective": "binary",
                "metric": "binary_logloss",
                "verbosity": -1,
                "device": self._device,
                "n_estimators": trial.suggest_int("n_estimators", 100, 1500),
                "learning_rate": trial.suggest_float("lr", 0.005, 0.1, log=True),
                "max_depth": trial.suggest_int("max_depth", 2, 6),
                "num_leaves": trial.suggest_int("num_leaves", 16, 128),
                "min_child_samples": trial.suggest_int("min_child", 100, 1000),
                "subsample": trial.suggest_float("subsample", 0.6, 0.9),
                "colsample_bytree": trial.suggest_float("colsample", 0.4, 0.8),
                "reg_alpha": trial.suggest_float("reg_alpha", 1e-8, 10.0, log=True),
                "reg_lambda": trial.suggest_float("reg_lambda", 1e-8, 10.0, log=True),
                "seed": self.seed,
            }

            all_oos_probs = np.zeros(len(y))
            all_oos_mask = np.zeros(len(y), dtype=bool)

            # Bar-level walk-forward splitting (vectorized np.isin)
            for bar_train_idx, bar_test_idx in splitter.split(n_bars):
                train_bars = unique_bars[bar_train_idx]
                test_bars = unique_bars[bar_test_idx]

                train_mask = np.isin(bar_indices, train_bars)
                test_mask = np.isin(bar_indices, test_bars)
                sample_train = np.where(train_mask)[0]
                sample_test = np.where(test_mask)[0]

                if len(sample_train) == 0 or len(sample_test) == 0:
                    continue

                train_data = lgb.Dataset(
                    X[sample_train], y[sample_train],
                    feature_name=self._feature_names,
                )
                valid_data = lgb.Dataset(
                    X[sample_test], y[sample_test],
                    reference=train_data,
                )
                n_est = params.pop("n_estimators", 500)
                callbacks = [lgb.early_stopping(50, verbose=False)]
                model = lgb.train(
                    params, train_data,
                    num_boost_round=n_est,
                    valid_sets=[valid_data],
                    callbacks=callbacks,
                )
                params["n_estimators"] = n_est

                oos_probs = model.predict(X[sample_test])
                all_oos_probs[sample_test] = oos_probs
                all_oos_mask[sample_test] = True

            if not all_oos_mask.any():
                return 1.0

            oos_idx = np.where(all_oos_mask)[0]
            brier = float(np.mean((all_oos_probs[oos_idx] - y[oos_idx]) ** 2))
            accuracy = float(np.mean(
                (all_oos_probs[oos_idx] > 0.5) == (y[oos_idx] == 1)
            ))

            nonlocal best_metrics
            if not best_metrics or brier < best_metrics.get("brier", 1.0):
                best_metrics = {
                    "brier": brier,
                    "accuracy": accuracy,
                    "n_oos_samples": int(all_oos_mask.sum()),
                }

            return brier

        study = optuna.create_study(
            direction="minimize",
            sampler=optuna.samplers.TPESampler(seed=self.seed),
        )
        study.optimize(objective, n_trials=self.n_trials, n_jobs=1)

        self._best_params = study.best_params
        logger.info("Pulse HPO complete. Best Brier: %.4f", study.best_value)

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
        if "lr" in final_params:
            final_params["learning_rate"] = final_params.pop("lr")
        if "min_child" in final_params:
            final_params["min_child_samples"] = final_params.pop("min_child")
        if "colsample" in final_params:
            final_params["colsample_bytree"] = final_params.pop("colsample")

        train_data = lgb.Dataset(X, y, feature_name=self._feature_names)
        self._model = lgb.train(final_params, train_data, num_boost_round=n_estimators)

        return best_metrics

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Predict P(Up) for new data."""
        if self._model is None:
            msg = "Model not trained. Call fit() first."
            raise RuntimeError(msg)
        return self._model.predict(X)

    def get_oos_predictions(
        self, dataset: IntraBarDataset
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Generate OOS predictions for calibration fitting.

        Uses bar-level walk-forward with the best params to produce
        out-of-sample predictions that can be passed to IsotonicCalibrator.

        Returns:
            (oos_probs, oos_targets, oos_mask) — oos_mask indicates which
            samples have OOS predictions.
        """
        if not self._best_params:
            msg = "No best params. Call fit() first."
            raise RuntimeError(msg)

        X = dataset.X
        y = dataset.y
        bar_indices = dataset.bar_indices
        unique_bars = np.unique(bar_indices)
        n_bars = len(unique_bars)

        splitter = WalkForwardSplitter(
            n_splits=self.n_splits,
            train_period=self.train_bars,
            test_period=self.test_bars,
            purge_period=self.purge_period,
            embargo_period=self.embargo_period,
        )

        final_params = {
            "objective": "binary",
            "metric": "binary_logloss",
            "verbosity": -1,
            "device": self._device,
            "seed": self.seed,
            **self._best_params,
        }
        n_estimators = final_params.pop("n_estimators", 500)
        if "lr" in final_params:
            final_params["learning_rate"] = final_params.pop("lr")
        if "min_child" in final_params:
            final_params["min_child_samples"] = final_params.pop("min_child")
        if "colsample" in final_params:
            final_params["colsample_bytree"] = final_params.pop("colsample")

        oos_probs = np.zeros(len(y))
        oos_mask = np.zeros(len(y), dtype=bool)

        for bar_train_idx, bar_test_idx in splitter.split(n_bars):
            train_bars = unique_bars[bar_train_idx]
            test_bars = unique_bars[bar_test_idx]

            train_mask = np.isin(bar_indices, train_bars)
            test_mask = np.isin(bar_indices, test_bars)
            sample_train = np.where(train_mask)[0]
            sample_test = np.where(test_mask)[0]

            if len(sample_train) == 0 or len(sample_test) == 0:
                continue

            train_data = lgb.Dataset(
                X[sample_train], y[sample_train],
                feature_name=self._feature_names,
            )
            model = lgb.train(final_params, train_data, num_boost_round=n_estimators)
            oos_probs[sample_test] = model.predict(X[sample_test])
            oos_mask[sample_test] = True

        return oos_probs, y, oos_mask

    def save(self, path: Path) -> None:
        if self._model is None:
            msg = "No model to save"
            raise RuntimeError(msg)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._model.save_model(str(path))

    def load(self, path: Path) -> None:
        self._model = lgb.Booster(model_file=str(path))

    @property
    def feature_importance(self) -> dict[str, int]:
        if self._model is None:
            return {}
        importance = self._model.feature_importance(importance_type="gain")
        names = self._model.feature_name()
        return dict(sorted(zip(names, importance), key=lambda x: -x[1]))

    @property
    def best_params(self) -> dict[str, Any]:
        return self._best_params
