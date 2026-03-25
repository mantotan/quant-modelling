"""ALSTM Pulse trainer: bar-level walk-forward for intra-bar prediction.

Matches the :class:`PulseTrainer` interface (accepts ``IntraBarDataset``,
provides ``get_oos_predictions()``), NOT the Sentinel ``LGBMTrainer``
interface.  Uses shorter sequences (seq_len=8) since Pulse has at most
8 samples per bar.

Requires ``torch`` (optional gpu dependency).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
import optuna

from qm.backtest.validation.walk_forward import WalkForwardSplitter
from qm.model.targets.intrabar import IntraBarDataset
from qm.model.trainers.alstm_trainer import ALSTMTrainer
from qm.model.trainers.sequence import SequenceNormalizer, create_sequences

logger = logging.getLogger(__name__)
optuna.logging.set_verbosity(optuna.logging.WARNING)


class ALSTMPulseTrainer:
    """ALSTM trainer for Pulse intra-bar predictions.

    Key differences from :class:`ALSTMTrainer`:
    - Accepts ``IntraBarDataset`` (not flat X, y)
    - Walk-forward splits at BAR level via ``bar_indices``
    - Shorter ``seq_len=8`` (max samples per bar)
    - Provides ``get_oos_predictions()`` for ``TimeAwareCalibrator``
    """

    def __init__(
        self,
        n_trials: int = 30,
        n_splits: int = 8,
        train_bars: int = 5000,
        test_bars: int = 2000,
        purge_period: int = 12,
        embargo_period: int = 6,
        seed: int = 42,
        seq_len: int = 8,
        use_gpu: bool = True,
    ) -> None:
        self.n_trials = n_trials
        self.n_splits = n_splits
        self.train_bars = train_bars
        self.test_bars = test_bars
        self.purge_period = purge_period
        self.embargo_period = embargo_period
        self.seed = seed
        self.seq_len = seq_len
        self.use_gpu = use_gpu
        self._model: Any = None
        self._normalizer = SequenceNormalizer()
        self._best_params: dict[str, Any] = {}
        self._feature_names: list[str] = []
        # Delegate to a Sentinel-style trainer for the training loop
        self._trainer = ALSTMTrainer(
            n_trials=n_trials,
            n_splits=n_splits,
            train_period=train_bars,
            test_period=test_bars,
            seed=seed,
            seq_len=seq_len,
            use_gpu=use_gpu,
        )

    def fit(self, dataset: IntraBarDataset) -> dict[str, float]:
        """Train ALSTM on intra-bar dataset with bar-level walk-forward."""
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
                "hidden_size": trial.suggest_categorical(
                    "hidden_size", [32, 64, 128],
                ),
                "num_layers": trial.suggest_int("num_layers", 1, 2),
                "dropout": trial.suggest_float("dropout", 0.1, 0.4),
                "lr": trial.suggest_float("lr", 1e-4, 1e-2, log=True),
                "batch_size": trial.suggest_categorical(
                    "batch_size", [128, 256, 512],
                ),
                "weight_decay": trial.suggest_float(
                    "weight_decay", 1e-6, 1e-2, log=True,
                ),
            }

            all_oos_probs = np.zeros(len(y))
            all_oos_mask = np.zeros(len(y), dtype=bool)

            for bar_train_idx, bar_test_idx in splitter.split(n_bars):
                train_bars_set = unique_bars[bar_train_idx]
                test_bars_set = unique_bars[bar_test_idx]

                train_mask = np.isin(bar_indices, train_bars_set)
                test_mask = np.isin(bar_indices, test_bars_set)
                s_train = np.where(train_mask)[0]
                s_test = np.where(test_mask)[0]

                if len(s_train) < 200 or len(s_test) < 50:
                    continue

                # Normalize + sequence with bar boundaries
                norm = SequenceNormalizer()
                X_tr_n = norm.fit_transform(X[s_train])
                X_te_n = norm.transform(X[s_test])

                X_tr_seq, y_tr_seq, vi_tr = create_sequences(
                    X_tr_n, y[s_train], self.seq_len,
                    bar_indices=bar_indices[s_train],
                )
                X_te_seq, y_te_seq, vi_te = create_sequences(
                    X_te_n, y[s_test], self.seq_len,
                    bar_indices=bar_indices[s_test],
                )

                if len(X_tr_seq) < 50 or len(X_te_seq) < 10:
                    continue

                val_n = max(1, len(X_tr_seq) // 5)
                model = self._trainer._train_one_model(
                    X_tr_seq[:-val_n], y_tr_seq[:-val_n],
                    X_tr_seq[-val_n:], y_tr_seq[-val_n:],
                    params,
                )

                probs = self._trainer._predict_with_model(model, X_te_seq)
                flat_test_idx = s_test[vi_te]
                all_oos_probs[flat_test_idx] = probs
                all_oos_mask[flat_test_idx] = True

                import torch
                del model
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

            if not all_oos_mask.any():
                return 1.0

            oos_idx = np.where(all_oos_mask)[0]
            brier = float(np.mean((all_oos_probs[oos_idx] - y[oos_idx]) ** 2))
            accuracy = float(np.mean(
                (all_oos_probs[oos_idx] > 0.5) == (y[oos_idx] == 1),
            ))

            nonlocal best_metrics
            if not best_metrics or brier < best_metrics.get("brier", 1.0):
                best_metrics = {"brier": brier, "accuracy": accuracy}

            return brier

        study = optuna.create_study(
            direction="minimize",
            sampler=optuna.samplers.TPESampler(seed=self.seed),
        )
        study.optimize(objective, n_trials=self.n_trials, n_jobs=1)

        self._best_params = study.best_params
        logger.info("ALSTM Pulse HPO complete. Best Brier: %.4f", study.best_value)

        # Retrain on full data
        self._normalizer.fit(X)
        X_norm = self._normalizer.transform(X)
        X_seq, y_seq, _ = create_sequences(
            X_norm, y, self.seq_len, bar_indices=bar_indices,
        )

        val_n = max(1, len(X_seq) // 10)
        params = {
            "hidden_size": self._best_params.get("hidden_size", 64),
            "num_layers": self._best_params.get("num_layers", 1),
            "dropout": self._best_params.get("dropout", 0.2),
            "lr": self._best_params.get("lr", 1e-3),
            "batch_size": self._best_params.get("batch_size", 256),
            "weight_decay": self._best_params.get("weight_decay", 1e-4),
        }
        self._model = self._trainer._train_one_model(
            X_seq[:-val_n], y_seq[:-val_n],
            X_seq[-val_n:], y_seq[-val_n:],
            params,
        )

        return best_metrics

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Predict P(Up) from flat feature array."""
        if self._model is None:
            msg = "Model not trained. Call fit() first."
            raise RuntimeError(msg)
        X_norm = self._normalizer.transform(X.astype(np.float64))
        X_seq, _, _ = create_sequences(X_norm, np.zeros(len(X)), self.seq_len)
        if len(X_seq) == 0:
            return np.array([], dtype=np.float64)
        return self._trainer._predict_with_model(self._model, X_seq)

    def get_oos_predictions(
        self, dataset: IntraBarDataset,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Generate OOS predictions for calibration fitting."""
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

        params = {
            "hidden_size": self._best_params.get("hidden_size", 64),
            "num_layers": self._best_params.get("num_layers", 1),
            "dropout": self._best_params.get("dropout", 0.2),
            "lr": self._best_params.get("lr", 1e-3),
            "batch_size": self._best_params.get("batch_size", 256),
            "weight_decay": self._best_params.get("weight_decay", 1e-4),
        }

        oos_probs = np.zeros(len(y))
        oos_mask = np.zeros(len(y), dtype=bool)

        for bar_train_idx, bar_test_idx in splitter.split(n_bars):
            train_bars_set = unique_bars[bar_train_idx]
            test_bars_set = unique_bars[bar_test_idx]

            train_mask = np.isin(bar_indices, train_bars_set)
            test_mask = np.isin(bar_indices, test_bars_set)
            s_train = np.where(train_mask)[0]
            s_test = np.where(test_mask)[0]

            if len(s_train) < 200 or len(s_test) < 50:
                continue

            norm = SequenceNormalizer()
            X_tr_n = norm.fit_transform(X[s_train])
            X_te_n = norm.transform(X[s_test])

            X_tr_seq, y_tr_seq, _ = create_sequences(
                X_tr_n, y[s_train], self.seq_len,
                bar_indices=bar_indices[s_train],
            )
            X_te_seq, _, vi_te = create_sequences(
                X_te_n, y[s_test], self.seq_len,
                bar_indices=bar_indices[s_test],
            )

            if len(X_tr_seq) < 50 or len(X_te_seq) < 10:
                continue

            val_n = max(1, len(X_tr_seq) // 5)
            model = self._trainer._train_one_model(
                X_tr_seq[:-val_n], y_tr_seq[:-val_n],
                X_tr_seq[-val_n:], y_tr_seq[-val_n:],
                params,
            )

            probs = self._trainer._predict_with_model(model, X_te_seq)
            flat_idx = s_test[vi_te]
            oos_probs[flat_idx] = probs
            oos_mask[flat_idx] = True

        return oos_probs, y, oos_mask

    def save(self, path: Path) -> None:
        self._trainer._model = self._model
        self._trainer._normalizer = self._normalizer
        self._trainer._best_params = self._best_params
        self._trainer._feature_names = self._feature_names
        self._trainer.save(path)

    def load(self, path: Path) -> None:
        self._trainer.load(path)
        self._model = self._trainer._model
        self._normalizer = self._trainer._normalizer
        self._best_params = self._trainer._best_params
        self._feature_names = self._trainer._feature_names

    @property
    def feature_importance(self) -> dict[str, int]:
        return {}

    @property
    def best_params(self) -> dict[str, Any]:
        return self._best_params
