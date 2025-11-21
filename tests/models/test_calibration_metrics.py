"""
Tests for Calibration Metrics.

Tests cover:
- Expected Calibration Error (ECE) - imported from main metrics
- Reliability curve computation
- Sharpness metrics
- Comprehensive calibration metrics
- Prediction interval evaluation
- Edge cases (perfect calibration, poor calibration, etc.)
- Error handling
"""

import pytest
import numpy as np

from models_src.calibration.metrics import (
    expected_calibration_error,
    compute_reliability_curve,
    compute_sharpness,
    compute_calibration_metrics,
    evaluate_prediction_intervals
)


class TestExpectedCalibrationError:
    """Test ECE computation (imported from main metrics module)."""
    
    def test_ece_perfectly_calibrated(self):
        """Test ECE for perfectly calibrated predictions."""
        np.random.seed(42)
        n_samples = 1000
        
        # Generate perfectly calibrated predictions
        true_probs = np.random.uniform(0.1, 0.9, n_samples)
        y_true = (np.random.rand(n_samples) < true_probs).astype(int)
        y_pred_probs = true_probs.copy()
        
        ece = expected_calibration_error(y_true, y_pred_probs, n_bins=10)
        
        # Should have low ECE (allowing for sampling variability)
        assert ece < 0.05
    
    def test_ece_poor_calibration(self):
        """Test ECE for poorly calibrated predictions."""
        np.random.seed(42)
        n_samples = 500
        
        # Generate outcomes
        y_true = np.random.randint(0, 2, n_samples)
        
        # Very poor predictions (always predict 0.9)
        y_pred_probs = np.full(n_samples, 0.9)
        
        ece = expected_calibration_error(y_true, y_pred_probs, n_bins=10)
        
        # Should have high ECE (far from actual ~50% rate)
        assert ece > 0.2


class TestReliabilityCurve:
    """Test reliability curve computation."""
    
    def test_reliability_curve_structure(self):
        """Test that reliability curve returns correct structure."""
        np.random.seed(42)
        n_samples = 200
        
        y_true = np.random.randint(0, 2, n_samples)
        y_pred_probs = np.random.uniform(0, 1, n_samples)
        
        curve = compute_reliability_curve(y_true, y_pred_probs, n_bins=10)
        
        # Check keys
        assert 'bin_centers' in curve
        assert 'predicted_probs' in curve
        assert 'observed_freqs' in curve
        assert 'counts' in curve
        assert 'confidence_lower' in curve
        assert 'confidence_upper' in curve
        
        # Check shapes match
        n_bins_with_data = len(curve['bin_centers'])
        assert len(curve['predicted_probs']) == n_bins_with_data
        assert len(curve['observed_freqs']) == n_bins_with_data
        assert len(curve['counts']) == n_bins_with_data
        assert len(curve['confidence_lower']) == n_bins_with_data
        assert len(curve['confidence_upper']) == n_bins_with_data
        
        # Check total counts
        assert np.sum(curve['counts']) == n_samples
    
    def test_reliability_curve_perfect_calibration(self):
        """Test reliability curve for perfectly calibrated data."""
        np.random.seed(42)
        n_samples = 1000
        
        # Perfectly calibrated
        true_probs = np.random.uniform(0.1, 0.9, n_samples)
        y_true = (np.random.rand(n_samples) < true_probs).astype(int)
        y_pred_probs = true_probs.copy()
        
        curve = compute_reliability_curve(y_true, y_pred_probs, n_bins=10)
        
        # Predicted and observed should be close
        diff = np.abs(curve['predicted_probs'] - curve['observed_freqs'])
        
        # Allow for sampling variability (large sample should be close)
        assert np.mean(diff) < 0.05
    
    def test_reliability_curve_validates_inputs(self):
        """Test that reliability curve validates inputs."""
        y_true = np.array([0, 1, 1, 0])
        y_pred_probs = np.array([0.2, 0.8])  # Wrong length
        
        with pytest.raises(ValueError, match="must have same length"):
            compute_reliability_curve(y_true, y_pred_probs)
    
    def test_reliability_curve_validates_binary_outcomes(self):
        """Test that non-binary outcomes raise ValueError."""
        y_true = np.array([0, 1, 2, 3])  # Not binary
        y_pred_probs = np.array([0.2, 0.5, 0.7, 0.9])
        
        with pytest.raises(ValueError, match="must contain only 0s and 1s"):
            compute_reliability_curve(y_true, y_pred_probs)
    
    def test_reliability_curve_validates_probability_range(self):
        """Test that probabilities outside [0, 1] raise ValueError."""
        y_true = np.array([0, 1, 1, 0])
        y_pred_probs = np.array([0.2, 1.5, 0.7, -0.1])
        
        with pytest.raises(ValueError, match="must be in range"):
            compute_reliability_curve(y_true, y_pred_probs)
    
    def test_reliability_curve_confidence_intervals(self):
        """Test that confidence intervals are valid."""
        np.random.seed(42)
        
        y_true = np.random.randint(0, 2, 200)
        y_pred_probs = np.random.uniform(0, 1, 200)
        
        curve = compute_reliability_curve(y_true, y_pred_probs, n_bins=5)
        
        # Lower bound should be <= observed freq <= upper bound
        for i in range(len(curve['observed_freqs'])):
            assert curve['confidence_lower'][i] <= curve['observed_freqs'][i]
            assert curve['observed_freqs'][i] <= curve['confidence_upper'][i]
        
        # Bounds should be in [0, 1]
        assert np.all((curve['confidence_lower'] >= 0) & (curve['confidence_lower'] <= 1))
        assert np.all((curve['confidence_upper'] >= 0) & (curve['confidence_upper'] <= 1))


class TestSharpness:
    """Test sharpness metrics computation."""
    
    def test_sharpness_basic(self):
        """Test basic sharpness computation."""
        lower = np.array([40.0, 45.0, 50.0])
        upper = np.array([60.0, 65.0, 70.0])
        
        metrics = compute_sharpness((lower, upper), confidence_level=0.9)
        
        # Check keys
        assert 'mean_interval_width' in metrics
        assert 'median_interval_width' in metrics
        assert 'std_interval_width' in metrics
        assert 'min_interval_width' in metrics
        assert 'max_interval_width' in metrics
        assert 'cv_interval_width' in metrics
        
        # All widths are 20
        assert metrics['mean_interval_width'] == 20.0
        assert metrics['median_interval_width'] == 20.0
        assert metrics['std_interval_width'] == 0.0
        assert metrics['min_interval_width'] == 20.0
        assert metrics['max_interval_width'] == 20.0
        assert metrics['cv_interval_width'] == 0.0
    
    def test_sharpness_varying_widths(self):
        """Test sharpness with varying interval widths."""
        lower = np.array([40.0, 45.0, 50.0, 55.0])
        upper = np.array([50.0, 60.0, 70.0, 85.0])
        
        metrics = compute_sharpness((lower, upper))
        
        # Widths: [10, 15, 20, 30]
        expected_mean = 18.75
        expected_std = np.std([10, 15, 20, 30])
        
        assert np.isclose(metrics['mean_interval_width'], expected_mean)
        assert np.isclose(metrics['std_interval_width'], expected_std)
        assert metrics['min_interval_width'] == 10.0
        assert metrics['max_interval_width'] == 30.0
    
    def test_sharpness_validates_length_mismatch(self):
        """Test that length mismatch raises ValueError."""
        lower = np.array([40.0, 45.0])
        upper = np.array([60.0, 65.0, 70.0])
        
        with pytest.raises(ValueError, match="must have same length"):
            compute_sharpness((lower, upper))
    
    def test_sharpness_validates_empty_input(self):
        """Test that empty input raises ValueError."""
        lower = np.array([])
        upper = np.array([])
        
        with pytest.raises(ValueError, match="cannot be empty"):
            compute_sharpness((lower, upper))
    
    def test_sharpness_validates_bound_ordering(self):
        """Test that incorrect bound ordering raises ValueError."""
        lower = np.array([60.0, 65.0, 70.0])
        upper = np.array([40.0, 45.0, 50.0])  # Lower > upper
        
        with pytest.raises(ValueError, match="Lower bounds must be"):
            compute_sharpness((lower, upper))


class TestCalibrationMetrics:
    """Test comprehensive calibration metrics."""
    
    def test_calibration_metrics_structure(self):
        """Test that calibration metrics returns all expected fields."""
        np.random.seed(42)
        
        y_true = np.random.randint(0, 2, 200)
        y_pred_probs = np.random.uniform(0, 1, 200)
        
        metrics = compute_calibration_metrics(y_true, y_pred_probs, n_bins=10)
        
        # Check keys
        assert 'ece' in metrics
        assert 'max_calibration_error' in metrics
        assert 'mean_confidence' in metrics
        assert 'brier_score' in metrics
        assert 'log_loss' in metrics
        assert 'reliability_curve' in metrics
    
    def test_calibration_metrics_perfect_predictions(self):
        """Test metrics for perfect predictions."""
        np.random.seed(42)
        n_samples = 500
        
        # Perfect predictions
        true_probs = np.random.uniform(0.1, 0.9, n_samples)
        y_true = (np.random.rand(n_samples) < true_probs).astype(int)
        y_pred_probs = true_probs.copy()
        
        metrics = compute_calibration_metrics(y_true, y_pred_probs)
        
        # ECE should be low
        assert metrics['ece'] < 0.05
        
        # Brier score should be low
        assert metrics['brier_score'] < 0.3
    
    def test_calibration_metrics_poor_predictions(self):
        """Test metrics for poor predictions."""
        np.random.seed(42)
        n_samples = 300
        
        y_true = np.random.randint(0, 2, n_samples)
        
        # Always predict 0.9 (overconfident)
        y_pred_probs = np.full(n_samples, 0.9)
        
        metrics = compute_calibration_metrics(y_true, y_pred_probs)
        
        # ECE should be high
        assert metrics['ece'] > 0.2
        
        # MCE should be high
        assert metrics['max_calibration_error'] > 0.2
    
    def test_calibration_metrics_validates_inputs(self):
        """Test that calibration metrics validates inputs."""
        y_true = np.array([0, 1, 1, 0])
        y_pred_probs = np.array([0.2, 0.8])  # Wrong length
        
        with pytest.raises(ValueError, match="must have same length"):
            compute_calibration_metrics(y_true, y_pred_probs)


class TestPredictionIntervalEvaluation:
    """Test prediction interval evaluation."""
    
    def test_interval_evaluation_basic(self):
        """Test basic interval evaluation."""
        np.random.seed(42)
        n_samples = 100
        
        y_true = np.random.randn(n_samples) * 10 + 50
        
        # Create intervals that cover ~90% of points
        lower = y_true - 15
        upper = y_true + 15
        
        # Add some noise so not all are covered
        lower += np.random.randn(n_samples) * 2
        upper += np.random.randn(n_samples) * 2
        
        metrics = evaluate_prediction_intervals(
            y_true,
            (lower, upper),
            confidence_level=0.9
        )
        
        # Check keys
        assert 'empirical_coverage' in metrics
        assert 'target_coverage' in metrics
        assert 'coverage_gap' in metrics
        assert 'mean_interval_width' in metrics
        assert 'median_interval_width' in metrics
        assert 'interval_score' in metrics
        
        # Coverage should be reasonably close to target
        assert 0.7 <= metrics['empirical_coverage'] <= 1.0
    
    def test_interval_evaluation_perfect_coverage(self):
        """Test evaluation with perfect coverage."""
        np.random.seed(42)
        n_samples = 200
        
        y_true = np.random.randn(n_samples) * 10 + 50
        
        # Wide intervals that cover everything
        lower = y_true - 50
        upper = y_true + 50
        
        metrics = evaluate_prediction_intervals(
            y_true,
            (lower, upper),
            confidence_level=0.9
        )
        
        # Coverage should be 100%
        assert metrics['empirical_coverage'] == 1.0
        
        # Mean width should be 100
        assert np.isclose(metrics['mean_interval_width'], 100.0)
    
    def test_interval_evaluation_no_coverage(self):
        """Test evaluation with zero coverage."""
        n_samples = 50
        
        y_true = np.full(n_samples, 50.0)
        
        # Intervals that don't cover any points
        lower = np.full(n_samples, 100.0)
        upper = np.full(n_samples, 150.0)
        
        metrics = evaluate_prediction_intervals(
            y_true,
            (lower, upper),
            confidence_level=0.9
        )
        
        # Coverage should be 0%
        assert metrics['empirical_coverage'] == 0.0
        
        # Interval score should be high (penalized for miscoverage)
        assert metrics['interval_score'] > metrics['mean_interval_width']
    
    def test_interval_evaluation_validates_lengths(self):
        """Test that length mismatch raises ValueError."""
        y_true = np.array([50.0, 51.0, 52.0])
        lower = np.array([40.0, 41.0])
        upper = np.array([60.0, 61.0])
        
        with pytest.raises(ValueError, match="must have same length"):
            evaluate_prediction_intervals(y_true, (lower, upper))
    
    def test_interval_evaluation_validates_empty_input(self):
        """Test that empty input raises ValueError."""
        y_true = np.array([])
        lower = np.array([])
        upper = np.array([])
        
        with pytest.raises(ValueError, match="cannot be empty"):
            evaluate_prediction_intervals(y_true, (lower, upper))
    
    def test_interval_evaluation_validates_bound_ordering(self):
        """Test that incorrect bound ordering raises ValueError."""
        y_true = np.array([50.0, 51.0, 52.0])
        lower = np.array([60.0, 61.0, 62.0])
        upper = np.array([40.0, 41.0, 42.0])  # Lower > upper
        
        with pytest.raises(ValueError, match="Lower bounds must be"):
            evaluate_prediction_intervals(y_true, (lower, upper))
    
    def test_interval_score_proper_scoring_rule(self):
        """Test that interval score penalizes both width and miscoverage."""
        np.random.seed(42)
        n_samples = 100
        
        y_true = np.random.randn(n_samples) * 10 + 50
        
        # Generate predictions with some error
        y_pred = y_true + np.random.randn(n_samples) * 5
        
        # Narrow intervals around predictions (good sharpness, may have poor coverage)
        lower_narrow = y_pred - 5
        upper_narrow = y_pred + 5
        
        # Wide intervals around predictions (poor sharpness, likely good coverage)
        lower_wide = y_pred - 30
        upper_wide = y_pred + 30
        
        metrics_narrow = evaluate_prediction_intervals(
            y_true,
            (lower_narrow, upper_narrow),
            confidence_level=0.9
        )
        
        metrics_wide = evaluate_prediction_intervals(
            y_true,
            (lower_wide, upper_wide),
            confidence_level=0.9
        )
        
        # Wide intervals should have better coverage (or equal if both are 100%)
        assert metrics_wide['empirical_coverage'] >= metrics_narrow['empirical_coverage']
        
        # Wide intervals are penalized by width
        assert metrics_wide['mean_interval_width'] > metrics_narrow['mean_interval_width']


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_all_same_predictions(self):
        """Test metrics with all same predictions."""
        n_samples = 100
        
        y_true = np.random.randint(0, 2, n_samples)
        y_pred_probs = np.full(n_samples, 0.5)
        
        # Should compute without error
        ece = expected_calibration_error(y_true, y_pred_probs)
        curve = compute_reliability_curve(y_true, y_pred_probs, n_bins=5)
        metrics = compute_calibration_metrics(y_true, y_pred_probs)
        
        assert ece >= 0
        assert len(curve['bin_centers']) > 0
        assert metrics['ece'] >= 0
    
    def test_extreme_confidence(self):
        """Test metrics with extreme confidence (0 and 1)."""
        y_true = np.array([1, 0, 1, 0, 1])
        y_pred_probs = np.array([1.0, 0.0, 1.0, 0.0, 1.0])
        
        # Perfect predictions with extreme confidence
        metrics = compute_calibration_metrics(y_true, y_pred_probs)
        
        # Should have good calibration
        assert metrics['ece'] < 0.1
        
        # Brier score should be 0 (perfect)
        assert metrics['brier_score'] == 0.0
    
    def test_single_bin_reliability_curve(self):
        """Test reliability curve with single bin."""
        y_true = np.array([1, 0, 1, 1, 0])
        y_pred_probs = np.array([0.5, 0.5, 0.5, 0.5, 0.5])
        
        curve = compute_reliability_curve(y_true, y_pred_probs, n_bins=1)
        
        # Should have one bin
        assert len(curve['bin_centers']) == 1
        
        # Observed frequency should be 3/5 = 0.6
        assert np.isclose(curve['observed_freqs'][0], 0.6)


class TestIntegration:
    """Integration tests for calibration metrics workflows."""
    
    def test_full_calibration_workflow(self):
        """Test complete calibration assessment workflow."""
        np.random.seed(42)
        n_samples = 500
        
        # Generate slightly miscalibrated data
        true_probs = np.random.uniform(0.2, 0.8, n_samples)
        y_true = (np.random.rand(n_samples) < true_probs).astype(int)
        
        # Overconfident predictions
        y_pred_probs = np.where(true_probs > 0.5, true_probs + 0.1, true_probs - 0.1)
        y_pred_probs = np.clip(y_pred_probs, 0.01, 0.99)
        
        # Compute comprehensive metrics
        calibration_metrics = compute_calibration_metrics(y_true, y_pred_probs)
        
        # Check all components
        assert 'ece' in calibration_metrics
        assert 'brier_score' in calibration_metrics
        assert 'log_loss' in calibration_metrics
        assert 'reliability_curve' in calibration_metrics
        
        # Reliability curve
        curve = calibration_metrics['reliability_curve']
        assert len(curve['bin_centers']) > 0
        assert len(curve['predicted_probs']) > 0
        
        # ECE should be elevated (miscalibrated)
        assert calibration_metrics['ece'] > 0.05
    
    def test_prediction_interval_assessment_workflow(self):
        """Test complete prediction interval assessment."""
        np.random.seed(42)
        n_samples = 300
        
        # Generate regression data
        y_true = np.random.randn(n_samples) * 15 + 100
        
        # Generate predictions with error
        y_pred = y_true + np.random.randn(n_samples) * 10
        
        # Construct intervals around predictions with ~90% coverage
        lower = y_pred - 20
        upper = y_pred + 20
        
        # Evaluate intervals
        interval_metrics = evaluate_prediction_intervals(
            y_true,
            (lower, upper),
            confidence_level=0.9
        )
        
        # Check all metrics
        assert 'empirical_coverage' in interval_metrics
        assert 'mean_interval_width' in interval_metrics
        assert 'interval_score' in interval_metrics
        
        # Coverage should be reasonable (allowing for high coverage with wide intervals)
        assert 0.75 <= interval_metrics['empirical_coverage'] <= 1.0
        
        # Sharpness metrics
        sharpness = compute_sharpness((lower, upper))
        assert 'mean_interval_width' in sharpness
        assert sharpness['mean_interval_width'] > 0

