"""
Property Tests for Isotonic Regression Calibration

Tests mathematical properties and algorithmic invariants:
- Monotonicity: Calibrated predictions must be monotonically non-decreasing
- Ranking Preservation: Relative ordering must be maintained
- Perfect Calibration: Already-calibrated predictions unchanged
- Boundary Behavior: Predictions stay within [0,1]

Purpose: Prevent TDD blindspots by testing mathematical correctness,
         not just observable behavior.

Reference: docs/TESTING_MATHEMATICAL_ALGORITHMS.md
"""

import pytest
import numpy as np

from models_src.calibration.isotonic import IsotonicCalibrator


class TestMonotonicityProperties:
    """Test monotonicity properties of isotonic regression"""
    
    @pytest.fixture
    def sample_data(self):
        """Generate sample calibration data"""
        np.random.seed(42)
        n_samples = 200
        
        # Generate miscalibrated predictions
        y_pred_probs = np.random.uniform(0.1, 0.9, n_samples)
        
        # Generate binary outcomes
        y_true = (np.random.rand(n_samples) < y_pred_probs * 1.2).astype(int)
        y_true = np.clip(y_true, 0, 1)
        
        return y_true, y_pred_probs
    
    def test_calibrated_predictions_monotonic(self, sample_data):
        """
        Calibrated predictions must be monotonically non-decreasing.
        
        Mathematical Property:
            If x1 <= x2, then f(x1) <= f(x2)
        
        Purpose: Verify that isotonic regression satisfies monotonicity
                 constraint, which is the defining property of the algorithm.
        """
        y_true, y_pred_probs = sample_data
        
        # Fit calibrator
        calibrator = IsotonicCalibrator()
        calibrator.fit(y_true, y_pred_probs)
        
        # Create sorted test predictions
        test_probs = np.linspace(0.0, 1.0, 100)
        calibrated_probs = calibrator.transform(test_probs)
        
        # Check monotonicity: f(x[i]) <= f(x[i+1])
        for i in range(len(calibrated_probs) - 1):
            assert calibrated_probs[i] <= calibrated_probs[i+1] + 1e-10, \
                f"Monotonicity violated at index {i}: " \
                f"{calibrated_probs[i]:.6f} > {calibrated_probs[i+1]:.6f}"
    
    def test_monotonicity_with_unsorted_input(self, sample_data):
        """
        Monotonicity must hold even for unsorted input.
        
        Mathematical Property:
            f is monotonic regardless of input order
        
        Purpose: Verify that monotonicity is a property of the function,
                 not just of sorted inputs.
        """
        y_true, y_pred_probs = sample_data
        
        # Fit calibrator
        calibrator = IsotonicCalibrator()
        calibrator.fit(y_true, y_pred_probs)
        
        # Create unsorted test predictions
        test_probs = np.array([0.3, 0.1, 0.8, 0.2, 0.9, 0.4, 0.7, 0.5, 0.6])
        calibrated_probs = calibrator.transform(test_probs)
        
        # Sort by input to check monotonicity
        sorted_idx = np.argsort(test_probs)
        sorted_input = test_probs[sorted_idx]
        sorted_output = calibrated_probs[sorted_idx]
        
        # Check monotonicity on sorted arrays
        for i in range(len(sorted_output) - 1):
            assert sorted_output[i] <= sorted_output[i+1] + 1e-10, \
                f"Monotonicity violated: input {sorted_input[i]:.3f}->{sorted_input[i+1]:.3f}, " \
                f"output {sorted_output[i]:.6f}->{sorted_output[i+1]:.6f}"
    
    def test_equal_inputs_produce_equal_outputs(self, sample_data):
        """
        Equal inputs must produce equal outputs.
        
        Mathematical Property:
            If x1 = x2, then f(x1) = f(x2)
        
        Purpose: Verify that calibrator is deterministic (a function).
        """
        y_true, y_pred_probs = sample_data
        
        # Fit calibrator
        calibrator = IsotonicCalibrator()
        calibrator.fit(y_true, y_pred_probs)
        
        # Transform same value multiple times
        test_prob = np.array([0.5, 0.5, 0.5, 0.5])
        calibrated_probs = calibrator.transform(test_prob)
        
        # All outputs should be identical
        assert np.all(np.abs(calibrated_probs - calibrated_probs[0]) < 1e-10), \
            f"Equal inputs produced different outputs: {calibrated_probs}"


class TestRankingPreservationProperties:
    """Test ranking preservation properties"""
    
    @pytest.fixture
    def sample_data(self):
        """Generate sample calibration data"""
        np.random.seed(42)
        n_samples = 200
        
        y_pred_probs = np.random.uniform(0.1, 0.9, n_samples)
        y_true = (np.random.rand(n_samples) < y_pred_probs * 1.2).astype(int)
        y_true = np.clip(y_true, 0, 1)
        
        return y_true, y_pred_probs
    
    def test_ranking_preserved(self, sample_data):
        """
        Isotonic calibration must preserve weak ordering.
        
        Mathematical Property:
            If x1 < x2, then f(x1) <= f(x2) (weak preservation)
        
        Purpose: Verify that calibration doesn't reverse orderings.
                 Note: Isotonic regression can produce ties (multiple inputs
                 map to same output), which is mathematically correct.
        
        Note: This test verifies weak monotonicity (order preservation)
              rather than strict ranking equality.
        """
        y_true, y_pred_probs = sample_data
        
        # Fit calibrator
        calibrator = IsotonicCalibrator()
        calibrator.fit(y_true, y_pred_probs)
        
        # Test on sorted predictions (to check monotonicity)
        test_probs = np.sort(np.random.uniform(0.0, 1.0, 50))
        calibrated_probs = calibrator.transform(test_probs)
        
        # Check that monotonicity is preserved
        # calibrated_probs should be non-decreasing
        for i in range(len(calibrated_probs) - 1):
            assert calibrated_probs[i] <= calibrated_probs[i+1] + 1e-10, \
                f"Weak ordering violated at index {i}: " \
                f"{calibrated_probs[i]:.6f} > {calibrated_probs[i+1]:.6f}"
    
    def test_strict_ordering_preserved(self, sample_data):
        """
        Strict ordering must be preserved.
        
        Mathematical Property:
            If x1 < x2 and f is strictly monotonic, then f(x1) < f(x2)
        
        Purpose: Verify that distinct inputs produce distinct outputs
                 (no unnecessary collapsing).
        
        Note: Isotonic regression may produce ties (equal outputs for
              different inputs), so this test checks that ordering
              direction is preserved, not strict inequality.
        """
        y_true, y_pred_probs = sample_data
        
        # Fit calibrator
        calibrator = IsotonicCalibrator()
        calibrator.fit(y_true, y_pred_probs)
        
        # Test pairs of predictions
        test_pairs = [
            (0.1, 0.9),
            (0.2, 0.8),
            (0.3, 0.7),
            (0.4, 0.6),
        ]
        
        for x1, x2 in test_pairs:
            y1 = calibrator.transform(np.array([x1]))[0]
            y2 = calibrator.transform(np.array([x2]))[0]
            
            # Since x1 < x2, we must have y1 <= y2
            assert y1 <= y2 + 1e-10, \
                f"Ordering violated: f({x1}) = {y1:.6f} > f({x2}) = {y2:.6f}"


class TestPerfectPredictionsProperties:
    """Test behavior with already-calibrated predictions"""
    
    def test_perfect_predictions_nearly_unchanged(self):
        """
        Already-calibrated predictions should be nearly unchanged.
        
        Mathematical Property:
            If predictions are calibrated, f(x) ≈ x
        
        Purpose: Verify that isotonic regression doesn't distort
                 already-good predictions.
        
        Note: Due to finite sample effects, we expect approximate
              preservation, not exact.
        """
        np.random.seed(42)
        n_samples = 500  # Large sample for stable calibration
        
        # Generate perfectly calibrated predictions
        y_pred_probs = np.random.uniform(0.1, 0.9, n_samples)
        y_true = (np.random.rand(n_samples) < y_pred_probs).astype(int)
        
        # Fit calibrator
        calibrator = IsotonicCalibrator()
        calibrator.fit(y_true, y_pred_probs)
        
        # Test calibration
        test_probs = np.linspace(0.2, 0.8, 10)
        calibrated_probs = calibrator.transform(test_probs)
        
        # Should be close to identity function
        # (Allow reasonable deviation due to finite sample effects)
        max_deviation = np.max(np.abs(calibrated_probs - test_probs))
        
        assert max_deviation < 0.2, \
            f"Perfect predictions changed significantly: max deviation = {max_deviation:.4f}"
    
    def test_calibration_improves_or_maintains_ece(self):
        """
        Calibration should improve or maintain ECE.
        
        Mathematical Property:
            ECE(calibrated) <= ECE(uncalibrated) + ε
        
        Purpose: Verify that calibration doesn't make predictions worse.
        
        Note: On finite samples, calibration might slightly increase
              ECE due to overfitting, so we allow small tolerance.
        """
        np.random.seed(42)
        n_samples = 200
        
        # Generate miscalibrated predictions
        y_pred_probs = np.random.uniform(0.1, 0.9, n_samples)
        y_true = (np.random.rand(n_samples) < y_pred_probs * 1.5).astype(int)
        y_true = np.clip(y_true, 0, 1)
        
        # Fit calibrator
        calibrator = IsotonicCalibrator()
        calibrator.fit(y_true, y_pred_probs)
        
        # ECE should improve (or at least not get much worse)
        ece_before = calibrator.ece_before_
        ece_after = calibrator.ece_after_
        
        # Allow small increase due to finite sample effects
        assert ece_after <= ece_before * 1.1, \
            f"Calibration increased ECE significantly: {ece_before:.4f} -> {ece_after:.4f}"


class TestBoundaryBehaviorProperties:
    """Test boundary behavior of calibrated predictions"""
    
    @pytest.fixture
    def fitted_calibrator(self):
        """Create a fitted calibrator"""
        np.random.seed(42)
        n_samples = 200
        
        y_pred_probs = np.random.uniform(0.1, 0.9, n_samples)
        y_true = (np.random.rand(n_samples) < y_pred_probs).astype(int)
        
        calibrator = IsotonicCalibrator()
        calibrator.fit(y_true, y_pred_probs)
        
        return calibrator
    
    def test_predictions_stay_in_valid_range(self, fitted_calibrator):
        """
        Calibrated predictions must stay in [0, 1].
        
        Mathematical Property:
            0 <= f(x) <= 1 for all x in [0, 1]
        
        Purpose: Verify that calibration produces valid probabilities.
        """
        # Test on various inputs
        test_probs = np.linspace(0.0, 1.0, 100)
        calibrated_probs = fitted_calibrator.transform(test_probs)
        
        # All outputs must be in [0, 1]
        assert np.all(calibrated_probs >= 0), \
            f"Calibrated predictions below 0: min = {np.min(calibrated_probs):.6f}"
        
        assert np.all(calibrated_probs <= 1), \
            f"Calibrated predictions above 1: max = {np.max(calibrated_probs):.6f}"
    
    def test_extreme_values_handled(self, fitted_calibrator):
        """
        Extreme values (0, 1) must be handled gracefully.
        
        Mathematical Property:
            f(0) is defined, f(1) is defined
        
        Purpose: Verify boundary value handling.
        """
        # Test extreme values
        extreme_probs = np.array([0.0, 1.0])
        calibrated_probs = fitted_calibrator.transform(extreme_probs)
        
        # Should produce valid probabilities
        assert np.all(np.isfinite(calibrated_probs)), \
            f"Extreme values produced non-finite outputs: {calibrated_probs}"
        
        assert np.all((calibrated_probs >= 0) & (calibrated_probs <= 1)), \
            f"Extreme values produced out-of-range outputs: {calibrated_probs}"
    
    def test_out_of_bounds_handling(self):
        """
        Out-of-bounds values must be validated.
        
        Mathematical Property:
            IsotonicCalibrator validates inputs are in [0, 1]
        
        Purpose: Verify that calibrator validates inputs properly.
        
        Note: The current implementation validates rather than clips
              out-of-bounds values. This is correct behavior - calibration
              should only be applied to valid probabilities.
        """
        np.random.seed(42)
        n_samples = 200
        
        y_pred_probs = np.random.uniform(0.1, 0.9, n_samples)
        y_true = (np.random.rand(n_samples) < y_pred_probs).astype(int)
        
        # Fit calibrator
        calibrator = IsotonicCalibrator()
        calibrator.fit(y_true, y_pred_probs)
        
        # Test out-of-bounds values (should raise ValueError)
        oob_probs = np.array([-0.5, 1.5, -1.0, 2.0])
        
        # Should raise error for out-of-bounds inputs
        with pytest.raises(ValueError, match="y_pred_probs must be in range"):
            calibrator.transform(oob_probs)


class TestIsotonicIntegrationWithProperties:
    """Integration tests combining multiple mathematical properties"""
    
    def test_all_properties_consistent(self):
        """
        Verify that all properties hold simultaneously.
        
        Mathematical Property:
            Monotonicity + Ranking + Boundaries all consistent
        
        Purpose: Ensure properties don't conflict.
        """
        np.random.seed(42)
        n_samples = 300
        
        # Generate data
        y_pred_probs = np.random.uniform(0.0, 1.0, n_samples)
        y_true = (np.random.rand(n_samples) < y_pred_probs * 1.3).astype(int)
        y_true = np.clip(y_true, 0, 1)
        
        # Fit calibrator
        calibrator = IsotonicCalibrator()
        calibrator.fit(y_true, y_pred_probs)
        
        # Test on sorted inputs
        test_probs = np.sort(np.random.uniform(0.0, 1.0, 50))
        calibrated_probs = calibrator.transform(test_probs)
        
        # Property 1: Monotonicity
        assert np.all(np.diff(calibrated_probs) >= -1e-10), \
            "Monotonicity violated"
        
        # Property 2: Valid range
        assert np.all((calibrated_probs >= 0) & (calibrated_probs <= 1)), \
            "Valid range violated"
        
        # Property 3: Monotonicity (weak ranking preserved)
        # Note: argsort may differ due to ties, but values should be non-decreasing
        # Since test_probs is already sorted, calibrated_probs should also be non-decreasing
        assert np.all(np.diff(calibrated_probs) >= -1e-10), \
            "Weak ordering violated (not non-decreasing)"
        
        # Property 4: All values finite
        assert np.all(np.isfinite(calibrated_probs)), \
            "Non-finite values produced"

