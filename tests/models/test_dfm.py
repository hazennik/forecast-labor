"""
Tests for Dynamic Factor Model (DFM)

Tests cover:
- Model initialization and inheritance
- Training with mixed-frequency data
- Prediction generation and shape validation
- Reproducibility (determinism)
- Missing data handling (ragged edge)
- Parameter convergence
- Feature registry integration
- Save/load functionality
"""

import pytest
import numpy as np
import pandas as pd
from pathlib import Path
from unittest.mock import Mock, patch
from datetime import datetime, timedelta

from models_src.dfm.dfm_model import DynamicFactorModel
from models_src.utils.base_model import BaseForecaster


class TestDFMInitialization:
    """Test DFM initialization and basic properties"""
    
    def test_inherits_from_base_forecaster(self):
        """DFM should inherit from BaseForecaster"""
        model = DynamicFactorModel(n_factors=2, random_state=42)
        assert isinstance(model, BaseForecaster)
    
    def test_initialization_with_default_params(self):
        """Test initialization with default parameters"""
        model = DynamicFactorModel(n_factors=2)
        assert model.n_factors == 2
        assert model.random_state == 42  # Default from BaseForecaster
        assert hasattr(model, 'model_id')
        assert hasattr(model, 'created_at')
    
    def test_initialization_with_custom_params(self):
        """Test initialization with custom parameters"""
        model = DynamicFactorModel(
            n_factors=3,
            max_iter=100,
            tol=1e-6,
            random_state=123
        )
        assert model.n_factors == 3
        assert model.max_iter == 100
        assert model.tol == 1e-6
        assert model.random_state == 123
    
    def test_initialization_validates_n_factors(self):
        """Test that n_factors must be positive"""
        with pytest.raises(ValueError, match="n_factors must be positive"):
            DynamicFactorModel(n_factors=0)
        
        with pytest.raises(ValueError, match="n_factors must be positive"):
            DynamicFactorModel(n_factors=-1)


class TestDFMFitting:
    """Test DFM training functionality"""
    
    @pytest.fixture
    def sample_data(self):
        """Create synthetic mixed-frequency time series data"""
        np.random.seed(42)
        n_obs = 120  # 10 years of monthly data
        dates = pd.date_range('2014-01-01', periods=n_obs, freq='M')
        
        # Create target (monthly NFP changes)
        y = pd.Series(
            np.random.normal(150, 50, n_obs),
            index=dates,
            name='nfp_change'
        )
        
        # Create features (mixed frequency)
        X = pd.DataFrame({
            # Monthly features
            'ces_employment': np.random.normal(140000, 1000, n_obs),
            'laus_employment': np.random.normal(145000, 1000, n_obs),
            # Weekly features (4 weeks per month, approximate)
            'claims_avg': np.random.normal(250000, 20000, n_obs),
            # Daily features (20 business days per month, approximate)
            'treasury_avg': np.random.normal(5000, 500, n_obs),
        }, index=dates)
        
        return X, y
    
    def test_fit_with_valid_data(self, sample_data):
        """Test fitting with valid data"""
        X, y = sample_data
        model = DynamicFactorModel(n_factors=2, max_iter=10, random_state=42)
        
        result = model.fit(X, y, vintage_date='2024-11-15')
        
        # Should return self for chaining
        assert result is model
        
        # Should store training metadata
        assert model.vintage_date == '2024-11-15'
        assert model.n_features == X.shape[1]
        assert hasattr(model, 'factors_')
        assert hasattr(model, 'loadings_')
        assert hasattr(model, 'is_fitted')
        assert model.is_fitted is True
    
    def test_fit_validates_input_shapes(self):
        """Test that fit validates input shapes"""
        model = DynamicFactorModel(n_factors=2, random_state=42)
        
        X = pd.DataFrame({'a': [1, 2, 3], 'b': [4, 5, 6]})
        y = pd.Series([1, 2])  # Wrong length
        
        with pytest.raises(ValueError, match="X and y must have same length"):
            model.fit(X, y, vintage_date='2024-11-15')
    
    def test_fit_validates_vintage_date_format(self, sample_data):
        """Test that fit validates vintage date format"""
        X, y = sample_data
        model = DynamicFactorModel(n_factors=2, random_state=42)
        
        with pytest.raises(ValueError, match="vintage_date must be in YYYY-MM-DD format"):
            model.fit(X, y, vintage_date='11-15-2024')  # Wrong format
    
    def test_fit_convergence(self, sample_data):
        """Test that statsmodels optimizer metadata is recorded."""
        X, y = sample_data
        model = DynamicFactorModel(
            n_factors=2,
            max_iter=50,
            tol=1e-4,
            random_state=42
        )
        
        model.fit(X, y, vintage_date='2024-11-15')
        
        # Should have convergence info
        assert hasattr(model, 'n_iter_')
        assert model.n_iter_ <= 50  # Converged before max_iter
        assert hasattr(model, 'converged_')
        # Note: May or may not converge depending on data, just check attribute exists
    
    def test_fit_stores_feature_names(self, sample_data):
        """Test that fit stores feature names for validation"""
        X, y = sample_data
        model = DynamicFactorModel(n_factors=2, random_state=42)
        
        model.fit(X, y, vintage_date='2024-11-15')
        
        assert hasattr(model, 'feature_names_')
        assert model.feature_names_ == list(X.columns)


class TestDFMPrediction:
    """Test DFM prediction functionality"""
    
    @pytest.fixture
    def fitted_model(self):
        """Create and fit a DFM for prediction tests"""
        np.random.seed(42)
        n_obs = 120
        dates = pd.date_range('2014-01-01', periods=n_obs, freq='M')
        
        y = pd.Series(np.random.normal(150, 50, n_obs), index=dates)
        X = pd.DataFrame({
            'ces_employment': np.random.normal(140000, 1000, n_obs),
            'laus_employment': np.random.normal(145000, 1000, n_obs),
            'claims_avg': np.random.normal(250000, 20000, n_obs),
            'treasury_avg': np.random.normal(5000, 500, n_obs),
        }, index=dates)
        
        model = DynamicFactorModel(n_factors=2, max_iter=10, random_state=42)
        model.fit(X, y, vintage_date='2024-11-15')
        
        return model, X
    
    def test_predict_without_fit_raises_error(self):
        """Test that predict raises error if model not fitted"""
        model = DynamicFactorModel(n_factors=2, random_state=42)
        X = pd.DataFrame({'a': [1, 2, 3], 'b': [4, 5, 6]})
        
        with pytest.raises(ValueError, match="Model must be fitted before prediction"):
            model.predict(X)
    
    def test_predict_returns_correct_shape(self, fitted_model):
        """Test that predict returns correct shape"""
        model, X_train = fitted_model
        
        # Predict on new data
        X_test = X_train.iloc[:10]  # First 10 samples
        predictions = model.predict(X_test)
        
        assert predictions.shape == (10,)
        assert isinstance(predictions, np.ndarray)
    
    def test_predict_validates_feature_names(self, fitted_model):
        """Test that predict validates feature names match training"""
        model, X_train = fitted_model
        
        # Wrong feature names
        X_wrong = pd.DataFrame({
            'wrong_feature_1': [1, 2, 3],
            'wrong_feature_2': [4, 5, 6],
        })
        
        with pytest.raises(ValueError, match="Feature names do not match training"):
            model.predict(X_wrong)
    
    def test_predict_handles_missing_columns(self, fitted_model):
        """Test that predict detects missing columns"""
        model, X_train = fitted_model
        
        # Missing one column
        X_missing = X_train[['ces_employment', 'laus_employment']].iloc[:10]
        
        with pytest.raises(ValueError, match="Feature names do not match training"):
            model.predict(X_missing)
    
    def test_predict_returns_finite_values(self, fitted_model):
        """Test that predictions are finite (no NaN/Inf)"""
        model, X_train = fitted_model
        
        predictions = model.predict(X_train.iloc[:10])
        
        assert np.all(np.isfinite(predictions))


class TestDFMReproducibility:
    """Test DFM reproducibility and determinism"""
    
    @pytest.fixture
    def sample_data(self):
        """Create consistent data for reproducibility tests"""
        np.random.seed(42)
        n_obs = 100
        dates = pd.date_range('2014-01-01', periods=n_obs, freq='M')
        
        y = pd.Series(np.random.normal(150, 50, n_obs), index=dates)
        X = pd.DataFrame({
            'feature_1': np.random.normal(1000, 100, n_obs),
            'feature_2': np.random.normal(2000, 200, n_obs),
        }, index=dates)
        
        return X, y
    
    def test_same_seed_produces_identical_results(self, sample_data):
        """Test that same seed produces identical model parameters"""
        X, y = sample_data
        
        # Train two models with same seed
        model1 = DynamicFactorModel(n_factors=2, max_iter=20, random_state=42)
        model1.fit(X, y, vintage_date='2024-11-15')
        
        model2 = DynamicFactorModel(n_factors=2, max_iter=20, random_state=42)
        model2.fit(X, y, vintage_date='2024-11-15')
        
        # Parameters should be identical
        np.testing.assert_array_almost_equal(
            model1.loadings_,
            model2.loadings_,
            decimal=10
        )
        
        # Predictions should be identical
        X_test = X.iloc[:10]
        pred1 = model1.predict(X_test)
        pred2 = model2.predict(X_test)
        
        np.testing.assert_array_almost_equal(pred1, pred2, decimal=10)
    
    def test_different_seed_preserves_deterministic_statsmodels_solution(self, sample_data):
        """Statsmodels MLE should be deterministic for the same data."""
        X, y = sample_data
        
        model1 = DynamicFactorModel(n_factors=2, max_iter=20, random_state=42)
        model1.fit(X, y, vintage_date='2024-11-15')
        
        model2 = DynamicFactorModel(n_factors=2, max_iter=20, random_state=123)
        model2.fit(X, y, vintage_date='2024-11-15')
        
        X_test = X.iloc[:5]
        pred1 = model1.predict(X_test)
        pred2 = model2.predict(X_test)
        
        np.testing.assert_array_almost_equal(pred1, pred2, decimal=8)


class TestDFMMissingData:
    """Test DFM handling of missing data (ragged edge)"""
    
    def test_fit_with_missing_values(self):
        """Test that DFM can handle missing values in training"""
        np.random.seed(42)
        n_obs = 100
        dates = pd.date_range('2014-01-01', periods=n_obs, freq='M')
        
        # Create data with missing values
        X = pd.DataFrame({
            'feature_1': np.random.normal(1000, 100, n_obs),
            'feature_2': np.random.normal(2000, 200, n_obs),
        }, index=dates)
        
        # Introduce missing values (last 10 observations for feature_2)
        X.loc[dates[-10:], 'feature_2'] = np.nan
        
        y = pd.Series(np.random.normal(150, 50, n_obs), index=dates)
        
        # Should fit without error
        model = DynamicFactorModel(n_factors=1, max_iter=10, random_state=42)
        model.fit(X, y, vintage_date='2024-11-15')
        
        assert model.is_fitted is True
    
    def test_predict_with_missing_values(self):
        """Test that DFM can make predictions with missing values"""
        np.random.seed(42)
        n_obs = 100
        dates = pd.date_range('2014-01-01', periods=n_obs, freq='M')
        
        X = pd.DataFrame({
            'feature_1': np.random.normal(1000, 100, n_obs),
            'feature_2': np.random.normal(2000, 200, n_obs),
        }, index=dates)
        y = pd.Series(np.random.normal(150, 50, n_obs), index=dates)
        
        model = DynamicFactorModel(n_factors=1, max_iter=10, random_state=42)
        model.fit(X, y, vintage_date='2024-11-15')
        
        # Create test data with missing values
        X_test = X.iloc[:10].copy()
        # Introduce missing values in last 5 rows of feature_2
        X_test.iloc[5:, X_test.columns.get_loc('feature_2')] = np.nan
        
        # Should predict without error
        predictions = model.predict(X_test)
        
        assert predictions.shape == (10,)
        assert np.all(np.isfinite(predictions))


class TestDFMGetParams:
    """Test DFM get_params functionality"""
    
    def test_get_params_before_fit(self):
        """Test get_params before fitting"""
        model = DynamicFactorModel(
            n_factors=3,
            max_iter=100,
            tol=1e-6,
            random_state=42
        )
        
        params = model.get_params()
        
        assert params['n_factors'] == 3
        assert params['max_iter'] == 100
        assert params['tol'] == 1e-6
        assert params['random_state'] == 42
        assert params['is_fitted'] is False
        assert params['vintage_date'] is None
    
    def test_get_params_after_fit(self):
        """Test get_params after fitting"""
        np.random.seed(42)
        n_obs = 50
        dates = pd.date_range('2014-01-01', periods=n_obs, freq='M')
        
        X = pd.DataFrame({
            'feature_1': np.random.normal(1000, 100, n_obs),
            'feature_2': np.random.normal(2000, 200, n_obs),
        }, index=dates)
        y = pd.Series(np.random.normal(150, 50, n_obs), index=dates)
        
        model = DynamicFactorModel(n_factors=2, random_state=42)
        model.fit(X, y, vintage_date='2024-11-15')
        
        params = model.get_params()
        
        assert params['is_fitted'] is True
        assert params['vintage_date'] == '2024-11-15'
        assert params['n_features'] == 2
        assert 'n_iter_' in params


class TestDFMSaveLoad:
    """Test DFM save/load functionality"""
    
    @pytest.fixture
    def fitted_model_and_path(self, tmp_path):
        """Create fitted model and temp path"""
        np.random.seed(42)
        n_obs = 50
        dates = pd.date_range('2014-01-01', periods=n_obs, freq='M')
        
        X = pd.DataFrame({
            'feature_1': np.random.normal(1000, 100, n_obs),
            'feature_2': np.random.normal(2000, 200, n_obs),
        }, index=dates)
        y = pd.Series(np.random.normal(150, 50, n_obs), index=dates)
        
        model = DynamicFactorModel(n_factors=2, max_iter=10, random_state=42)
        model.fit(X, y, vintage_date='2024-11-15')
        
        save_path = tmp_path / "test_dfm_model.pkl"
        return model, save_path, X
    
    def test_save_creates_file(self, fitted_model_and_path):
        """Test that save creates a file"""
        model, save_path, _ = fitted_model_and_path
        
        model.save(save_path)
        
        assert save_path.exists()
        assert save_path.stat().st_size > 0
    
    def test_load_restores_model(self, fitted_model_and_path):
        """Test that load restores model state"""
        original_model, save_path, X = fitted_model_and_path
        
        # Save model
        original_model.save(save_path)
        
        # Load model
        loaded_model = DynamicFactorModel.load(save_path)
        
        # Check basic attributes
        assert loaded_model.n_factors == original_model.n_factors
        assert loaded_model.random_state == original_model.random_state
        assert loaded_model.vintage_date == original_model.vintage_date
        assert loaded_model.is_fitted is True
        
        # Check parameters match
        np.testing.assert_array_almost_equal(
            loaded_model.loadings_,
            original_model.loadings_
        )
        
        # Check predictions match
        X_test = X.iloc[:5]
        pred_original = original_model.predict(X_test)
        pred_loaded = loaded_model.predict(X_test)
        
        np.testing.assert_array_almost_equal(pred_original, pred_loaded)
    
    def test_save_without_fit_raises_error(self, tmp_path):
        """Test that save raises error if model not fitted"""
        model = DynamicFactorModel(n_factors=2, random_state=42)
        save_path = tmp_path / "test_model.pkl"
        
        with pytest.raises(ValueError, match="Model must be fitted before saving"):
            model.save(save_path)


class TestDFMFeatureRegistryIntegration:
    """Test DFM integration with feature registry"""
    
    def test_fit_stores_feature_metadata(self):
        """Test that fit stores feature metadata for registry integration"""
        np.random.seed(42)
        n_obs = 50
        dates = pd.date_range('2014-01-01', periods=n_obs, freq='M')
        
        X = pd.DataFrame({
            'feature_1': np.random.normal(1000, 100, n_obs),
            'feature_2': np.random.normal(2000, 200, n_obs),
        }, index=dates)
        y = pd.Series(np.random.normal(150, 50, n_obs), index=dates)
        
        # Fit model (should store feature metadata)
        model = DynamicFactorModel(n_factors=2, max_iter=10, random_state=42)
        model.fit(X, y, vintage_date='2024-11-15')
        
        # Should store feature metadata
        assert hasattr(model, 'feature_metadata_')
        assert model.feature_metadata_['feature_names'] == list(X.columns)
        assert model.feature_metadata_['vintage_date'] == '2024-11-15'
        assert model.feature_metadata_['n_features'] == 2
    
    def test_get_params_includes_feature_metadata(self):
        """Test that get_params includes feature metadata"""
        np.random.seed(42)
        n_obs = 50
        dates = pd.date_range('2014-01-01', periods=n_obs, freq='M')
        
        X = pd.DataFrame({
            'feature_1': np.random.normal(1000, 100, n_obs),
            'feature_2': np.random.normal(2000, 200, n_obs),
        }, index=dates)
        y = pd.Series(np.random.normal(150, 50, n_obs), index=dates)
        
        model = DynamicFactorModel(n_factors=2, max_iter=10, random_state=42)
        model.fit(X, y, vintage_date='2024-11-15')
        
        params = model.get_params()
        
        assert 'feature_metadata' in params
        assert params['feature_metadata']['feature_names'] == ['feature_1', 'feature_2']
        assert params['feature_metadata']['vintage_date'] == '2024-11-15'

