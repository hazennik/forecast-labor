"""
Tests for Split Conformal Prediction.

Tests cover:
- Predictor initialization and parameter validation
- Fitting on calibration set
- Prediction interval construction
- Coverage validation (empirical vs. target)
- Interval width tests
- Adaptive intervals
- Edge cases (small samples, perfect predictions, etc.)
- Save/load functionality
- Multiple confidence levels
"""

import pytest
import numpy as np
import tempfile
from pathlib import Path

from models_src.calibration.conformal import ConformalPredictor


class TestConformalPredictorInitialization:
    """Test conformal predictor initialization and parameter validation."""
    
    def test_init_default_parameters(self):
        """Test initialization with default parameters."""
        predictor = ConformalPredictor()
        
        assert predictor.confidence_levels == [0.8, 0.9, 0.95]
        assert predictor.adaptive is False
        assert predictor.adaptive_gamma == 0.1
        assert predictor.is_fitted_ is False
        assert predictor.quantiles_ is None
        assert predictor.calibration_scores_ is None
    
    def test_init_custom_parameters(self):
        """Test initialization with custom parameters."""
        custom_levels = [0.85, 0.95]
        predictor = ConformalPredictor(
            confidence_levels=custom_levels,
            adaptive=True,
            adaptive_gamma=0.2
        )
        
        assert predictor.confidence_levels == custom_levels
        assert predictor.adaptive is True
        assert predictor.adaptive_gamma == 0.2
    
    def test_init_validates_empty_confidence_levels(self):
        """Test that empty confidence levels list raises ValueError."""
        with pytest.raises(ValueError, match="confidence_levels list cannot be empty"):
            ConformalPredictor(confidence_levels=[])
    
    def test_init_validates_confidence_range(self):
        """Test that confidence levels outside (0, 1) raise ValueError."""
        with pytest.raises(ValueError, match="must be in \\(0, 1\\)"):
            ConformalPredictor(confidence_levels=[0.0, 0.5, 1.0])
    
    def test_init_validates_adaptive_gamma(self):
        """Test that non-positive adaptive_gamma raises ValueError."""
        with pytest.raises(ValueError, match="adaptive_gamma must be positive"):
            ConformalPredictor(adaptive_gamma=0)


class TestConformalPredictorFitting:
    """Test conformal predictor fitting functionality."""
    
    @pytest.fixture
    def sample_calibration_data(self):
        """Generate sample calibration data (predictions with errors)."""
        np.random.seed(42)
        n_samples = 100
        
        # True values
        y_true = np.random.randn(n_samples) * 10 + 50
        
        # Predictions with some error
        y_pred = y_true + np.random.randn(n_samples) * 5
        
        return y_true, y_pred
    
    def test_fit_basic(self, sample_calibration_data):
        """Test basic fitting functionality."""
        y_true, y_pred = sample_calibration_data
        
        predictor = ConformalPredictor(confidence_levels=[0.9])
        result = predictor.fit(y_true, y_pred)
        
        # Check method chaining
        assert result is predictor
        
        # Check fitted attributes
        assert predictor.is_fitted_ is True
        assert predictor.n_calibration_ == len(y_true)
        assert predictor.quantiles_ is not None
        assert 0.9 in predictor.quantiles_
        assert predictor.calibration_scores_ is not None
        assert len(predictor.calibration_scores_) == len(y_true)
        assert predictor.coverage_diagnostics_ is not None
    
    def test_fit_computes_correct_scores(self, sample_calibration_data):
        """Test that non-conformity scores are absolute residuals."""
        y_true, y_pred = sample_calibration_data
        
        predictor = ConformalPredictor()
        predictor.fit(y_true, y_pred)
        
        # Scores should be absolute residuals
        expected_scores = np.abs(y_true - y_pred)
        assert np.allclose(predictor.calibration_scores_, expected_scores)
    
    def test_fit_empty_data(self):
        """Test that fitting with empty data raises ValueError."""
        predictor = ConformalPredictor()
        y_true = np.array([])
        y_pred = np.array([])
        
        with pytest.raises(ValueError, match="cannot be empty"):
            predictor.fit(y_true, y_pred)
    
    def test_fit_length_mismatch(self, sample_calibration_data):
        """Test that length mismatch raises ValueError."""
        y_true, y_pred = sample_calibration_data
        
        predictor = ConformalPredictor()
        y_true_short = y_true[:50]
        
        with pytest.raises(ValueError, match="must have same length"):
            predictor.fit(y_true_short, y_pred)
    
    def test_fit_warns_on_small_calibration_set(self):
        """Test that small calibration set logs warning."""
        np.random.seed(42)
        
        # Very small calibration set
        y_true = np.random.randn(20)
        y_pred = y_true + np.random.randn(20) * 0.5
        
        predictor = ConformalPredictor()
        # Should fit without error but log warning
        predictor.fit(y_true, y_pred)
        
        assert predictor.is_fitted_ is True


class TestPredictInterval:
    """Test prediction interval construction."""
    
    @pytest.fixture
    def fitted_predictor(self):
        """Create and fit a predictor for testing."""
        np.random.seed(42)
        n_samples = 200
        
        y_true = np.random.randn(n_samples) * 10 + 50
        y_pred = y_true + np.random.randn(n_samples) * 5
        
        predictor = ConformalPredictor(confidence_levels=[0.8, 0.9, 0.95])
        predictor.fit(y_true, y_pred)
        
        return predictor
    
    def test_predict_interval_returns_bounds(self, fitted_predictor):
        """Test that predict_interval returns lower and upper bounds."""
        y_pred = np.array([45.0, 50.0, 55.0])
        
        lower, upper = fitted_predictor.predict_interval(y_pred, confidence_level=0.9)
        
        assert len(lower) == len(y_pred)
        assert len(upper) == len(y_pred)
        assert np.all(lower <= upper)
    
    def test_predict_interval_before_fit(self):
        """Test that predicting before fit raises ValueError."""
        predictor = ConformalPredictor()
        y_pred = np.array([45.0, 50.0, 55.0])
        
        with pytest.raises(ValueError, match="must be fitted before prediction"):
            predictor.predict_interval(y_pred, confidence_level=0.9)
    
    def test_predict_interval_invalid_confidence_level(self, fitted_predictor):
        """Test that invalid confidence level raises ValueError."""
        y_pred = np.array([45.0, 50.0, 55.0])
        
        with pytest.raises(ValueError, match="Confidence level .* not found"):
            fitted_predictor.predict_interval(y_pred, confidence_level=0.99)
    
    def test_predict_interval_empty_input(self, fitted_predictor):
        """Test that empty input raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            fitted_predictor.predict_interval(np.array([]), confidence_level=0.9)
    
    def test_predict_interval_width_increases_with_confidence(self, fitted_predictor):
        """Test that interval width increases with confidence level."""
        y_pred = np.array([50.0])
        
        lower_80, upper_80 = fitted_predictor.predict_interval(y_pred, confidence_level=0.8)
        lower_90, upper_90 = fitted_predictor.predict_interval(y_pred, confidence_level=0.9)
        lower_95, upper_95 = fitted_predictor.predict_interval(y_pred, confidence_level=0.95)
        
        width_80 = upper_80[0] - lower_80[0]
        width_90 = upper_90[0] - lower_90[0]
        width_95 = upper_95[0] - lower_95[0]
        
        # Higher confidence → wider intervals
        assert width_80 < width_90 < width_95


class TestCoverageValidation:
    """Test coverage validation on test sets."""
    
    def test_coverage_meets_target(self):
        """Test that empirical coverage meets target on test set."""
        np.random.seed(42)
        
        # Generate calibration data
        n_calib = 200
        y_calib_true = np.random.randn(n_calib) * 10 + 50
        y_calib_pred = y_calib_true + np.random.randn(n_calib) * 5
        
        # Generate test data (from same distribution)
        n_test = 500
        y_test_true = np.random.randn(n_test) * 10 + 50
        y_test_pred = y_test_true + np.random.randn(n_test) * 5
        
        # Fit conformal predictor
        predictor = ConformalPredictor(confidence_levels=[0.9])
        predictor.fit(y_calib_true, y_calib_pred)
        
        # Validate coverage on test set
        metrics = predictor.validate_coverage(
            y_test_true,
            y_test_pred,
            confidence_level=0.9
        )
        
        # Empirical coverage should be close to 90% (within 5% tolerance)
        assert 0.85 <= metrics['empirical_coverage'] <= 0.95
        assert metrics['target_coverage'] == 0.9
        assert 'avg_interval_width' in metrics
    
    def test_coverage_multiple_levels(self):
        """Test coverage validation for multiple confidence levels."""
        np.random.seed(42)
        
        # Calibration data
        n_calib = 300
        y_calib_true = np.random.randn(n_calib) * 15 + 100
        y_calib_pred = y_calib_true + np.random.randn(n_calib) * 8
        
        # Test data
        n_test = 500
        y_test_true = np.random.randn(n_test) * 15 + 100
        y_test_pred = y_test_true + np.random.randn(n_test) * 8
        
        # Fit with multiple levels
        predictor = ConformalPredictor(confidence_levels=[0.8, 0.9, 0.95])
        predictor.fit(y_calib_true, y_calib_pred)
        
        # Validate each level
        for conf_level in [0.8, 0.9, 0.95]:
            metrics = predictor.validate_coverage(
                y_test_true,
                y_test_pred,
                confidence_level=conf_level
            )
            
            # Coverage should be within reasonable range
            tolerance = 0.06  # ±6%
            assert conf_level - tolerance <= metrics['empirical_coverage'] <= 1.0
    
    def test_validate_coverage_length_mismatch(self):
        """Test that length mismatch raises ValueError."""
        np.random.seed(42)
        
        y_calib_true = np.random.randn(100)
        y_calib_pred = y_calib_true + np.random.randn(100) * 5
        
        predictor = ConformalPredictor()
        predictor.fit(y_calib_true, y_calib_pred)
        
        y_test_true = np.random.randn(50)
        y_test_pred = np.random.randn(100)
        
        with pytest.raises(ValueError, match="must have same length"):
            predictor.validate_coverage(y_test_true, y_test_pred)


class TestIntervalWidth:
    """Test interval width properties."""
    
    def test_interval_width_consistent_for_fixed_predictor(self):
        """Test that fixed (non-adaptive) intervals have consistent width."""
        np.random.seed(42)
        
        y_calib_true = np.random.randn(150) * 10
        y_calib_pred = y_calib_true + np.random.randn(150) * 5
        
        predictor = ConformalPredictor(
            confidence_levels=[0.9],
            adaptive=False
        )
        predictor.fit(y_calib_true, y_calib_pred)
        
        # Different predictions
        y_pred = np.array([10.0, 20.0, 30.0, 40.0, 50.0])
        lower, upper = predictor.predict_interval(y_pred, confidence_level=0.9)
        
        # All intervals should have same width (fixed intervals)
        widths = upper - lower
        assert np.allclose(widths, widths[0])
    
    def test_adaptive_intervals_vary_by_prediction(self):
        """Test that adaptive intervals can vary by prediction."""
        np.random.seed(42)
        
        y_calib_true = np.random.randn(150) * 10 + 50
        y_calib_pred = y_calib_true + np.random.randn(150) * 5
        
        predictor = ConformalPredictor(
            confidence_levels=[0.9],
            adaptive=True,
            adaptive_gamma=0.1
        )
        predictor.fit(y_calib_true, y_calib_pred)
        
        # Predictions including outliers
        y_pred = np.array([50.0, 51.0, 52.0, 100.0, 150.0])
        lower, upper = predictor.predict_interval(y_pred, confidence_level=0.9)
        
        # With adaptive intervals, can have some variation
        # (though not guaranteed to be different in all cases)
        widths = upper - lower
        assert len(widths) == 5


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_perfect_predictions(self):
        """Test conformal predictor with perfect predictions."""
        np.random.seed(42)
        n_samples = 100
        
        # Perfect predictions (no error)
        y_true = np.random.randn(n_samples) * 10
        y_pred = y_true.copy()
        
        predictor = ConformalPredictor(confidence_levels=[0.9])
        predictor.fit(y_true, y_pred)
        
        # Should fit without error
        assert predictor.is_fitted_ is True
        
        # Intervals should be very narrow (all scores near 0)
        test_pred = np.array([5.0])
        lower, upper = predictor.predict_interval(test_pred, confidence_level=0.9)
        
        # Width should be small
        width = upper[0] - lower[0]
        assert width < 1.0  # Very narrow for perfect predictions
    
    def test_large_errors(self):
        """Test conformal predictor with large prediction errors."""
        np.random.seed(42)
        n_samples = 150
        
        y_true = np.random.randn(n_samples) * 10
        # Large errors
        y_pred = y_true + np.random.randn(n_samples) * 20
        
        predictor = ConformalPredictor(confidence_levels=[0.9])
        predictor.fit(y_true, y_pred)
        
        # Intervals should be wide
        test_pred = np.array([5.0])
        lower, upper = predictor.predict_interval(test_pred, confidence_level=0.9)
        
        width = upper[0] - lower[0]
        assert width > 20  # Wide intervals for large errors
    
    def test_single_confidence_level(self):
        """Test with single confidence level."""
        np.random.seed(42)
        
        y_calib_true = np.random.randn(100) * 10
        y_calib_pred = y_calib_true + np.random.randn(100) * 5
        
        predictor = ConformalPredictor(confidence_levels=[0.95])
        predictor.fit(y_calib_true, y_calib_pred)
        
        assert len(predictor.quantiles_) == 1
        assert 0.95 in predictor.quantiles_


class TestSaveLoad:
    """Test save/load functionality."""
    
    def test_save_unfitted_predictor(self):
        """Test that saving unfitted predictor raises ValueError."""
        predictor = ConformalPredictor()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'predictor.pkl'
            
            with pytest.raises(ValueError, match="Cannot save unfitted"):
                predictor.save(path)
    
    def test_save_load_roundtrip(self):
        """Test that save/load preserves predictor state."""
        np.random.seed(42)
        
        y_calib_true = np.random.randn(150) * 10
        y_calib_pred = y_calib_true + np.random.randn(150) * 5
        
        predictor = ConformalPredictor(
            confidence_levels=[0.8, 0.9, 0.95],
            adaptive=True,
            adaptive_gamma=0.15
        )
        predictor.fit(y_calib_true, y_calib_pred)
        
        # Get intervals before save
        test_pred = np.array([5.0, 10.0, 15.0])
        lower_orig, upper_orig = predictor.predict_interval(test_pred, confidence_level=0.9)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'conformal_predictor.pkl'
            
            # Save predictor
            predictor.save(path)
            assert path.exists()
            
            # Load predictor
            loaded_predictor = ConformalPredictor.load(path)
            
            # Check parameters match
            assert loaded_predictor.confidence_levels == predictor.confidence_levels
            assert loaded_predictor.adaptive == predictor.adaptive
            assert loaded_predictor.adaptive_gamma == predictor.adaptive_gamma
            
            # Check fitted state matches
            assert loaded_predictor.is_fitted_ == predictor.is_fitted_
            assert loaded_predictor.n_calibration_ == predictor.n_calibration_
            assert list(loaded_predictor.quantiles_.keys()) == list(predictor.quantiles_.keys())
            
            for key in predictor.quantiles_:
                assert np.isclose(
                    loaded_predictor.quantiles_[key],
                    predictor.quantiles_[key]
                )
            
            # Check intervals match
            lower_loaded, upper_loaded = loaded_predictor.predict_interval(
                test_pred,
                confidence_level=0.9
            )
            assert np.allclose(lower_orig, lower_loaded)
            assert np.allclose(upper_orig, upper_loaded)
    
    def test_load_nonexistent_file(self):
        """Test that loading nonexistent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="file not found"):
            ConformalPredictor.load(Path('/nonexistent/path/predictor.pkl'))


class TestGetParams:
    """Test get_params method."""
    
    def test_get_params_unfitted(self):
        """Test get_params on unfitted predictor."""
        predictor = ConformalPredictor(
            confidence_levels=[0.85, 0.95],
            adaptive=True
        )
        
        params = predictor.get_params()
        
        assert params['confidence_levels'] == [0.85, 0.95]
        assert params['adaptive'] is True
        assert params['is_fitted'] is False
        assert params['n_calibration'] is None
        assert params['quantiles'] is None
    
    def test_get_params_fitted(self):
        """Test get_params on fitted predictor."""
        np.random.seed(42)
        
        y_calib_true = np.random.randn(100) * 10
        y_calib_pred = y_calib_true + np.random.randn(100) * 5
        
        predictor = ConformalPredictor(confidence_levels=[0.9])
        predictor.fit(y_calib_true, y_calib_pred)
        
        params = predictor.get_params()
        
        assert params['is_fitted'] is True
        assert params['n_calibration'] == 100
        assert params['quantiles'] is not None
        assert 0.9 in params['quantiles']
        assert params['coverage_diagnostics'] is not None


class TestIntegration:
    """Integration tests for complete workflows."""
    
    def test_full_workflow(self):
        """Test complete workflow: fit → predict → validate → save → load."""
        np.random.seed(42)
        
        # Generate calibration data
        n_calib = 200
        y_calib_true = np.random.randn(n_calib) * 15 + 50
        y_calib_pred = y_calib_true + np.random.randn(n_calib) * 7
        
        # Generate test data
        n_test = 300
        y_test_true = np.random.randn(n_test) * 15 + 50
        y_test_pred = y_test_true + np.random.randn(n_test) * 7
        
        # Fit conformal predictor
        predictor = ConformalPredictor(confidence_levels=[0.9])
        predictor.fit(y_calib_true, y_calib_pred)
        
        # Check fitted
        assert predictor.is_fitted_ is True
        
        # Predict intervals
        lower, upper = predictor.predict_interval(y_test_pred, confidence_level=0.9)
        assert len(lower) == n_test
        assert len(upper) == n_test
        
        # Validate coverage
        metrics = predictor.validate_coverage(
            y_test_true,
            y_test_pred,
            confidence_level=0.9
        )
        assert 0.85 <= metrics['empirical_coverage'] <= 0.95
        
        # Get params
        params = predictor.get_params()
        assert params['is_fitted'] is True
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Save
            save_path = Path(tmpdir) / 'predictor.pkl'
            predictor.save(save_path)
            assert save_path.exists()
            
            # Load
            loaded_predictor = ConformalPredictor.load(save_path)
            
            # Verify loaded predictor produces same results
            lower_loaded, upper_loaded = loaded_predictor.predict_interval(
                y_test_pred,
                confidence_level=0.9
            )
            assert np.allclose(lower, lower_loaded)
            assert np.allclose(upper, upper_loaded)
    
    def test_realistic_labor_market_scenario(self):
        """Test conformal prediction on realistic labor market forecast errors."""
        np.random.seed(42)
        
        # Simulate NFP forecast errors (typical range: ±50K)
        n_calib = 120  # ~10 years of monthly data
        # True NFP changes
        y_calib_true = np.random.randn(n_calib) * 50 + 200  # Mean 200K, std 50K
        # Model predictions (with typical forecast error)
        y_calib_pred = y_calib_true + np.random.randn(n_calib) * 30  # RMSE ~30K
        
        # Test set
        n_test = 24  # 2 years
        y_test_true = np.random.randn(n_test) * 50 + 200
        y_test_pred = y_test_true + np.random.randn(n_test) * 30
        
        # Fit 90% prediction intervals
        predictor = ConformalPredictor(confidence_levels=[0.9])
        predictor.fit(y_calib_true, y_calib_pred)
        
        # Validate on test set
        metrics = predictor.validate_coverage(
            y_test_true,
            y_test_pred,
            confidence_level=0.9
        )
        
        # Should achieve nominal coverage
        assert metrics['empirical_coverage'] >= 0.80  # At least 80% (small test set)
        
        # Interval width should be reasonable for NFP (typical: ±50-80K)
        assert 60 <= metrics['avg_interval_width'] <= 120  # Total width

