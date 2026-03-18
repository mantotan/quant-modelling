"""Tests for Sentinel + Pulse ensemble combination strategies."""

from __future__ import annotations

import numpy as np
import pytest

from qm.model.ensemble.predictor import (
    BayesianUpdateStrategy,
    CombinationStrategy,
    TimeWeightedStrategy,
    combine_predictions_batch,
    _clip,
)


# ── Strategy unit tests ──────────────────────────────────────────────


class TestBayesianUpdateStrategy:
    def setup_method(self):
        self.strategy = BayesianUpdateStrategy(ramp_pct=0.10)

    def test_at_t0_no_pulse_equals_sentinel(self):
        """At t=0 with no Pulse data, combined = sentinel exactly."""
        result = self.strategy.combine(
            sentinel_prob=0.55, pulse_prob=None,
            time_elapsed_pct=0.0, market_prob=0.50,
        )
        assert abs(result - 0.55) < 1e-6

    def test_at_t0_with_pulse_dampened(self):
        """At t=0, even with Pulse data, dampening makes LR ~1.0."""
        result = self.strategy.combine(
            sentinel_prob=0.55, pulse_prob=0.70,
            time_elapsed_pct=0.0, market_prob=0.50,
        )
        # At t=0, alpha=0, so lr_dampened=1.0, combined=sentinel
        assert abs(result - 0.55) < 1e-6

    def test_pulse_updates_away_from_sentinel(self):
        """After ramp, Pulse evidence shifts combined away from Sentinel."""
        result = self.strategy.combine(
            sentinel_prob=0.55, pulse_prob=0.75,
            time_elapsed_pct=0.50, market_prob=0.50,
        )
        # Pulse says 75%, Sentinel says 55%
        # Combined should be between them, closer to Pulse after ramp
        assert result > 0.55
        assert result < 0.99

    def test_no_new_info_lr_near_one(self):
        """When Pulse agrees with Sentinel exactly, combined ~= Sentinel."""
        result = self.strategy.combine(
            sentinel_prob=0.60, pulse_prob=0.60,
            time_elapsed_pct=0.50, market_prob=0.50,
        )
        assert abs(result - 0.60) < 1e-6

    def test_output_clipped(self):
        """Combined output is always in [0.01, 0.99]."""
        # Extreme inputs
        result_high = self.strategy.combine(
            sentinel_prob=0.99, pulse_prob=0.99,
            time_elapsed_pct=0.80, market_prob=0.50,
        )
        assert result_high <= 0.99

        result_low = self.strategy.combine(
            sentinel_prob=0.01, pulse_prob=0.01,
            time_elapsed_pct=0.80, market_prob=0.50,
        )
        assert result_low >= 0.01

    def test_ramp_gradual(self):
        """At t=0.05 (half ramp), update is dampened by 50%."""
        # Full update at t=0.20 (past ramp)
        full = self.strategy.combine(
            sentinel_prob=0.50, pulse_prob=0.70,
            time_elapsed_pct=0.20, market_prob=0.50,
        )
        # Half update at t=0.05
        half = self.strategy.combine(
            sentinel_prob=0.50, pulse_prob=0.70,
            time_elapsed_pct=0.05, market_prob=0.50,
        )
        # Half should be closer to sentinel (0.50) than full
        assert abs(half - 0.50) < abs(full - 0.50)


class TestTimeWeightedStrategy:
    def setup_method(self):
        self.strategy = TimeWeightedStrategy(min_sentinel_weight=0.20)

    def test_at_t0_mostly_sentinel(self):
        """At t=0, Sentinel weight = 1.0."""
        result = self.strategy.combine(
            sentinel_prob=0.55, pulse_prob=0.70,
            time_elapsed_pct=0.0, market_prob=0.50,
        )
        assert abs(result - 0.55) < 1e-6

    def test_at_t08_mostly_pulse(self):
        """At t=0.8, Sentinel weight = 0.20 (min), Pulse = 0.80."""
        result = self.strategy.combine(
            sentinel_prob=0.55, pulse_prob=0.70,
            time_elapsed_pct=0.80, market_prob=0.50,
        )
        expected = 0.20 * 0.55 + 0.80 * 0.70
        assert abs(result - expected) < 1e-6

    def test_no_pulse_returns_sentinel(self):
        result = self.strategy.combine(
            sentinel_prob=0.60, pulse_prob=None,
            time_elapsed_pct=0.50, market_prob=0.50,
        )
        assert abs(result - 0.60) < 1e-6

    def test_midpoint_interpolation(self):
        """At t=0.5, Sentinel weight=0.5, Pulse weight=0.5."""
        result = self.strategy.combine(
            sentinel_prob=0.40, pulse_prob=0.60,
            time_elapsed_pct=0.50, market_prob=0.50,
        )
        expected = 0.50 * 0.40 + 0.50 * 0.60
        assert abs(result - expected) < 1e-6


class TestStrategiesAgree:
    def test_strong_agreement(self):
        """Both strategies agree when models strongly agree."""
        bayesian = BayesianUpdateStrategy()
        tw = TimeWeightedStrategy()

        # Both models say 70% at t=0.5
        b_result = bayesian.combine(0.70, 0.70, 0.50, 0.50)
        tw_result = tw.combine(0.70, 0.70, 0.50, 0.50)

        # Should be very close to 0.70
        assert abs(b_result - 0.70) < 0.01
        assert abs(tw_result - 0.70) < 0.01


# ── Batch combination tests ──────────────────────────────────────────


class TestCombinePredictionsBatch:
    def test_basic_batch(self):
        """Batch combination produces correct shape and values."""
        sentinel_probs = np.array([0.55, 0.60, 0.50])
        pulse_probs = np.array([0.60, 0.65, 0.55, 0.70, 0.60, 0.52])
        time_pcts = np.array([0.10, 0.40, 0.10, 0.40, 0.10, 0.40])
        bar_indices = np.array([0, 0, 1, 1, 2, 2])
        market_probs = np.full(6, 0.50)
        strategy = BayesianUpdateStrategy()

        combined = combine_predictions_batch(
            sentinel_probs, pulse_probs, time_pcts,
            bar_indices, market_probs, strategy,
        )

        assert combined.shape == (6,)
        assert np.all(combined >= 0.01)
        assert np.all(combined <= 0.99)

    def test_batch_matches_individual(self):
        """Batch result matches individual calls."""
        strategy = TimeWeightedStrategy()
        sentinel_probs = np.array([0.55])
        pulse_probs = np.array([0.65])
        time_pcts = np.array([0.40])
        bar_indices = np.array([0])
        market_probs = np.array([0.50])

        batch_result = combine_predictions_batch(
            sentinel_probs, pulse_probs, time_pcts,
            bar_indices, market_probs, strategy,
        )
        individual = strategy.combine(0.55, 0.65, 0.40, 0.50)

        assert abs(batch_result[0] - individual) < 1e-10


# ── Protocol compliance ──────────────────────────────────────────────


class TestProtocolCompliance:
    def test_bayesian_is_combination_strategy(self):
        assert isinstance(BayesianUpdateStrategy(), CombinationStrategy)

    def test_time_weighted_is_combination_strategy(self):
        assert isinstance(TimeWeightedStrategy(), CombinationStrategy)


# ── Disagreement filter tests ────────────────────────────────────────


class TestDisagreementFilter:
    def test_time_dependent_threshold(self):
        """Early bar allows more disagreement than late bar."""
        from qm.model.signals import SignalGenerator

        sg = SignalGenerator()

        # Early bar (t=0.003): max allowed ~0.40
        ok_early, _ = sg.check_model_agreement(0.50, 0.85, 0.003)
        assert ok_early  # 0.35 < 0.40

        # Late bar (t=0.80): max allowed ~0.15
        ok_late, _ = sg.check_model_agreement(0.50, 0.70, 0.80)
        assert not ok_late  # 0.20 > 0.15

    def test_agreement_passes(self):
        from qm.model.signals import SignalGenerator

        sg = SignalGenerator()
        ok, disagreement = sg.check_model_agreement(0.55, 0.60, 0.50)
        assert ok
        assert abs(disagreement - 0.05) < 1e-10


# ── Clip utility ─────────────────────────────────────────────────────


class TestClip:
    def test_clip_normal(self):
        assert _clip(0.50) == 0.50

    def test_clip_low(self):
        assert _clip(0.001) == 0.01

    def test_clip_high(self):
        assert _clip(0.999) == 0.99

    def test_clip_boundary(self):
        assert _clip(0.01) == 0.01
        assert _clip(0.99) == 0.99
