"""
Tests for forecasting metrics and evaluation functions

Validates:
- RMSE, sMAPE, CRPS calculations
- Prediction interval coverage
- Expected Calibration Error (ECE)
- Turning point detection
- Edge cases (zeros, negatives, NaNs)
"""

import pytest
import numpy as np

from models_src.utils.metrics import (
    rmse,
    smape,
    crps,
    prediction_interval_coverage,
    expected_calibration_error,
    turning_point_accuracy,
)


class TestRMSE:
    """Test Root Mean Squared Error metric"""

    def test_rmse_perfect_predictions(self):
        """Test RMSE with perfect predictions (should be 0)"""
        y_true = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        y_pred = np.array([1.0, 2.0, 3.0, 4.0, 5.0])

        result = rmse(y_true, y_pred)

        assert result == 0.0

    def test_rmse_known_values(self):
        """Test RMSE with known expected output"""
        y_true = np.array([3.0, -0.5, 2.0, 7.0])
        y_pred = np.array([2.5, 0.0, 2.0, 8.0])

        # Expected: sqrt(((0.5)^2 + (0.5)^2 + (0)^2 + (1)^2) / 4)
        # Expected: sqrt(1.5 / 4) = sqrt(0.375) = 0.612372
        expected = np.sqrt(0.375)
        result = rmse(y_true, y_pred)

        assert np.isclose(result, expected, rtol=1e-5)

    def test_rmse_with_large_errors(self):
        """Test RMSE with large prediction errors"""
        y_true = np.array([0.0, 0.0, 0.0])
        y_pred = np.array([100.0, 100.0, 100.0])

        result = rmse(y_true, y_pred)

        assert result == 100.0

    def test_rmse_length_mismatch_raises_error(self):
        """Test that mismatched array lengths raise ValueError"""
        y_true = np.array([1.0, 2.0, 3.0])
        y_pred = np.array([1.0, 2.0])

        with pytest.raises(ValueError) as exc_info:
            rmse(y_true, y_pred)

        assert "same length" in str(exc_info.value).lower()

    def test_rmse_with_nan_raises_error(self):
        """Test that NaN values raise ValueError"""
        y_true = np.array([1.0, 2.0, np.nan])
        y_pred = np.array([1.0, 2.0, 3.0])

        with pytest.raises(ValueError) as exc_info:
            rmse(y_true, y_pred)

        assert "nan" in str(exc_info.value).lower() or "missing" in str(exc_info.value).lower()

    def test_rmse_empty_arrays_raises_error(self):
        """Test that empty arrays raise ValueError"""
        y_true = np.array([])
        y_pred = np.array([])

        with pytest.raises(ValueError) as exc_info:
            rmse(y_true, y_pred)

        assert "empty" in str(exc_info.value).lower()


class TestSMAPE:
    """Test Symmetric Mean Absolute Percentage Error metric"""

    def test_smape_perfect_predictions(self):
        """Test sMAPE with perfect predictions (should be 0)"""
        y_true = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        y_pred = np.array([1.0, 2.0, 3.0, 4.0, 5.0])

        result = smape(y_true, y_pred)

        assert result == 0.0

    def test_smape_known_values(self):
        """Test sMAPE with known expected output"""
        y_true = np.array([100.0, 200.0])
        y_pred = np.array([110.0, 180.0])

        # For first: |110-100| / ((|100|+|110|)/2) = 10/105 = 0.0952
        # For second: |180-200| / ((|200|+|180|)/2) = 20/190 = 0.1053
        # Mean: (0.0952 + 0.1053) / 2 = 0.10025
        # As percentage: 10.025%
        expected = 10.025
        result = smape(y_true, y_pred)

        assert np.isclose(result, expected, rtol=1e-3)

    def test_smape_with_zeros(self):
        """Test sMAPE handles zeros gracefully"""
        y_true = np.array([0.0, 100.0])
        y_pred = np.array([0.0, 100.0])

        # Should handle zero denominators
        result = smape(y_true, y_pred)

        assert result == 0.0

    def test_smape_range_bounds(self):
        """Test sMAPE is bounded between 0 and 200"""
        y_true = np.array([100.0, 200.0, 300.0])
        y_pred = np.array([50.0, 250.0, 200.0])

        result = smape(y_true, y_pred)

        assert 0.0 <= result <= 200.0

    def test_smape_with_negative_values(self):
        """Test sMAPE with negative values"""
        y_true = np.array([-100.0, -200.0])
        y_pred = np.array([-110.0, -180.0])

        result = smape(y_true, y_pred)

        # Should handle negatives correctly
        assert 0.0 <= result <= 200.0


class TestCRPS:
    """Test Continuous Ranked Probability Score"""

    def test_crps_perfect_prediction(self):
        """Test CRPS with perfect point prediction"""
        y_true = np.array([5.0])
        y_pred_mean = np.array([5.0])
        y_pred_std = np.array([0.01])  # Very small uncertainty

        result = crps(y_true, y_pred_mean, y_pred_std)

        # Should be close to zero
        assert result < 0.1

    def test_crps_with_uncertainty(self):
        """Test CRPS increases with uncertainty"""
        y_true = np.array([10.0, 10.0])
        y_pred_mean = np.array([10.0, 10.0])

        # Test with different uncertainty levels
        crps_low_std = crps(y_true, y_pred_mean, np.array([1.0, 1.0]))
        crps_high_std = crps(y_true, y_pred_mean, np.array([10.0, 10.0]))

        # Higher uncertainty should give higher CRPS
        assert crps_high_std > crps_low_std

    def test_crps_with_bias(self):
        """Test CRPS increases with prediction bias"""
        y_true = np.array([10.0, 10.0])
        y_pred_std = np.array([1.0, 1.0])

        # Test with different bias levels
        crps_no_bias = crps(y_true, np.array([10.0, 10.0]), y_pred_std)
        crps_with_bias = crps(y_true, np.array([15.0, 15.0]), y_pred_std)

        # Bias should increase CRPS
        assert crps_with_bias > crps_no_bias

    def test_crps_always_positive(self):
        """Test CRPS is always non-negative"""
        y_true = np.array([1.0, 5.0, 10.0, 50.0, 100.0])
        y_pred_mean = np.array([2.0, 4.0, 12.0, 45.0, 110.0])
        y_pred_std = np.array([1.0, 2.0, 3.0, 5.0, 10.0])

        result = crps(y_true, y_pred_mean, y_pred_std)

        assert result >= 0.0


class TestPredictionIntervalCoverage:
    """Test prediction interval coverage calculation"""

    def test_perfect_90_percent_coverage(self):
        """Test with perfect 90% coverage"""
        # 90 out of 100 observations within interval
        y_true = np.arange(100)
        lower = y_true - 1.0
        upper = y_true + 1.0

        # Put 10 observations outside interval
        y_true[0:5] = lower[0:5] - 10
        y_true[95:100] = upper[95:100] + 10

        coverage = prediction_interval_coverage(y_true, lower, upper, confidence_level=90)

        # Should be exactly 90%
        assert coverage == 90.0

    def test_100_percent_coverage(self):
        """Test with all observations within interval"""
        y_true = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        lower = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
        upper = np.array([2.0, 3.0, 4.0, 5.0, 6.0])

        coverage = prediction_interval_coverage(y_true, lower, upper)

        assert coverage == 100.0

    def test_zero_percent_coverage(self):
        """Test with no observations within interval"""
        y_true = np.array([10.0, 20.0, 30.0])
        lower = np.array([0.0, 0.0, 0.0])
        upper = np.array([5.0, 5.0, 5.0])

        coverage = prediction_interval_coverage(y_true, lower, upper)

        assert coverage == 0.0

    def test_coverage_with_boundary_cases(self):
        """Test coverage with values exactly on boundaries"""
        y_true = np.array([1.0, 2.0, 3.0])
        lower = np.array([1.0, 1.0, 1.0])  # First value on lower boundary
        upper = np.array([3.0, 3.0, 3.0])  # Third value on upper boundary

        coverage = prediction_interval_coverage(y_true, lower, upper)

        # Boundary values should be included
        assert coverage == 100.0

    def test_coverage_returns_percentage(self):
        """Test that coverage is returned as percentage (0-100)"""
        y_true = np.array([1.0, 2.0, 3.0, 4.0])
        lower = y_true - 0.5
        upper = y_true + 0.5

        coverage = prediction_interval_coverage(y_true, lower, upper)

        assert 0.0 <= coverage <= 100.0


class TestExpectedCalibrationError:
    """Test Expected Calibration Error (ECE) for probability forecasts"""

    def test_ece_perfect_calibration(self):
        """Test ECE with perfectly calibrated probabilities"""
        # Create truly well-calibrated data:
        # Bin 0-0.5: predict 0.25, actual 25% positive
        # Bin 0.5-1.0: predict 0.75, actual 75% positive
        y_true = np.array([0, 0, 0, 1] + [0, 1, 1, 1])  # 25% then 75%
        y_pred_probs = np.array([0.25, 0.25, 0.25, 0.25] + [0.75, 0.75, 0.75, 0.75])

        # With 2 bins, should have perfect calibration
        ece = expected_calibration_error(y_true, y_pred_probs, n_bins=2)

        # Should be very close to 0 for perfect calibration
        assert ece < 0.05

    def test_ece_poor_calibration(self):
        """Test ECE with poorly calibrated probabilities"""
        # Always predict 0.9 but outcome is only 50% True
        y_true = np.array([0, 1, 0, 1, 0, 1, 0, 1, 0, 1])
        y_pred_probs = np.array([0.9] * 10)

        ece = expected_calibration_error(y_true, y_pred_probs, n_bins=5)

        # Should have high calibration error (predicted 90%, actual 50%)
        # ECE should be around |0.9 - 0.5| = 0.4
        assert ece > 0.3

    def test_ece_always_zero(self):
        """Test ECE is always non-negative"""
        y_true = np.array([1, 0, 1, 1, 0, 1, 0, 0])
        y_pred_probs = np.array([0.8, 0.3, 0.7, 0.9, 0.2, 0.6, 0.4, 0.1])

        ece = expected_calibration_error(y_true, y_pred_probs, n_bins=5)

        assert ece >= 0.0

    def test_ece_bounded_by_one(self):
        """Test ECE is bounded by 1.0"""
        y_true = np.array([0, 0, 0, 1, 1, 1])
        y_pred_probs = np.array([1.0, 1.0, 1.0, 0.0, 0.0, 0.0])

        ece = expected_calibration_error(y_true, y_pred_probs, n_bins=5)

        assert 0.0 <= ece <= 1.0

    def test_ece_with_different_bin_counts(self):
        """Test ECE calculation with different numbers of bins"""
        y_true = np.array([1] * 50 + [0] * 50)
        y_pred_probs = np.random.uniform(0, 1, 100)

        ece_5_bins = expected_calibration_error(y_true, y_pred_probs, n_bins=5)
        ece_10_bins = expected_calibration_error(y_true, y_pred_probs, n_bins=10)

        # Both should be valid (non-negative)
        assert ece_5_bins >= 0.0
        assert ece_10_bins >= 0.0


class TestTurningPointAccuracy:
    """Test turning point detection accuracy"""

    def test_turning_point_perfect_detection(self):
        """Test perfect turning point detection"""
        # Series: down, down, UP, up, DOWN, down
        y_true = np.array([10, 8, 6, 8, 10, 8, 6])
        y_pred = np.array([10, 8, 6, 8, 10, 8, 6])

        accuracy = turning_point_accuracy(y_true, y_pred)

        # Perfect match of turning points
        assert accuracy == 100.0

    def test_turning_point_no_detection(self):
        """Test zero turning point detection"""
        # True series has turning point at index 2
        # Predicted series is monotonic (no turning points)
        y_true = np.array([10, 5, 2, 7, 12])  # Down then up (turning point at 2)
        y_pred = np.array([10, 8, 6, 4, 2])  # Monotonic down (no turning point)

        accuracy = turning_point_accuracy(y_true, y_pred)

        # Should have 0% accuracy (missed the turning point)
        assert accuracy == 0.0

    def test_turning_point_with_no_actual_turns(self):
        """Test when actual series has no turning points"""
        # Monotonic series
        y_true = np.array([1, 2, 3, 4, 5])
        y_pred = np.array([1, 2, 3, 4, 5])

        accuracy = turning_point_accuracy(y_true, y_pred)

        # No turning points to detect - should handle gracefully
        # Either 100% (no turns to miss) or handle special case
        assert 0.0 <= accuracy <= 100.0

    def test_turning_point_partial_detection(self):
        """Test partial turning point detection"""
        # True series: clear peak at index 1, trough at 3, peak at 5
        y_true = np.array([10, 50, 30, 20, 40, 70, 50])

        # Predicted: monotonic increase, completely misses turning points
        y_pred = np.array([10, 20, 30, 40, 50, 60, 70])

        accuracy = turning_point_accuracy(y_true, y_pred)

        # Should be 0% (no turning points in predicted series)
        assert accuracy == 0.0

    def test_turning_point_returns_percentage(self):
        """Test that accuracy is returned as percentage (0-100)"""
        y_true = np.array([5, 3, 1, 2, 4, 6])
        y_pred = np.array([5, 4, 3, 4, 5, 6])

        accuracy = turning_point_accuracy(y_true, y_pred)

        assert 0.0 <= accuracy <= 100.0


class TestMetricsEdgeCases:
    """Test edge cases across all metrics"""

    def test_metrics_with_single_value(self):
        """Test metrics with single observation"""
        y_true = np.array([5.0])
        y_pred = np.array([5.5])

        # Should handle single value gracefully
        rmse_result = rmse(y_true, y_pred)
        smape_result = smape(y_true, y_pred)

        assert rmse_result >= 0.0
        assert 0.0 <= smape_result <= 200.0

    def test_metrics_with_constant_predictions(self):
        """Test metrics when all predictions are identical"""
        y_true = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        y_pred = np.array([3.0, 3.0, 3.0, 3.0, 3.0])

        rmse_result = rmse(y_true, y_pred)
        smape_result = smape(y_true, y_pred)

        # Should calculate correctly
        assert rmse_result > 0.0
        assert smape_result > 0.0

    def test_metrics_input_validation(self):
        """Test that metrics validate input types"""
        # Test with lists (should convert to numpy)
        y_true_list = [1.0, 2.0, 3.0]
        y_pred_list = [1.5, 2.5, 3.5]

        result = rmse(y_true_list, y_pred_list)

        # Should handle list input
        assert isinstance(result, (float, np.floating))
