"""
Tests for Isotonic Regression Calibration.

Tests cover:
- Calibrator initialization and parameter validation
- Fitting on validation data
- Transform functionality (applying calibration)
- Calibration improvement (before/after ECE comparison)
- Reliability diagram generation
- Edge cases (perfect calibration, imbalanced data, etc.)
- Save/load functionality
- Error handling
"""

import pytest
import numpy as np
import tempfile
from pathlib import Path

from models_src.calibration.isotonic import IsotonicCalibrator
from models_src.utils.metrics import expected_calibration_error


class TestIsotonicCalibratorInitialization:
    """Test calibrator initialization and parameter validation."""
    
    def test_init_default_parameters(self):
        """Test initialization with default parameters."""
        calibrator = IsotonicCalibrator()
        
        assert calibrator.out_of_bounds == 'clip'
        assert calibrator.is_fitted_ is False
        assert calibrator.calibrator_ is None
        assert calibrator.n_samples_ is None
        assert calibrator.ece_before_ is None
        assert calibrator.ece_after_ is None
    
    def test_init_custom_parameters(self):
        """Test initialization with custom parameters."""
        calibrator = IsotonicCalibrator(out_of_bounds='nan')
        
        assert calibrator.out_of_bounds == 'nan'
    
    def test_init_validates_out_of_bounds(self):
        """Test that invalid out_of_bounds raises ValueError."""
        with pytest.raises(ValueError, match="out_of_bounds must be"):
            IsotonicCalibrator(out_of_bounds='invalid')


class TestIsotonicCalibratorFitting:
    """Test calibrator fitting functionality."""
    
    @pytest.fixture
    def sample_data(self):
        """Generate sample calibration data (intentionally miscalibrated)."""
        np.random.seed(42)
        n_samples = 200
        
        # Generate true probabilities
        true_probs = np.random.uniform(0.2, 0.8, n_samples)
        
        # Generate binary outcomes based on true probs
        y_true = (np.random.rand(n_samples) < true_probs).astype(int)
        
        # Generate miscalibrated predictions (too confident)
        # Push probabilities towards extremes
        y_pred_probs = np.where(
            true_probs > 0.5,
            true_probs * 1.2,  # Overconfident for high probs
            true_probs * 0.8   # Underconfident for low probs
        )
        y_pred_probs = np.clip(y_pred_probs, 0.01, 0.99)
        
        return y_true, y_pred_probs
    
    def test_fit_basic(self, sample_data):
        """Test basic fitting functionality."""
        y_true, y_pred_probs = sample_data
        
        calibrator = IsotonicCalibrator()
        result = calibrator.fit(y_true, y_pred_probs)
        
        # Check method chaining
        assert result is calibrator
        
        # Check fitted attributes
        assert calibrator.is_fitted_ is True
        assert calibrator.calibrator_ is not None
        assert calibrator.n_samples_ == len(y_true)
        assert calibrator.ece_before_ is not None
        assert calibrator.ece_after_ is not None
        
        # Calibration should improve ECE (or at worst, keep it same)
        assert calibrator.ece_after_ <= calibrator.ece_before_ + 1e-6
    
    def test_fit_empty_data(self):
        """Test that fitting with empty data raises ValueError."""
        calibrator = IsotonicCalibrator()
        y_true = np.array([])
        y_pred_probs = np.array([])
        
        with pytest.raises(ValueError, match="cannot be empty"):
            calibrator.fit(y_true, y_pred_probs)
    
    def test_fit_length_mismatch(self, sample_data):
        """Test that length mismatch raises ValueError."""
        y_true, y_pred_probs = sample_data
        
        calibrator = IsotonicCalibrator()
        y_true_short = y_true[:100]
        
        with pytest.raises(ValueError, match="must have same length"):
            calibrator.fit(y_true_short, y_pred_probs)
    
    def test_fit_validates_binary_outcomes(self):
        """Test that non-binary outcomes raise ValueError."""
        calibrator = IsotonicCalibrator()
        
        y_true = np.array([0, 1, 2, 3])  # Not binary
        y_pred_probs = np.array([0.1, 0.3, 0.5, 0.7])
        
        with pytest.raises(ValueError, match="must contain only 0s and 1s"):
            calibrator.fit(y_true, y_pred_probs)
    
    def test_fit_validates_probability_range(self):
        """Test that probabilities outside [0, 1] raise ValueError."""
        calibrator = IsotonicCalibrator()
        
        y_true = np.array([0, 1, 1, 0])
        y_pred_probs = np.array([0.1, 1.5, 0.7, -0.2])  # Invalid range
        
        with pytest.raises(ValueError, match="must be in range"):
            calibrator.fit(y_true, y_pred_probs)


class TestIsotonicCalibratorTransform:
    """Test transform functionality."""
    
    @pytest.fixture
    def fitted_calibrator(self):
        """Create and fit a calibrator for testing."""
        np.random.seed(42)
        n_samples = 200
        
        true_probs = np.random.uniform(0.2, 0.8, n_samples)
        y_true = (np.random.rand(n_samples) < true_probs).astype(int)
        
        # Miscalibrated predictions
        y_pred_probs = np.where(true_probs > 0.5, true_probs * 1.2, true_probs * 0.8)
        y_pred_probs = np.clip(y_pred_probs, 0.01, 0.99)
        
        calibrator = IsotonicCalibrator()
        calibrator.fit(y_true, y_pred_probs)
        
        return calibrator, y_pred_probs
    
    def test_transform_returns_probabilities(self, fitted_calibrator):
        """Test that transform returns valid probabilities."""
        calibrator, y_pred_probs = fitted_calibrator
        
        calibrated = calibrator.transform(y_pred_probs)
        
        assert len(calibrated) == len(y_pred_probs)
        assert np.all((calibrated >= 0) & (calibrated <= 1))
    
    def test_transform_before_fit(self):
        """Test that transform before fit raises ValueError."""
        calibrator = IsotonicCalibrator()
        y_pred_probs = np.array([0.1, 0.3, 0.5, 0.7])
        
        with pytest.raises(ValueError, match="must be fitted before transform"):
            calibrator.transform(y_pred_probs)
    
    def test_transform_empty_input(self, fitted_calibrator):
        """Test that empty input raises ValueError."""
        calibrator, _ = fitted_calibrator
        
        with pytest.raises(ValueError, match="cannot be empty"):
            calibrator.transform(np.array([]))
    
    def test_transform_validates_probability_range(self, fitted_calibrator):
        """Test that invalid probabilities raise ValueError."""
        calibrator, _ = fitted_calibrator
        
        invalid_probs = np.array([0.1, 1.5, 0.7, -0.2])
        
        with pytest.raises(ValueError, match="must be in range"):
            calibrator.transform(invalid_probs)


class TestCalibrationImprovement:
    """Test that calibration improves ECE."""
    
    def test_calibration_improves_overconfident_predictions(self):
        """Test calibration improves overconfident predictions."""
        np.random.seed(42)
        n_samples = 500
        
        # True probabilities
        true_probs = np.random.uniform(0.3, 0.7, n_samples)
        y_true = (np.random.rand(n_samples) < true_probs).astype(int)
        
        # Overconfident predictions (pushed towards extremes)
        y_pred_probs = np.where(
            true_probs > 0.5,
            np.minimum(true_probs + 0.2, 0.95),
            np.maximum(true_probs - 0.2, 0.05)
        )
        
        # Fit calibrator
        calibrator = IsotonicCalibrator()
        calibrator.fit(y_true, y_pred_probs)
        
        # Calibration should improve ECE
        assert calibrator.ece_after_ < calibrator.ece_before_
        
        # ECE improvement should be meaningful (at least 10% reduction)
        improvement_pct = (calibrator.ece_before_ - calibrator.ece_after_) / calibrator.ece_before_
        assert improvement_pct > 0.1
    
    def test_calibration_improves_underconfident_predictions(self):
        """Test calibration improves underconfident predictions."""
        np.random.seed(123)
        n_samples = 500
        
        # True probabilities with more separation
        true_probs = np.concatenate([
            np.random.uniform(0.1, 0.3, n_samples // 2),
            np.random.uniform(0.7, 0.9, n_samples // 2)
        ])
        y_true = (np.random.rand(n_samples) < true_probs).astype(int)
        
        # Underconfident predictions (shrunk towards 0.5)
        y_pred_probs = 0.5 + (true_probs - 0.5) * 0.6
        
        # Fit calibrator
        calibrator = IsotonicCalibrator()
        calibrator.fit(y_true, y_pred_probs)
        
        # Calibration should improve ECE
        assert calibrator.ece_after_ < calibrator.ece_before_


class TestReliabilityDiagram:
    """Test reliability diagram generation."""
    
    def test_reliability_diagram_data_structure(self):
        """Test that reliability diagram data has correct structure."""
        np.random.seed(42)
        n_samples = 200
        
        true_probs = np.random.uniform(0.2, 0.8, n_samples)
        y_true = (np.random.rand(n_samples) < true_probs).astype(int)
        y_pred_uncal = np.clip(true_probs * 1.1, 0, 1)
        
        calibrator = IsotonicCalibrator()
        calibrator.fit(y_true, y_pred_uncal)
        
        y_pred_cal = calibrator.transform(y_pred_uncal)
        
        data = calibrator.get_reliability_diagram_data(
            y_true,
            y_pred_uncal,
            y_pred_cal,
            n_bins=10
        )
        
        # Check keys
        assert 'bins' in data
        assert 'uncalibrated_predicted' in data
        assert 'uncalibrated_observed' in data
        assert 'uncalibrated_counts' in data
        assert 'calibrated_predicted' in data
        assert 'calibrated_observed' in data
        assert 'calibrated_counts' in data
        
        # Check shapes match
        n_bins_with_data = len(data['bins'])
        assert len(data['uncalibrated_predicted']) == n_bins_with_data
        assert len(data['uncalibrated_observed']) == n_bins_with_data
        assert len(data['uncalibrated_counts']) == n_bins_with_data
        
        # Check total counts
        assert np.sum(data['uncalibrated_counts']) == n_samples
    
    def test_reliability_diagram_without_calibrated(self):
        """Test reliability diagram with only uncalibrated data."""
        np.random.seed(42)
        n_samples = 100
        
        y_true = np.random.randint(0, 2, n_samples)
        y_pred_uncal = np.random.uniform(0, 1, n_samples)
        
        calibrator = IsotonicCalibrator()
        
        data = calibrator.get_reliability_diagram_data(
            y_true,
            y_pred_uncal,
            y_pred_probs_calibrated=None,
            n_bins=5
        )
        
        # Should have uncalibrated data
        assert 'uncalibrated_predicted' in data
        assert 'uncalibrated_observed' in data
        
        # Should NOT have calibrated data
        assert 'calibrated_predicted' not in data
        assert 'calibrated_observed' not in data


class TestFitTransform:
    """Test fit_transform convenience method."""
    
    def test_fit_transform_combines_fit_and_transform(self):
        """Test that fit_transform produces same result as fit + transform."""
        np.random.seed(42)
        n_samples = 200
        
        y_true = np.random.randint(0, 2, n_samples)
        y_pred_probs = np.random.uniform(0.1, 0.9, n_samples)
        
        # Method 1: fit_transform
        calibrator1 = IsotonicCalibrator()
        result1 = calibrator1.fit_transform(y_true, y_pred_probs)
        
        # Method 2: fit then transform
        calibrator2 = IsotonicCalibrator()
        calibrator2.fit(y_true, y_pred_probs)
        result2 = calibrator2.transform(y_pred_probs)
        
        # Results should be identical
        assert np.allclose(result1, result2)


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_perfect_calibration(self):
        """Test calibrator on perfectly calibrated data."""
        np.random.seed(42)
        n_samples = 1000
        
        # Perfectly calibrated: predictions match true probabilities
        true_probs = np.random.uniform(0.1, 0.9, n_samples)
        y_true = (np.random.rand(n_samples) < true_probs).astype(int)
        y_pred_probs = true_probs.copy()
        
        calibrator = IsotonicCalibrator()
        calibrator.fit(y_true, y_pred_probs)
        
        # ECE should be low for perfectly calibrated data
        assert calibrator.ece_before_ < 0.05
        
        # Calibration should improve or maintain good calibration
        assert calibrator.ece_after_ <= calibrator.ece_before_
        
        # Final ECE should be very low
        assert calibrator.ece_after_ < 0.05
    
    def test_all_same_class(self):
        """Test calibrator with all same class (edge case)."""
        n_samples = 100
        
        # All positive class
        y_true = np.ones(n_samples, dtype=int)
        y_pred_probs = np.random.uniform(0.5, 0.9, n_samples)
        
        calibrator = IsotonicCalibrator()
        
        # Should fit without error (but will log warning)
        calibrator.fit(y_true, y_pred_probs)
        
        assert calibrator.is_fitted_ is True
    
    def test_extreme_probabilities(self):
        """Test calibrator with probabilities at extremes."""
        np.random.seed(42)
        n_samples = 200
        
        # Mix of extreme and moderate probabilities
        y_pred_probs = np.concatenate([
            np.random.uniform(0.0, 0.1, n_samples // 3),
            np.random.uniform(0.4, 0.6, n_samples // 3),
            np.random.uniform(0.9, 1.0, n_samples // 3)
        ])
        
        y_true = (y_pred_probs > 0.5).astype(int)  # Generate consistent labels
        
        calibrator = IsotonicCalibrator()
        calibrator.fit(y_true, y_pred_probs)
        
        # Should handle without error
        calibrated = calibrator.transform(y_pred_probs)
        
        # Calibrated probs should still be in valid range
        assert np.all((calibrated >= 0) & (calibrated <= 1))


class TestSaveLoad:
    """Test save/load functionality."""
    
    def test_save_unfitted_calibrator(self):
        """Test that saving unfitted calibrator raises ValueError."""
        calibrator = IsotonicCalibrator()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'calibrator.pkl'
            
            with pytest.raises(ValueError, match="Cannot save unfitted calibrator"):
                calibrator.save(path)
    
    def test_save_load_roundtrip(self):
        """Test that save/load preserves calibrator state."""
        np.random.seed(42)
        n_samples = 200
        
        y_true = np.random.randint(0, 2, n_samples)
        y_pred_probs = np.random.uniform(0.1, 0.9, n_samples)
        
        # Fit calibrator
        calibrator = IsotonicCalibrator(out_of_bounds='nan')
        calibrator.fit(y_true, y_pred_probs)
        
        # Transform some test data
        test_probs = np.array([0.2, 0.5, 0.8])
        predictions_original = calibrator.transform(test_probs)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'calibrator.pkl'
            
            # Save calibrator
            calibrator.save(path)
            assert path.exists()
            
            # Load calibrator
            loaded_calibrator = IsotonicCalibrator.load(path)
            
            # Check parameters match
            assert loaded_calibrator.out_of_bounds == calibrator.out_of_bounds
            assert loaded_calibrator.is_fitted_ == calibrator.is_fitted_
            assert loaded_calibrator.n_samples_ == calibrator.n_samples_
            assert loaded_calibrator.ece_before_ == calibrator.ece_before_
            assert loaded_calibrator.ece_after_ == calibrator.ece_after_
            
            # Check predictions match
            predictions_loaded = loaded_calibrator.transform(test_probs)
            assert np.allclose(predictions_original, predictions_loaded)
    
    def test_load_nonexistent_file(self):
        """Test that loading nonexistent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="Calibrator file not found"):
            IsotonicCalibrator.load(Path('/nonexistent/path/calibrator.pkl'))


class TestGetParams:
    """Test get_params method."""
    
    def test_get_params_unfitted(self):
        """Test get_params on unfitted calibrator."""
        calibrator = IsotonicCalibrator(out_of_bounds='nan')
        
        params = calibrator.get_params()
        
        assert params['out_of_bounds'] == 'nan'
        assert params['is_fitted'] is False
        assert params['n_samples'] is None
        assert params['ece_before'] is None
        assert params['ece_after'] is None
        assert params['ece_improvement'] is None
    
    def test_get_params_fitted(self):
        """Test get_params on fitted calibrator."""
        np.random.seed(42)
        n_samples = 100
        
        y_true = np.random.randint(0, 2, n_samples)
        y_pred_probs = np.random.uniform(0.1, 0.9, n_samples)
        
        calibrator = IsotonicCalibrator()
        calibrator.fit(y_true, y_pred_probs)
        
        params = calibrator.get_params()
        
        assert params['is_fitted'] is True
        assert params['n_samples'] == n_samples
        assert params['ece_before'] is not None
        assert params['ece_after'] is not None
        assert params['ece_improvement'] is not None
        assert params['ece_improvement'] >= 0  # Should improve or stay same


class TestIntegration:
    """Integration tests for complete workflows."""
    
    def test_full_workflow(self):
        """Test complete workflow: fit → transform → save → load."""
        np.random.seed(42)
        
        # Generate training data
        n_train = 500
        true_probs_train = np.random.uniform(0.2, 0.8, n_train)
        y_train = (np.random.rand(n_train) < true_probs_train).astype(int)
        y_pred_train = np.clip(true_probs_train * 1.2, 0, 1)  # Overconfident
        
        # Generate test data
        n_test = 100
        true_probs_test = np.random.uniform(0.2, 0.8, n_test)
        y_test = (np.random.rand(n_test) < true_probs_test).astype(int)
        y_pred_test = np.clip(true_probs_test * 1.2, 0, 1)
        
        # Fit calibrator on training data
        calibrator = IsotonicCalibrator()
        calibrator.fit(y_train, y_pred_train)
        
        # Check improvement on training data
        assert calibrator.ece_after_ < calibrator.ece_before_
        
        # Transform test data
        y_pred_test_calibrated = calibrator.transform(y_pred_test)
        
        # Calibrated predictions should have better ECE on test data
        ece_before_test = expected_calibration_error(y_test, y_pred_test)
        ece_after_test = expected_calibration_error(y_test, y_pred_test_calibrated)
        
        # Calibration should help (or at least not hurt significantly)
        assert ece_after_test <= ece_before_test + 0.01
        
        # Get reliability diagram
        diagram_data = calibrator.get_reliability_diagram_data(
            y_test,
            y_pred_test,
            y_pred_test_calibrated
        )
        
        assert 'uncalibrated_predicted' in diagram_data
        assert 'calibrated_predicted' in diagram_data
        
        # Get params
        params = calibrator.get_params()
        assert params['is_fitted'] is True
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Save
            save_path = Path(tmpdir) / 'calibrator.pkl'
            calibrator.save(save_path)
            assert save_path.exists()
            
            # Load
            loaded_calibrator = IsotonicCalibrator.load(save_path)
            
            # Verify loaded calibrator produces same results
            y_pred_test_calibrated_loaded = loaded_calibrator.transform(y_pred_test)
            assert np.allclose(y_pred_test_calibrated, y_pred_test_calibrated_loaded)

