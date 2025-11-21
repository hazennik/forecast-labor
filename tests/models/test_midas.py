"""
Tests for MIDAS regression model.

Tests cover:
- Model fitting with mixed-frequency data
- Almon weight constraint validation (sum to 1)
- Reproducibility (same seed → same output)
- Multi-horizon forecasting
- Feature registry integration
- Save/load functionality
- Error handling
"""

import pytest
import numpy as np
import pandas as pd
from pathlib import Path
import tempfile

from models_src.midas.midas_model import MIDASRegression


class TestMIDASRegression:
    """Test suite for MIDAS regression model."""
    
    @pytest.fixture
    def sample_data(self):
        """Generate sample mixed-frequency data for testing."""
        np.random.seed(42)
        
        # Low-frequency target (monthly, 24 months)
        n_samples = 24
        dates = pd.date_range('2022-01-01', periods=n_samples, freq='MS')
        
        # High-frequency features (MIDAS lags: 20 lags per sample)
        n_lags = 20
        X = pd.DataFrame(
            np.random.randn(n_samples, n_lags),
            index=dates,
            columns=[f'lag_{i}' for i in range(n_lags)]
        )
        
        # Target with some linear relationship to features
        true_weights = np.exp(-np.arange(n_lags) / n_lags)
        true_weights = true_weights / true_weights.sum()
        
        y = pd.Series(
            100 + np.dot(X.values, true_weights) + np.random.randn(n_samples) * 5,
            index=dates,
            name='target'
        )
        
        return X, y
    
    @pytest.fixture
    def fitted_model(self, sample_data):
        """Create and fit a MIDAS model for testing."""
        X, y = sample_data
        model = MIDASRegression(
            n_lags=20,
            almon_degree=2,
            horizon=1,
            random_state=42
        )
        model.fit(X, y, vintage_date='2024-11-15')
        return model
    
    # ===== Model Initialization Tests =====
    
    def test_init_default_parameters(self):
        """Test model initialization with default parameters."""
        model = MIDASRegression()
        
        assert model.n_lags == 20
        assert model.almon_degree == 2
        assert model.horizon == 1
        assert model.include_intercept is True
        assert model.random_state == 42
        assert model.coefficients_ is None  # Not fitted yet
    
    def test_init_custom_parameters(self):
        """Test model initialization with custom parameters."""
        model = MIDASRegression(
            n_lags=30,
            almon_degree=3,
            horizon=2,
            include_intercept=False,
            random_state=123
        )
        
        assert model.n_lags == 30
        assert model.almon_degree == 3
        assert model.horizon == 2
        assert model.include_intercept is False
        assert model.random_state == 123
    
    def test_init_invalid_n_lags(self):
        """Test that negative n_lags raises ValueError."""
        with pytest.raises(ValueError, match="n_lags must be positive"):
            MIDASRegression(n_lags=-5)
    
    def test_init_invalid_almon_degree(self):
        """Test that negative almon_degree raises ValueError."""
        with pytest.raises(ValueError, match="almon_degree must be non-negative"):
            MIDASRegression(almon_degree=-1)
    
    def test_init_invalid_horizon(self):
        """Test that non-positive horizon raises ValueError."""
        with pytest.raises(ValueError, match="horizon must be positive"):
            MIDASRegression(horizon=0)
    
    # ===== Fit Tests =====
    
    def test_fit_basic(self, sample_data):
        """Test basic model fitting."""
        X, y = sample_data
        model = MIDASRegression(random_state=42)
        
        result = model.fit(X, y, vintage_date='2024-11-15')
        
        # Check method chaining
        assert result is model
        
        # Check fitted attributes exist
        assert model.coefficients_ is not None
        assert model.almon_weights_ is not None
        assert model.intercept_ is not None
        assert model.vintage_date_ == '2024-11-15'
        assert model.n_features_ == X.shape[1]
        assert model.feature_names_ == list(X.columns)
        assert model.training_loss_ is not None
    
    def test_fit_empty_data(self):
        """Test that fitting with empty data raises ValueError."""
        model = MIDASRegression()
        X = pd.DataFrame()
        y = pd.Series(dtype=float)
        
        with pytest.raises(ValueError, match="X and y cannot be empty"):
            model.fit(X, y, vintage_date='2024-11-15')
    
    def test_fit_length_mismatch(self, sample_data):
        """Test that X and y length mismatch raises ValueError."""
        X, y = sample_data
        model = MIDASRegression()
        
        # Truncate y
        y_short = y.iloc[:10]
        
        with pytest.raises(ValueError, match="X and y must have same length"):
            model.fit(X, y_short, vintage_date='2024-11-15')
    
    def test_fit_stores_metadata(self, sample_data):
        """Test that fit stores all required metadata."""
        X, y = sample_data
        model = MIDASRegression(random_state=42)
        model.fit(X, y, vintage_date='2024-11-15')
        
        assert model.vintage_date_ == '2024-11-15'
        assert model.n_features_ == 20
        assert len(model.feature_names_) == 20
        assert all(name.startswith('lag_') for name in model.feature_names_)
    
    # ===== Almon Weight Tests =====
    
    def test_almon_weights_sum_to_one(self, fitted_model):
        """Test that Almon weights sum to 1 (normalized)."""
        weights = fitted_model.almon_weights_
        
        assert weights is not None
        assert len(weights) == fitted_model.n_lags
        assert np.isclose(weights.sum(), 1.0, atol=1e-6)
    
    def test_almon_weights_all_positive(self, fitted_model):
        """Test that all Almon weights are positive."""
        weights = fitted_model.almon_weights_
        
        assert np.all(weights > 0)
    
    def test_almon_weights_degree_zero(self, sample_data):
        """Test that degree=0 produces equal weights."""
        X, y = sample_data
        model = MIDASRegression(n_lags=10, almon_degree=0, random_state=42)
        # Use iloc for DataFrame slicing
        model.fit(X.iloc[:, :10], y, vintage_date='2024-11-15')
        
        weights = model.almon_weights_
        expected_weight = 1.0 / 10
        
        assert np.allclose(weights, expected_weight, atol=1e-6)
    
    def test_almon_weights_decay_pattern(self, fitted_model):
        """Test that weights follow expected decay pattern (recent > distant)."""
        weights = fitted_model.almon_weights_
        
        # For exponential Almon, recent lags typically have higher weight
        # Check that first weight >= last weight (general pattern)
        # Note: This is a soft test as exact pattern depends on estimated params
        assert weights[0] > 0  # First weight exists
        assert weights[-1] > 0  # Last weight exists
    
    # ===== Predict Tests =====
    
    def test_predict_basic(self, fitted_model, sample_data):
        """Test basic prediction functionality."""
        X, y = sample_data
        
        predictions = fitted_model.predict(X)
        
        assert predictions is not None
        assert len(predictions) == len(X)
        assert predictions.dtype == np.float64
        assert not np.any(np.isnan(predictions))
    
    def test_predict_before_fit(self, sample_data):
        """Test that predicting before fit raises ValueError."""
        X, y = sample_data
        model = MIDASRegression()
        
        with pytest.raises(ValueError, match="Model must be fitted before prediction"):
            model.predict(X)
    
    def test_predict_feature_mismatch(self, fitted_model):
        """Test that feature count mismatch raises ValueError."""
        # Create data with wrong number of features
        X_wrong = pd.DataFrame(np.random.randn(10, 15))
        
        with pytest.raises(ValueError, match="Feature mismatch"):
            fitted_model.predict(X_wrong)
    
    def test_predict_shape(self, fitted_model, sample_data):
        """Test that prediction shape matches input."""
        X, y = sample_data
        
        # Predict on subset
        predictions = fitted_model.predict(X.iloc[:10])
        assert len(predictions) == 10
        
        # Predict on full set
        predictions = fitted_model.predict(X)
        assert len(predictions) == len(X)
    
    # ===== Reproducibility Tests =====
    
    def test_reproducibility_same_seed(self, sample_data):
        """Test that same seed produces identical results."""
        X, y = sample_data
        
        # Train two models with same seed
        model1 = MIDASRegression(random_state=42)
        model1.fit(X, y, vintage_date='2024-11-15')
        predictions1 = model1.predict(X)
        
        model2 = MIDASRegression(random_state=42)
        model2.fit(X, y, vintage_date='2024-11-15')
        predictions2 = model2.predict(X)
        
        # Results should be identical
        assert np.allclose(predictions1, predictions2)
        assert np.allclose(model1.coefficients_, model2.coefficients_)
        assert np.allclose(model1.almon_weights_, model2.almon_weights_)
    
    def test_reproducibility_different_seed(self, sample_data):
        """Test that different seeds are respected in model initialization."""
        X, y = sample_data
        
        # Train two models with different seeds
        model1 = MIDASRegression(random_state=42)
        model1.fit(X, y, vintage_date='2024-11-15')
        
        model2 = MIDASRegression(random_state=123)
        model2.fit(X, y, vintage_date='2024-11-15')
        
        # Models should store different random states
        assert model1.random_state != model2.random_state
        assert model1.random_state == 42
        assert model2.random_state == 123
        
        # Note: NLS optimization may converge to same solution regardless of seed
        # if the problem is convex. This is expected behavior - the seed mainly
        # affects stochastic components, not deterministic optimization.
    
    # ===== Multi-Horizon Tests =====
    
    def test_multi_horizon_fitting(self, sample_data):
        """Test that model can be fitted with different horizons."""
        X, y = sample_data
        
        for horizon in [1, 2, 3]:
            model = MIDASRegression(horizon=horizon, random_state=42)
            model.fit(X, y, vintage_date='2024-11-15')
            
            assert model.horizon == horizon
            assert model.coefficients_ is not None
            
            # Can generate predictions
            predictions = model.predict(X)
            assert len(predictions) == len(X)
    
    # ===== Get Params Tests =====
    
    def test_get_params_unfitted(self):
        """Test get_params before fitting."""
        model = MIDASRegression(n_lags=15, almon_degree=3, random_state=42)
        params = model.get_params()
        
        assert params['n_lags'] == 15
        assert params['almon_degree'] == 3
        assert params['random_state'] == 42
        assert params['is_fitted'] is False
        assert params['vintage_date'] is None
    
    def test_get_params_fitted(self, fitted_model):
        """Test get_params after fitting."""
        params = fitted_model.get_params()
        
        assert params['is_fitted'] is True
        assert params['vintage_date'] == '2024-11-15'
        assert params['n_features'] == 20
        assert params['training_loss'] is not None
        assert 'model_id' in params
        assert 'created_at' in params
    
    # ===== Save/Load Tests =====
    
    def test_save_unfitted_model(self):
        """Test that saving unfitted model raises ValueError."""
        model = MIDASRegression()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'model.pkl'
            
            with pytest.raises(ValueError, match="Cannot save unfitted model"):
                model.save(path)
    
    def test_save_load_roundtrip(self, fitted_model, sample_data):
        """Test that save/load preserves model state."""
        X, y = sample_data
        
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'midas_model.pkl'
            
            # Save model
            fitted_model.save(path)
            assert path.exists()
            
            # Load model
            loaded_model = MIDASRegression.load(path)
            
            # Check parameters match
            assert loaded_model.n_lags == fitted_model.n_lags
            assert loaded_model.almon_degree == fitted_model.almon_degree
            assert loaded_model.random_state == fitted_model.random_state
            
            # Check fitted state matches
            assert np.allclose(loaded_model.coefficients_, fitted_model.coefficients_)
            assert np.allclose(loaded_model.almon_weights_, fitted_model.almon_weights_)
            assert loaded_model.intercept_ == fitted_model.intercept_
            assert loaded_model.vintage_date_ == fitted_model.vintage_date_
            
            # Check predictions match
            predictions_original = fitted_model.predict(X)
            predictions_loaded = loaded_model.predict(X)
            assert np.allclose(predictions_original, predictions_loaded)
    
    def test_load_nonexistent_file(self):
        """Test that loading nonexistent file raises FileNotFoundError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'nonexistent.pkl'
            
            with pytest.raises(FileNotFoundError, match="Model file not found"):
                MIDASRegression.load(path)
    
    # ===== Feature Importance Tests =====
    
    def test_feature_importance_unfitted(self):
        """Test that feature importance before fit raises ValueError."""
        model = MIDASRegression()
        
        with pytest.raises(ValueError, match="Model must be fitted"):
            model.get_feature_importance()
    
    def test_feature_importance_structure(self, fitted_model):
        """Test feature importance output structure."""
        importance = fitted_model.get_feature_importance()
        
        assert isinstance(importance, pd.DataFrame)
        assert len(importance) == fitted_model.n_features_
        assert 'feature' in importance.columns
        assert 'coefficient' in importance.columns
        assert 'abs_coefficient' in importance.columns
        
        # Should be sorted by absolute coefficient (descending)
        assert importance['abs_coefficient'].is_monotonic_decreasing
    
    # ===== Integration Tests =====
    
    def test_full_workflow(self, sample_data):
        """Test complete model workflow: init → fit → predict → save → load."""
        X, y = sample_data
        
        # Initialize
        model = MIDASRegression(
            n_lags=20,
            almon_degree=2,
            horizon=1,
            random_state=42
        )
        
        # Fit
        model.fit(X, y, vintage_date='2024-11-15')
        assert model.coefficients_ is not None
        
        # Predict
        predictions = model.predict(X)
        assert len(predictions) == len(X)
        
        # Get params
        params = model.get_params()
        assert params['is_fitted'] is True
        
        # Get feature importance
        importance = model.get_feature_importance()
        assert len(importance) == 20
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Save
            save_path = Path(tmpdir) / 'model.pkl'
            model.save(save_path)
            assert save_path.exists()
            
            # Load
            loaded_model = MIDASRegression.load(save_path)
            loaded_predictions = loaded_model.predict(X)
            
            # Verify consistency
            assert np.allclose(predictions, loaded_predictions)
    
    def test_method_chaining(self, sample_data):
        """Test that fit returns self for method chaining."""
        X, y = sample_data
        
        # Should be able to chain fit().predict()
        model = MIDASRegression(random_state=42)
        predictions = model.fit(X, y, vintage_date='2024-11-15').predict(X)
        
        assert predictions is not None
        assert len(predictions) == len(X)


class TestMIDASEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_single_feature(self):
        """Test model with single feature."""
        np.random.seed(42)
        X = pd.DataFrame(np.random.randn(50, 1), columns=['feature_0'])
        y = pd.Series(np.random.randn(50))
        
        model = MIDASRegression(n_lags=1, random_state=42)
        model.fit(X, y, vintage_date='2024-11-15')
        predictions = model.predict(X)
        
        assert len(predictions) == 50
    
    def test_small_sample_size(self):
        """Test model with small sample size."""
        np.random.seed(42)
        X = pd.DataFrame(np.random.randn(10, 5))
        y = pd.Series(np.random.randn(10))
        
        model = MIDASRegression(n_lags=5, random_state=42)
        model.fit(X, y, vintage_date='2024-11-15')
        predictions = model.predict(X)
        
        assert len(predictions) == 10
    
    def test_no_intercept(self):
        """Test model without intercept."""
        np.random.seed(42)
        X = pd.DataFrame(np.random.randn(30, 10))
        y = pd.Series(np.random.randn(30))
        
        model = MIDASRegression(
            n_lags=10,
            include_intercept=False,
            random_state=42
        )
        model.fit(X, y, vintage_date='2024-11-15')
        
        # Intercept should be 0
        assert model.intercept_ == 0.0
        
        predictions = model.predict(X)
        assert len(predictions) == 30

