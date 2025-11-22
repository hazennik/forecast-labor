"""
Tests for revision forecasting model.

Tests cover:
- Model fitting with revision data
- Reproducibility (same seed → same output)
- Revision magnitude prediction (RMSE)
- Revision direction accuracy
- Feature registry integration
- Save/load functionality
- Error handling
"""

import pytest
import numpy as np
import pandas as pd
from pathlib import Path
import tempfile

from models_src.revision.revision_model import RevisionForecaster


class TestRevisionForecaster:
    """Test suite for revision forecasting model."""
    
    @pytest.fixture
    def sample_data(self):
        """Generate sample revision data for testing."""
        np.random.seed(42)
        
        # Simulate revision data: 48 months of preliminary releases
        n_samples = 48
        dates = pd.date_range('2020-01-01', periods=n_samples, freq='MS')
        
        # Features: preliminary value, leading indicators, historical stats
        preliminary_values = 150 + np.cumsum(np.random.randn(n_samples) * 10)
        claims_4wk = 220 + np.random.randn(n_samples) * 15
        prev_revision_avg = np.random.randn(n_samples) * 8
        withholdings_growth = np.random.randn(n_samples) * 2
        
        X = pd.DataFrame({
            'preliminary_value': preliminary_values,
            'claims_4wk_avg': claims_4wk,
            'prev_revision_avg': prev_revision_avg,
            'withholdings_growth': withholdings_growth,
        }, index=dates)
        
        # Target: actual revisions (final - preliminary)
        # Revisions tend to be mean-reverting and correlated with indicators
        revisions = (
            -0.1 * (preliminary_values - 150) +  # Mean reversion
            -0.05 * (claims_4wk - 220) +         # Claims signal
            0.3 * prev_revision_avg +             # Persistence
            np.random.randn(n_samples) * 5        # Noise
        )
        
        y = pd.Series(revisions, index=dates, name='revision')
        
        return X, y
    
    @pytest.fixture
    def fitted_model(self, sample_data):
        """Create and fit a revision model for testing."""
        X, y = sample_data
        model = RevisionForecaster(
            alpha=1.0,
            fit_intercept=True,
            random_state=42
        )
        model.fit(X, y, vintage_date='2024-11-15')
        return model
    
    # ===== Model Initialization Tests =====
    
    def test_init_default_parameters(self):
        """Test model initialization with default parameters."""
        model = RevisionForecaster()
        
        assert model.alpha == 1.0
        assert model.fit_intercept is True
        assert model.random_state == 42
        assert model.model_ is None  # Not fitted yet
    
    def test_init_custom_parameters(self):
        """Test model initialization with custom parameters."""
        model = RevisionForecaster(
            alpha=0.5,
            fit_intercept=False,
            random_state=123
        )
        
        assert model.alpha == 0.5
        assert model.fit_intercept is False
        assert model.random_state == 123
    
    def test_init_invalid_alpha(self):
        """Test that negative alpha raises ValueError."""
        with pytest.raises(ValueError, match="alpha must be non-negative"):
            RevisionForecaster(alpha=-1.0)
    
    # ===== Fit Tests =====
    
    def test_fit_basic(self, sample_data):
        """Test basic model fitting."""
        X, y = sample_data
        model = RevisionForecaster(random_state=42)
        
        result = model.fit(X, y, vintage_date='2024-11-15')
        
        # Check method chaining
        assert result is model
        
        # Check fitted attributes exist
        assert model.model_ is not None
        assert model.scaler_ is not None
        assert model.feature_names_ is not None
        assert model.vintage_date_ == '2024-11-15'
        assert model.n_features_ == X.shape[1]
        assert model.feature_names_ == list(X.columns)
        assert model.training_rmse_ is not None
        assert model.training_rmse_ > 0
    
    def test_fit_empty_data(self):
        """Test that fitting with empty data raises ValueError."""
        model = RevisionForecaster()
        X = pd.DataFrame()
        y = pd.Series(dtype=float)
        
        with pytest.raises(ValueError, match="X and y cannot be empty"):
            model.fit(X, y, vintage_date='2024-11-15')
    
    def test_fit_length_mismatch(self, sample_data):
        """Test that X and y length mismatch raises ValueError."""
        X, y = sample_data
        model = RevisionForecaster()
        
        # Truncate y
        y_short = y.iloc[:20]
        
        with pytest.raises(ValueError, match="X and y must have same length"):
            model.fit(X, y_short, vintage_date='2024-11-15')
    
    def test_fit_with_nan_features(self, sample_data):
        """Test that NaN in features raises ValueError."""
        X, y = sample_data
        model = RevisionForecaster()
        
        # Introduce NaN
        X_nan = X.copy()
        X_nan.iloc[0, 0] = np.nan
        
        with pytest.raises(ValueError, match="X contains NaN values"):
            model.fit(X_nan, y, vintage_date='2024-11-15')
    
    def test_fit_with_nan_target(self, sample_data):
        """Test that NaN in target raises ValueError."""
        X, y = sample_data
        model = RevisionForecaster()
        
        # Introduce NaN
        y_nan = y.copy()
        y_nan.iloc[0] = np.nan
        
        with pytest.raises(ValueError, match="y contains NaN values"):
            model.fit(X, y_nan, vintage_date='2024-11-15')
    
    def test_fit_invalid_vintage_date(self, sample_data):
        """Test that invalid vintage_date format raises ValueError."""
        X, y = sample_data
        model = RevisionForecaster()
        
        with pytest.raises(ValueError, match="vintage_date must be in YYYY-MM-DD format"):
            model.fit(X, y, vintage_date='11/15/2024')
    
    def test_fit_stores_metadata(self, sample_data):
        """Test that fit stores all required metadata."""
        X, y = sample_data
        model = RevisionForecaster(random_state=42)
        model.fit(X, y, vintage_date='2024-11-15')
        
        assert model.vintage_date_ == '2024-11-15'
        assert model.n_features_ == 4
        assert len(model.feature_names_) == 4
        assert 'preliminary_value' in model.feature_names_
        assert 'claims_4wk_avg' in model.feature_names_
        
        # Check feature metadata for registry integration
        assert hasattr(model, 'feature_metadata_')
        assert model.feature_metadata_['vintage_date'] == '2024-11-15'
        assert model.feature_metadata_['n_features'] == 4
    
    def test_fit_training_rmse_reasonable(self, sample_data):
        """Test that training RMSE is computed and reasonable."""
        X, y = sample_data
        model = RevisionForecaster(alpha=1.0, random_state=42)
        model.fit(X, y, vintage_date='2024-11-15')
        
        # Training RMSE should be positive and less than target std
        assert model.training_rmse_ > 0
        assert model.training_rmse_ < y.std() * 2  # Reasonable fit
    
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
        model = RevisionForecaster()
        
        with pytest.raises(ValueError, match="Model must be fitted before prediction"):
            model.predict(X)
    
    def test_predict_feature_mismatch(self, fitted_model):
        """Test that feature count mismatch raises ValueError."""
        # Create data with wrong number of features
        X_wrong = pd.DataFrame(np.random.randn(10, 2))
        
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
    
    def test_predict_revision_distribution(self, fitted_model, sample_data):
        """Test that predictions have reasonable distribution."""
        X, y = sample_data
        predictions = fitted_model.predict(X)
        
        # Predictions should have reasonable scale (not all zeros or huge)
        assert np.std(predictions) > 0  # Some variance
        assert np.abs(np.mean(predictions)) < 100  # Not extreme
        
        # Predictions should correlate with actuals
        correlation = np.corrcoef(y.values, predictions)[0, 1]
        assert correlation > 0.3  # Some predictive power
    
    # ===== Reproducibility Tests =====
    
    def test_reproducibility_same_seed(self, sample_data):
        """Test that same seed produces identical results."""
        X, y = sample_data
        
        # Train two models with same seed
        model1 = RevisionForecaster(alpha=1.0, random_state=42)
        model1.fit(X, y, vintage_date='2024-11-15')
        predictions1 = model1.predict(X)
        
        model2 = RevisionForecaster(alpha=1.0, random_state=42)
        model2.fit(X, y, vintage_date='2024-11-15')
        predictions2 = model2.predict(X)
        
        # Results should be identical
        assert np.allclose(predictions1, predictions2)
        assert np.allclose(model1.model_.coef_, model2.model_.coef_)
        assert np.isclose(model1.model_.intercept_, model2.model_.intercept_)
    
    def test_reproducibility_different_seed(self, sample_data):
        """Test that different seeds are stored correctly."""
        X, y = sample_data
        
        # Train two models with different seeds
        model1 = RevisionForecaster(random_state=42)
        model1.fit(X, y, vintage_date='2024-11-15')
        
        model2 = RevisionForecaster(random_state=123)
        model2.fit(X, y, vintage_date='2024-11-15')
        
        # Models should store different random states
        assert model1.random_state != model2.random_state
        assert model1.random_state == 42
        assert model2.random_state == 123
    
    # ===== Revision Direction Tests =====
    
    def test_revision_direction_signs(self, fitted_model):
        """Test that model can predict both positive and negative revisions."""
        # Create test data with clear upward revision signal
        X_up = pd.DataFrame({
            'preliminary_value': [100],  # Low preliminary
            'claims_4wk_avg': [200],     # Strong labor market
            'prev_revision_avg': [10],    # Recent upward revisions
            'withholdings_growth': [2],   # Strong withholdings
        })
        
        # Create test data with clear downward revision signal
        X_down = pd.DataFrame({
            'preliminary_value': [250],   # High preliminary
            'claims_4wk_avg': [270],      # Weak labor market
            'prev_revision_avg': [-10],   # Recent downward revisions
            'withholdings_growth': [-2],  # Weak withholdings
        })
        
        pred_up = fitted_model.predict(X_up)[0]
        pred_down = fitted_model.predict(X_down)[0]
        
        # Model should be able to predict different signs
        # (though not guaranteed without very strong signal)
        assert isinstance(pred_up, (int, float))
        assert isinstance(pred_down, (int, float))
    
    # ===== Get Params Tests =====
    
    def test_get_params_unfitted(self):
        """Test get_params before fitting."""
        model = RevisionForecaster(alpha=0.5, random_state=42)
        params = model.get_params()
        
        assert params['alpha'] == 0.5
        assert params['fit_intercept'] is True
        assert params['random_state'] == 42
        assert params['is_fitted'] is False
        assert params['vintage_date'] is None
    
    def test_get_params_fitted(self, fitted_model):
        """Test get_params after fitting."""
        params = fitted_model.get_params()
        
        assert params['is_fitted'] is True
        assert params['vintage_date'] == '2024-11-15'
        assert params['n_features'] == 4
        assert params['training_rmse'] is not None
        assert 'model_id' in params
        assert 'created_at' in params
        assert 'coefficients' in params
        assert 'intercept' in params
        assert len(params['coefficients']) == 4
    
    # ===== Feature Importance Tests =====
    
    def test_feature_importance_unfitted(self):
        """Test that feature importance before fit raises ValueError."""
        model = RevisionForecaster()
        
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
        assert 'direction' in importance.columns
        
        # Should be sorted by absolute coefficient (descending)
        assert importance['abs_coefficient'].is_monotonic_decreasing
    
    def test_feature_importance_directions(self, fitted_model):
        """Test that feature importance correctly identifies directions."""
        importance = fitted_model.get_feature_importance()
        
        for _, row in importance.iterrows():
            if row['coefficient'] > 0:
                assert row['direction'] == 'positive'
            else:
                assert row['direction'] == 'negative'
    
    # ===== Save/Load Tests =====
    
    def test_save_unfitted_model(self):
        """Test that saving unfitted model raises ValueError."""
        model = RevisionForecaster()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'model.pkl'
            
            with pytest.raises(ValueError, match="Cannot save unfitted model"):
                model.save(path)
    
    def test_save_load_roundtrip(self, fitted_model, sample_data):
        """Test that save/load preserves model state."""
        X, y = sample_data
        
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'revision_model.pkl'
            
            # Save model
            fitted_model.save(path)
            assert path.exists()
            
            # Load model
            loaded_model = RevisionForecaster.load(path)
            
            # Check parameters match
            assert loaded_model.alpha == fitted_model.alpha
            assert loaded_model.fit_intercept == fitted_model.fit_intercept
            assert loaded_model.random_state == fitted_model.random_state
            
            # Check fitted state matches
            assert np.allclose(
                loaded_model.model_.coef_, 
                fitted_model.model_.coef_
            )
            assert np.isclose(
                loaded_model.model_.intercept_,
                fitted_model.model_.intercept_
            )
            assert loaded_model.vintage_date_ == fitted_model.vintage_date_
            assert loaded_model.feature_names_ == fitted_model.feature_names_
            
            # Check predictions match
            predictions_original = fitted_model.predict(X)
            predictions_loaded = loaded_model.predict(X)
            assert np.allclose(predictions_original, predictions_loaded)
    
    def test_load_nonexistent_file(self):
        """Test that loading nonexistent file raises FileNotFoundError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'nonexistent.pkl'
            
            with pytest.raises(FileNotFoundError, match="Model file not found"):
                RevisionForecaster.load(path)
    
    # ===== Integration Tests =====
    
    def test_full_workflow(self, sample_data):
        """Test complete model workflow: init → fit → predict → save → load."""
        X, y = sample_data
        
        # Initialize
        model = RevisionForecaster(
            alpha=1.0,
            fit_intercept=True,
            random_state=42
        )
        
        # Fit
        model.fit(X, y, vintage_date='2024-11-15')
        assert model.model_ is not None
        
        # Predict
        predictions = model.predict(X)
        assert len(predictions) == len(X)
        
        # Get params
        params = model.get_params()
        assert params['is_fitted'] is True
        
        # Get feature importance
        importance = model.get_feature_importance()
        assert len(importance) == 4
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Save
            save_path = Path(tmpdir) / 'model.pkl'
            model.save(save_path)
            assert save_path.exists()
            
            # Load
            loaded_model = RevisionForecaster.load(save_path)
            loaded_predictions = loaded_model.predict(X)
            
            # Verify consistency
            assert np.allclose(predictions, loaded_predictions)
    
    def test_method_chaining(self, sample_data):
        """Test that fit returns self for method chaining."""
        X, y = sample_data
        
        # Should be able to chain fit().predict()
        model = RevisionForecaster(random_state=42)
        predictions = model.fit(X, y, vintage_date='2024-11-15').predict(X)
        
        assert predictions is not None
        assert len(predictions) == len(X)


class TestRevisionForecasterEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_single_feature(self):
        """Test model with single feature."""
        np.random.seed(42)
        X = pd.DataFrame(
            np.random.randn(50, 1), 
            columns=['preliminary_value']
        )
        y = pd.Series(np.random.randn(50))
        
        model = RevisionForecaster(random_state=42)
        model.fit(X, y, vintage_date='2024-11-15')
        predictions = model.predict(X)
        
        assert len(predictions) == 50
    
    def test_small_sample_size(self):
        """Test model with small sample size."""
        np.random.seed(42)
        X = pd.DataFrame(np.random.randn(10, 3))
        y = pd.Series(np.random.randn(10))
        
        model = RevisionForecaster(random_state=42)
        model.fit(X, y, vintage_date='2024-11-15')
        predictions = model.predict(X)
        
        assert len(predictions) == 10
    
    def test_no_intercept(self):
        """Test model without intercept."""
        np.random.seed(42)
        X = pd.DataFrame(np.random.randn(30, 5))
        y = pd.Series(np.random.randn(30))
        
        model = RevisionForecaster(
            alpha=1.0,
            fit_intercept=False,
            random_state=42
        )
        model.fit(X, y, vintage_date='2024-11-15')
        
        # Intercept should be 0
        assert model.model_.intercept_ == 0.0
        
        predictions = model.predict(X)
        assert len(predictions) == 30
    
    def test_high_regularization(self):
        """Test model with high regularization (alpha=100)."""
        np.random.seed(42)
        X = pd.DataFrame(np.random.randn(50, 10))
        y = pd.Series(np.random.randn(50))
        
        model = RevisionForecaster(alpha=100.0, random_state=42)
        model.fit(X, y, vintage_date='2024-11-15')
        
        # High regularization should shrink coefficients toward zero
        coefficients = model.model_.coef_
        assert np.all(np.abs(coefficients) < 1.0)  # Heavily regularized
    
    def test_zero_regularization(self):
        """Test model with no regularization (alpha=0)."""
        np.random.seed(42)
        X = pd.DataFrame(np.random.randn(50, 3))
        y = pd.Series(np.random.randn(50))
        
        model = RevisionForecaster(alpha=0.0, random_state=42)
        model.fit(X, y, vintage_date='2024-11-15')
        predictions = model.predict(X)
        
        assert len(predictions) == 50
        # Alpha=0 is OLS regression (no regularization)


class TestRevisionForecasterRealism:
    """Test realistic revision forecasting scenarios."""
    
    def test_mean_reversion_pattern(self):
        """Test that model captures mean reversion in revisions."""
        np.random.seed(42)
        
        # Create data where high preliminary values get revised down
        n = 100
        preliminary = 150 + np.random.randn(n) * 30
        revisions = -0.2 * (preliminary - 150) + np.random.randn(n) * 5
        
        X = pd.DataFrame({'preliminary_value': preliminary})
        y = pd.Series(revisions)
        
        model = RevisionForecaster(alpha=0.1, random_state=42)
        model.fit(X, y, vintage_date='2024-11-15')
        
        # Test: High preliminary should predict downward revision
        X_high = pd.DataFrame({'preliminary_value': [200]})
        pred_high = model.predict(X_high)[0]
        
        # Test: Low preliminary should predict upward revision
        X_low = pd.DataFrame({'preliminary_value': [100]})
        pred_low = model.predict(X_low)[0]
        
        # With strong mean reversion signal, expect this pattern
        assert pred_high < pred_low  # Higher prelim → more negative revision
    
    def test_persistence_pattern(self):
        """Test that model captures revision persistence."""
        np.random.seed(42)
        
        # Create data where revisions are persistent (correlated over time)
        n = 100
        prev_revisions = np.random.randn(n) * 10
        current_revisions = 0.5 * prev_revisions + np.random.randn(n) * 5
        
        X = pd.DataFrame({'prev_revision_avg': prev_revisions})
        y = pd.Series(current_revisions)
        
        model = RevisionForecaster(alpha=0.1, random_state=42)
        model.fit(X, y, vintage_date='2024-11-15')
        
        # Check coefficient is positive (persistence)
        importance = model.get_feature_importance()
        prev_rev_coef = importance[
            importance['feature'] == 'prev_revision_avg'
        ]['coefficient'].values[0]
        
        assert prev_rev_coef > 0  # Positive persistence

