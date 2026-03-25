"""Stacking ensemble trainer: combines multiple base model predictions.

Uses a 2-pass approach (NOT nested HPO):
1. Base models are pre-trained independently with their own HPO.
2. OOS predictions from walk-forward are collected and calibrated.
3. A lightweight meta-learner (logistic regression) combines them.
4. Final calibration on the stacking output.

The meta-learner has only N_base_models inputs (typically 3), so
logistic regression is preferred over LightGBM to avoid overfitting.
"""

from __future__ import annotations

import json
import logging
import pickle
from pathlib import Path
from typing import Any

import numpy as np

from qm.backtest.validation.walk_forward import WalkForwardSplitter
from qm.model.calibration.calibrator import IsotonicCalibrator

logger = logging.getLogger(__name__)


class StackingTrainer:
    """Stacking ensemble that combines calibrated base model predictions.

    Args:
        base_trainers: List of ``(name, trainer_instance)`` tuples.
            Each trainer must implement ``fit()``, ``predict_proba()``,
            ``save()``, ``load()``, and ``best_params``.
        meta_model: ``"logistic"`` (default) or ``"lgbm"``.
        n_stacking_splits: Walk-forward splits for collecting OOS
            predictions for the meta-learner.
        seed: Reproducibility.
    """

    def __init__(
        self,
        base_trainers: list[tuple[str, Any]],
        meta_model: str = "logistic",
        n_stacking_splits: int = 3,
        seed: int = 42,
    ) -> None:
        self.base_trainers = base_trainers
        self.meta_model_type = meta_model
        self.n_stacking_splits = n_stacking_splits
        self.seed = seed
        self._meta_model: Any = None
        self._base_calibrators: dict[str, IsotonicCalibrator] = {}
        self._stacking_calibrator: IsotonicCalibrator | None = None
        self._best_params: dict[str, Any] = {}
        self._feature_names: list[str] = []

    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        feature_names: list[str] | None = None,
        market_probs: np.ndarray | None = None,
    ) -> dict[str, float]:
        """2-pass stacking: train base models, then fit meta-learner.

        Pass 1: Each base trainer runs its own HPO + fit on X, y.
        Pass 2: Collect OOS predictions via walk-forward, calibrate,
                 fit meta-learner on calibrated OOS predictions.
        """
        if hasattr(X, "to_numpy"):
            X = X.to_numpy()
        if hasattr(y, "to_numpy"):
            y = y.to_numpy()

        X = X.astype(np.float64)
        y = y.astype(np.float64)
        self._feature_names = feature_names or [f"f{i}" for i in range(X.shape[1])]

        # ── Pass 1: Train each base model ──
        for name, trainer in self.base_trainers:
            logger.info("Stacking pass 1: training base model '%s'...", name)
            trainer.fit(X, y, feature_names=feature_names, market_probs=market_probs)

        # ── Pass 2: Collect OOS predictions for meta-learner ──
        logger.info("Stacking pass 2: collecting OOS predictions...")
        splitter = WalkForwardSplitter(
            n_splits=self.n_stacking_splits,
            train_period=len(X) // 3,
            test_period=len(X) // 6,
            purge_period=12,
            embargo_period=6,
        )

        n_base = len(self.base_trainers)
        oos_meta_X = np.full((len(y), n_base), np.nan)
        oos_mask = np.zeros(len(y), dtype=bool)

        for fold_idx, (train_idx, test_idx) in enumerate(splitter.split(len(y))):
            logger.info("  Stacking fold %d: train=%d, test=%d",
                        fold_idx, len(train_idx), len(test_idx))

            for model_idx, (_name, trainer) in enumerate(self.base_trainers):
                # Re-train base model on this fold's training data
                fold_trainer = _clone_trainer(trainer)
                fold_trainer.fit(
                    X[train_idx], y[train_idx],
                    feature_names=feature_names,
                    market_probs=(
                        market_probs[train_idx] if market_probs is not None else None
                    ),
                )
                # Predict on OOS
                raw_probs = fold_trainer.predict_proba(X[test_idx])

                # Handle sequence-based models that return fewer predictions
                if len(raw_probs) < len(test_idx):
                    # Pad front with 0.5 (uninformative)
                    pad = np.full(len(test_idx) - len(raw_probs), 0.5)
                    raw_probs = np.concatenate([pad, raw_probs])

                oos_meta_X[test_idx, model_idx] = raw_probs

            oos_mask[test_idx] = True

        oos_idx = np.where(oos_mask)[0]
        meta_X = oos_meta_X[oos_idx]
        meta_y = y[oos_idx]

        # Calibrate each base model's OOS predictions
        for model_idx, (name, _) in enumerate(self.base_trainers):
            cal = IsotonicCalibrator()
            col = meta_X[:, model_idx]
            valid = ~np.isnan(col)
            if valid.sum() > 20:
                cal.fit(col[valid], meta_y[valid])
                meta_X[valid, model_idx] = cal.transform(col[valid])
            self._base_calibrators[name] = cal

        # Replace any remaining NaN with 0.5
        meta_X = np.nan_to_num(meta_X, nan=0.5)

        # ── Fit meta-learner ──
        if self.meta_model_type == "lgbm":
            import lightgbm as lgb

            ds = lgb.Dataset(meta_X, meta_y)
            params = {
                "objective": "binary", "metric": "binary_logloss",
                "verbosity": -1, "max_depth": 2, "num_leaves": 4,
                "n_estimators": 50, "seed": self.seed,
            }
            self._meta_model = lgb.train(params, ds, num_boost_round=50)
        else:
            from sklearn.linear_model import LogisticRegression

            self._meta_model = LogisticRegression(
                random_state=self.seed, max_iter=1000,
            )
            self._meta_model.fit(meta_X, meta_y)

        # Final calibration on stacking output
        if self.meta_model_type == "lgbm":
            stacking_probs = self._meta_model.predict(meta_X)
        else:
            stacking_probs = self._meta_model.predict_proba(meta_X)[:, 1]

        self._stacking_calibrator = IsotonicCalibrator()
        self._stacking_calibrator.fit(stacking_probs, meta_y)

        # Compute final metrics
        cal_probs = self._stacking_calibrator.transform(stacking_probs)
        brier = float(np.mean((cal_probs - meta_y) ** 2))
        accuracy = float(np.mean((cal_probs > 0.5) == (meta_y == 1)))

        self._best_params = {
            "meta_model": self.meta_model_type,
            "n_base_models": n_base,
            "base_models": [name for name, _ in self.base_trainers],
        }

        logger.info("Stacking complete. OOS Brier: %.4f, Accuracy: %.4f", brier, accuracy)
        return {"brier": brier, "accuracy": accuracy, "n_oos": len(meta_y)}

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Predict P(Up) using the stacking ensemble."""
        if self._meta_model is None:
            msg = "Model not trained. Call fit() first."
            raise RuntimeError(msg)
        if hasattr(X, "to_numpy"):
            X = X.to_numpy()

        n_base = len(self.base_trainers)
        n_samples = len(X)
        meta_X = np.full((n_samples, n_base), 0.5)

        for model_idx, (name, trainer) in enumerate(self.base_trainers):
            raw = trainer.predict_proba(X)
            # Handle sequence-based models
            if len(raw) < n_samples:
                pad = np.full(n_samples - len(raw), 0.5)
                raw = np.concatenate([pad, raw])
            # Calibrate
            if name in self._base_calibrators:
                raw = self._base_calibrators[name].transform(raw)
            meta_X[:, model_idx] = raw

        if self.meta_model_type == "lgbm":
            stacking_probs = self._meta_model.predict(meta_X)
        else:
            stacking_probs = self._meta_model.predict_proba(meta_X)[:, 1]

        if self._stacking_calibrator is not None:
            return self._stacking_calibrator.transform(stacking_probs)
        return stacking_probs

    def save(self, path: Path) -> None:
        """Save entire stacking ensemble to directory."""
        if self._meta_model is None:
            msg = "No model to save"
            raise RuntimeError(msg)
        path.mkdir(parents=True, exist_ok=True)

        # Save each base model
        for name, trainer in self.base_trainers:
            base_dir = path / "base" / name
            trainer.save(base_dir)

        # Save base calibrators
        cal_dir = path / "calibrators"
        cal_dir.mkdir(parents=True, exist_ok=True)
        for name, cal in self._base_calibrators.items():
            cal.save(cal_dir / f"{name}.pkl")

        # Save meta model
        with open(path / "meta_model.pkl", "wb") as f:
            pickle.dump(self._meta_model, f)

        # Save stacking calibrator
        if self._stacking_calibrator is not None:
            self._stacking_calibrator.save(path / "stacking_calibrator.pkl")

        # Save metadata
        meta = {
            "meta_model_type": self.meta_model_type,
            "base_model_names": [name for name, _ in self.base_trainers],
            "best_params": self._best_params,
            "feature_names": self._feature_names,
        }
        (path / "meta.json").write_text(json.dumps(meta))
        logger.info("Stacking ensemble saved to %s", path)

    def load(self, path: Path) -> None:
        """Load stacking ensemble. Base trainers must be pre-instantiated."""
        meta = json.loads((path / "meta.json").read_text())
        self.meta_model_type = meta["meta_model_type"]
        self._best_params = meta["best_params"]
        self._feature_names = meta.get("feature_names", [])

        # Load base models
        for name, trainer in self.base_trainers:
            base_dir = path / "base" / name
            if base_dir.exists():
                trainer.load(base_dir)

        # Load base calibrators
        cal_dir = path / "calibrators"
        for name, _ in self.base_trainers:
            cal_path = cal_dir / f"{name}.pkl"
            if cal_path.exists():
                cal = IsotonicCalibrator()
                cal.load(cal_path)
                self._base_calibrators[name] = cal

        # Load meta model
        with open(path / "meta_model.pkl", "rb") as f:  # noqa: S301
            self._meta_model = pickle.load(f)  # noqa: S301

        # Load stacking calibrator
        cal_path = path / "stacking_calibrator.pkl"
        if cal_path.exists():
            self._stacking_calibrator = IsotonicCalibrator()
            self._stacking_calibrator.load(cal_path)

    @property
    def feature_importance(self) -> dict[str, int]:
        """Not meaningful for stacking — returns empty."""
        return {}

    @property
    def best_params(self) -> dict[str, Any]:
        return self._best_params


def _clone_trainer(trainer: Any) -> Any:
    """Create a fresh trainer instance with same config (no trained state)."""
    cls = type(trainer)
    # Extract constructor params from the trainer's attributes
    init_kwargs: dict[str, Any] = {}
    for attr in ("n_trials", "n_splits", "train_period", "test_period",
                 "seed", "seq_len", "use_gpu"):
        if hasattr(trainer, attr):
            init_kwargs[attr] = getattr(trainer, attr)
    # Map PulseTrainer-style attrs
    for attr in ("train_bars", "test_bars", "purge_period", "embargo_period"):
        if hasattr(trainer, attr):
            init_kwargs[attr] = getattr(trainer, attr)
    # BacktestEngine
    if hasattr(trainer, "_engine"):
        init_kwargs["backtest_engine"] = trainer._engine

    return cls(**init_kwargs)
