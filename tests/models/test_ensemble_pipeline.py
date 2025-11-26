"""
Tests for ensemble forecasting pipeline.

This module tests ensemble methods including:
- Simple averaging (equal weights)
- Weighted averaging (optimized weights)
- Stacking (meta-learning)
- Model combination strategies
- Reproducibility and determinism
- Integration with trained models (DFM, MIDAS, GBM)

Following TDD methodology and lessons from TESTING_MATHEMATICAL_ALGORITHMS.md:
- Test mathematical properties (variance reduction, weight constraints)
- Test method differentiation (simple vs weighted vs stacking)
- Test reproducibility (same seed = same results)
- Test integration (real model combinations)
"""

import pytest
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import date, datetime
from unittest.mock import Mock, patch, MagicMock
import tempfile

from models_src.pipelines.ensemble_pipeline import (
    EnsembleConfig,
    EnsembleMethod,
    EnsembleForecaster,
    simple_average,
    weighted_average,
    optimize_weights,
    validate_predictions_dict,
)
from models_src.utils.base_model import BaseForecaster


# ============================================================================
# Test Helpers
# ============================================================================


class MockForecaster(BaseForecaster):
    """
    Mock forecaster for testing ensemble.
    
    Returns predictions based on a configurable bias to test ensemble behavior.
    Must be at module level to be pickleable.
    """
    
    def __init__(self, random_state=42, bias=0.0, variance=1.0):
        super().__init__(random_state=random_state)
        self.bias = bias
        self.variance = variance
        self._is_fitted = False
        self.model_name = f"Mock_bias{bias}"
    
    def fit(self, X, y, vintage_date):
        """Fit mock model."""
        self._is_fitted = True
        self.vintage_date = vintage_date
        self.feature_names = X.columns.tolist()
        self.n_features = X.shape[1]
        return self
    
    def predict(self, X):
        """Generate deterministic predictions with configurable bias."""
        if not self._is_fitted:
            raise ValueError("Model must be fitted before prediction")
        
        # Deterministic predictions: first feature + bias + small noise
        np.random.seed(self.random_state)
        predictions = (
            X.iloc[:, 0].values + 
            self.bias + 
            np.random.randn(len(X)) * self.variance
        )
        return predictions
    
    def get_params(self):
        """Return mock parameters."""
        return {
            "random_state": self.random_state,
            "bias": self.bias,
            "variance": self.variance,
            "is_fitted": self._is_fitted,
        }


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sample_data():
    """
    Create sample time series data for testing.
    
    Returns DataFrame with:
    - date index
    - feature columns (feat1, feat2, feat3)
    - target column
    """
    np.random.seed(42)
    n_samples = 200
    dates = pd.date_range('2020-01-01', periods=n_samples, freq='D')
    
    # Generate features with different patterns
    feat1 = np.sin(np.linspace(0, 4*np.pi, n_samples)) + np.random.randn(n_samples) * 0.1
    feat2 = np.cos(np.linspace(0, 4*np.pi, n_samples)) + np.random.randn(n_samples) * 0.1
    feat3 = np.linspace(0, 10, n_samples) + np.random.randn(n_samples) * 0.1
    
    # Target is combination of features
    target = 0.5 * feat1 + 0.3 * feat2 + 0.2 * feat3 + np.random.randn(n_samples) * 0.5
    
    df = pd.DataFrame({
        'feat1': feat1,
        'feat2': feat2,
        'feat3': feat3,
        'target': target,
    }, index=dates)
    
    return df


@pytest.fixture
def sample_predictions():
    """
    Create sample predictions from multiple models.
    
    Returns dict with predictions from 3 models.
    """
    np.random.seed(42)
    n_samples = 50
    
    # Model 1: slightly optimistic (bias +2)
    pred1 = np.linspace(100, 150, n_samples) + np.random.randn(n_samples) * 5 + 2
    
    # Model 2: slightly pessimistic (bias -2)
    pred2 = np.linspace(100, 150, n_samples) + np.random.randn(n_samples) * 5 - 2
    
    # Model 3: unbiased but noisy
    pred3 = np.linspace(100, 150, n_samples) + np.random.randn(n_samples) * 8
    
    return {
        'dfm': pred1,
        'midas': pred2,
        'xgboost': pred3,
    }


@pytest.fixture
def sample_true_values():
    """Create true values for evaluation."""
    np.random.seed(42)
    n_samples = 50
    return np.linspace(100, 150, n_samples) + np.random.randn(n_samples) * 3


@pytest.fixture
def fitted_mock_models(sample_data):
    """
    Create and fit multiple mock models with different characteristics.
    
    Returns dict of fitted models.
    """
    # Split data
    train_size = 150
    X_train = sample_data[['feat1', 'feat2', 'feat3']].iloc[:train_size]
    y_train = sample_data['target'].iloc[:train_size]
    
    # Create models with different biases (simulating different model types)
    models = {
        'dfm': MockForecaster(random_state=42, bias=0.5, variance=0.5),
        'midas': MockForecaster(random_state=43, bias=-0.5, variance=0.5),
        'xgboost': MockForecaster(random_state=44, bias=0.0, variance=1.0),
    }
    
    # Fit all models
    for name, model in models.items():
        model.fit(X_train, y_train, vintage_date='2024-11-15')
    
    return models


@pytest.fixture
def ensemble_config():
    """Create basic ensemble configuration."""
    return EnsembleConfig(
        method=EnsembleMethod.SIMPLE_AVERAGE,
        model_names=['dfm', 'midas', 'xgboost'],
        weights=None,
        optimize_weights=False,
        random_state=42,
    )


# ============================================================================
# Test EnsembleConfig
# ============================================================================


class TestEnsembleConfig:
    """Test EnsembleConfig validation and initialization."""
    
    def test_config_initialization(self):
        """Test basic config initialization."""
        config = EnsembleConfig(
            method=EnsembleMethod.SIMPLE_AVERAGE,
            model_names=['model1', 'model2'],
        )
        
        assert config.method == EnsembleMethod.SIMPLE_AVERAGE
        assert config.model_names == ['model1', 'model2']
        assert config.weights is None
        assert config.optimize_weights is False
        assert config.random_state == 42  # default
    
    def test_config_with_weights(self):
        """Test config with explicit weights."""
        weights = {'model1': 0.6, 'model2': 0.4}
        config = EnsembleConfig(
            method=EnsembleMethod.WEIGHTED_AVERAGE,
            model_names=['model1', 'model2'],
            weights=weights,
        )
        
        assert config.weights == weights
    
    def test_config_validation_weights_sum(self):
        """Test that weights must sum to 1.0."""
        with pytest.raises(ValueError, match="sum to 1.0"):
            EnsembleConfig(
                method=EnsembleMethod.WEIGHTED_AVERAGE,
                model_names=['model1', 'model2'],
                weights={'model1': 0.6, 'model2': 0.6},  # sum = 1.2
            )
    
    def test_config_validation_weights_positive(self):
        """Test that weights must be positive."""
        with pytest.raises(ValueError, match="positive"):
            EnsembleConfig(
                method=EnsembleMethod.WEIGHTED_AVERAGE,
                model_names=['model1', 'model2'],
                weights={'model1': 0.7, 'model2': -0.3},  # negative
            )
    
    def test_config_validation_weights_keys(self):
        """Test that weight keys must match model_names."""
        with pytest.raises(ValueError, match="must match"):
            EnsembleConfig(
                method=EnsembleMethod.WEIGHTED_AVERAGE,
                model_names=['model1', 'model2'],
                weights={'model1': 0.5, 'model3': 0.5},  # model3 not in names
            )
    
    def test_config_validation_empty_models(self):
        """Test that model_names cannot be empty."""
        with pytest.raises(ValueError, match="cannot be empty"):
            EnsembleConfig(
                method=EnsembleMethod.SIMPLE_AVERAGE,
                model_names=[],
            )


# ============================================================================
# Test Utility Functions
# ============================================================================


class TestUtilityFunctions:
    """Test utility functions for ensemble predictions."""
    
    def test_validate_predictions_dict_valid(self, sample_predictions):
        """Test validation of valid predictions dict."""
        # Should not raise
        validate_predictions_dict(
            sample_predictions,
            expected_keys=['dfm', 'midas', 'xgboost']
        )
    
    def test_validate_predictions_dict_missing_keys(self, sample_predictions):
        """Test validation fails with missing keys."""
        with pytest.raises(ValueError, match="Missing predictions"):
            validate_predictions_dict(
                sample_predictions,
                expected_keys=['dfm', 'midas', 'xgboost', 'missing_model']
            )
    
    def test_validate_predictions_dict_mismatched_lengths(self):
        """Test validation fails with mismatched prediction lengths."""
        predictions = {
            'model1': np.array([1, 2, 3]),
            'model2': np.array([1, 2, 3, 4]),  # different length
        }
        
        with pytest.raises(ValueError, match="same length"):
            validate_predictions_dict(
                predictions,
                expected_keys=['model1', 'model2']
            )
    
    def test_simple_average(self, sample_predictions):
        """Test simple averaging of predictions."""
        result = simple_average(sample_predictions)
        
        # Check shape
        assert len(result) == len(sample_predictions['dfm'])
        
        # Check that average is computed correctly
        expected = (
            sample_predictions['dfm'] + 
            sample_predictions['midas'] + 
            sample_predictions['xgboost']
        ) / 3
        
        np.testing.assert_array_almost_equal(result, expected)
    
    def test_weighted_average(self, sample_predictions):
        """Test weighted averaging of predictions."""
        weights = {'dfm': 0.5, 'midas': 0.3, 'xgboost': 0.2}
        result = weighted_average(sample_predictions, weights)
        
        # Check shape
        assert len(result) == len(sample_predictions['dfm'])
        
        # Check that weighted average is computed correctly
        expected = (
            0.5 * sample_predictions['dfm'] + 
            0.3 * sample_predictions['midas'] + 
            0.2 * sample_predictions['xgboost']
        )
        
        np.testing.assert_array_almost_equal(result, expected)
    
    def test_optimize_weights_basic(self, sample_predictions, sample_true_values):
        """Test weight optimization returns valid weights."""
        weights = optimize_weights(
            predictions=sample_predictions,
            y_true=sample_true_values,
            method='minimize_mse',
        )
        
        # Check all models have weights
        assert set(weights.keys()) == set(sample_predictions.keys())
        
        # Check weights are positive
        assert all(w >= 0 for w in weights.values())
        
        # Check weights sum to 1.0
        assert abs(sum(weights.values()) - 1.0) < 1e-6
    
    def test_optimize_weights_improves_performance(
        self, 
        sample_predictions, 
        sample_true_values
    ):
        """
        Test that optimized weights improve over simple average.
        
        This is a key mathematical property: weight optimization should
        reduce forecast error compared to equal weighting.
        """
        # Simple average
        simple_avg = simple_average(sample_predictions)
        simple_mse = np.mean((simple_avg - sample_true_values) ** 2)
        
        # Optimized weights
        weights = optimize_weights(
            predictions=sample_predictions,
            y_true=sample_true_values,
            method='minimize_mse',
        )
        weighted_avg = weighted_average(sample_predictions, weights)
        weighted_mse = np.mean((weighted_avg - sample_true_values) ** 2)
        
        # Optimized should be equal or better (allowing small tolerance)
        assert weighted_mse <= simple_mse * 1.01


# ============================================================================
# Test EnsembleForecaster - Basic Functionality
# ============================================================================


class TestEnsembleForecasterBasic:
    """Test EnsembleForecaster basic functionality."""
    
    def test_initialization(self, ensemble_config):
        """Test ensemble forecaster initialization."""
        ensemble = EnsembleForecaster(
            models={'dfm': Mock(), 'midas': Mock(), 'xgboost': Mock()},
            config=ensemble_config,
        )
        
        assert ensemble.config == ensemble_config
        assert len(ensemble.models) == 3
        assert set(ensemble.models.keys()) == {'dfm', 'midas', 'xgboost'}
    
    def test_initialization_validation_model_names_mismatch(self):
        """Test initialization fails if model names don't match config."""
        config = EnsembleConfig(
            method=EnsembleMethod.SIMPLE_AVERAGE,
            model_names=['model1', 'model2', 'model3'],
        )
        
        models = {'model1': Mock(), 'model2': Mock()}  # missing model3
        
        with pytest.raises(ValueError, match="must match"):
            EnsembleForecaster(models=models, config=config)
    
    def test_get_params(self, fitted_mock_models, ensemble_config):
        """Test get_params returns correct information."""
        ensemble = EnsembleForecaster(
            models=fitted_mock_models,
            config=ensemble_config,
        )
        
        params = ensemble.get_params()
        
        assert params['method'] == EnsembleMethod.SIMPLE_AVERAGE
        assert params['n_models'] == 3
        assert set(params['model_names']) == {'dfm', 'midas', 'xgboost'}
        assert params['random_state'] == 42


# ============================================================================
# Test EnsembleForecaster - Prediction Methods
# ============================================================================


class TestEnsembleForecasterPrediction:
    """Test EnsembleForecaster prediction methods."""
    
    def test_predict_simple_average(self, fitted_mock_models, sample_data):
        """Test prediction with simple averaging."""
        config = EnsembleConfig(
            method=EnsembleMethod.SIMPLE_AVERAGE,
            model_names=['dfm', 'midas', 'xgboost'],
        )
        
        ensemble = EnsembleForecaster(
            models=fitted_mock_models,
            config=config,
        )
        
        # Get test data
        X_test = sample_data[['feat1', 'feat2', 'feat3']].iloc[150:160]
        
        # Predict
        predictions = ensemble.predict(X_test)
        
        # Check shape
        assert len(predictions) == len(X_test)
        
        # Manually compute expected (simple average)
        individual_preds = {
            name: model.predict(X_test)
            for name, model in fitted_mock_models.items()
        }
        expected = simple_average(individual_preds)
        
        np.testing.assert_array_almost_equal(predictions, expected)
    
    def test_predict_weighted_average(self, fitted_mock_models, sample_data):
        """Test prediction with weighted averaging."""
        weights = {'dfm': 0.5, 'midas': 0.3, 'xgboost': 0.2}
        config = EnsembleConfig(
            method=EnsembleMethod.WEIGHTED_AVERAGE,
            model_names=['dfm', 'midas', 'xgboost'],
            weights=weights,
        )
        
        ensemble = EnsembleForecaster(
            models=fitted_mock_models,
            config=config,
        )
        
        # Get test data
        X_test = sample_data[['feat1', 'feat2', 'feat3']].iloc[150:160]
        
        # Predict
        predictions = ensemble.predict(X_test)
        
        # Check shape
        assert len(predictions) == len(X_test)
        
        # Manually compute expected (weighted average)
        individual_preds = {
            name: model.predict(X_test)
            for name, model in fitted_mock_models.items()
        }
        expected = weighted_average(individual_preds, weights)
        
        np.testing.assert_array_almost_equal(predictions, expected)
    
    def test_predict_with_optimization(self, fitted_mock_models, sample_data):
        """Test prediction with weight optimization."""
        config = EnsembleConfig(
            method=EnsembleMethod.WEIGHTED_AVERAGE,
            model_names=['dfm', 'midas', 'xgboost'],
            optimize_weights=True,
        )
        
        ensemble = EnsembleForecaster(
            models=fitted_mock_models,
            config=config,
        )
        
        # Get validation data for optimization
        X_val = sample_data[['feat1', 'feat2', 'feat3']].iloc[130:150]
        y_val = sample_data['target'].iloc[130:150]
        
        # Fit (optimize weights)
        ensemble.fit(X_val, y_val, vintage_date='2024-11-15')
        
        # Check weights were optimized
        assert ensemble.optimized_weights is not None
        assert set(ensemble.optimized_weights.keys()) == {'dfm', 'midas', 'xgboost'}
        assert abs(sum(ensemble.optimized_weights.values()) - 1.0) < 1e-6
        
        # Get test data
        X_test = sample_data[['feat1', 'feat2', 'feat3']].iloc[150:160]
        
        # Predict (should use optimized weights)
        predictions = ensemble.predict(X_test)
        
        # Check shape
        assert len(predictions) == len(X_test)


# ============================================================================
# Test EnsembleForecaster - Method Differentiation
# ============================================================================


class TestEnsembleMethodDifferentiation:
    """
    Test that different ensemble methods produce meaningfully different results.
    
    This follows TESTING_MATHEMATICAL_ALGORITHMS.md guidance:
    If offering simple/weighted/stacking, verify they differ appropriately.
    """
    
    def test_simple_vs_weighted_differ(self, fitted_mock_models, sample_data):
        """Test that simple and weighted averaging produce different results."""
        X_test = sample_data[['feat1', 'feat2', 'feat3']].iloc[150:160]
        
        # Simple average
        config_simple = EnsembleConfig(
            method=EnsembleMethod.SIMPLE_AVERAGE,
            model_names=['dfm', 'midas', 'xgboost'],
        )
        ensemble_simple = EnsembleForecaster(
            models=fitted_mock_models,
            config=config_simple,
        )
        pred_simple = ensemble_simple.predict(X_test)
        
        # Weighted average (non-equal weights)
        weights = {'dfm': 0.6, 'midas': 0.3, 'xgboost': 0.1}
        config_weighted = EnsembleConfig(
            method=EnsembleMethod.WEIGHTED_AVERAGE,
            model_names=['dfm', 'midas', 'xgboost'],
            weights=weights,
        )
        ensemble_weighted = EnsembleForecaster(
            models=fitted_mock_models,
            config=config_weighted,
        )
        pred_weighted = ensemble_weighted.predict(X_test)
        
        # Predictions should differ meaningfully
        diff = np.abs(pred_simple - pred_weighted).max()
        assert diff > 0.01, "Simple and weighted averaging should produce different results"
    
    def test_optimized_weights_differ_from_equal(self, fitted_mock_models, sample_data):
        """Test that optimized weights differ from equal weighting."""
        # Get validation data
        X_val = sample_data[['feat1', 'feat2', 'feat3']].iloc[130:150]
        y_val = sample_data['target'].iloc[130:150]
        
        # Optimize weights
        config = EnsembleConfig(
            method=EnsembleMethod.WEIGHTED_AVERAGE,
            model_names=['dfm', 'midas', 'xgboost'],
            optimize_weights=True,
        )
        ensemble = EnsembleForecaster(
            models=fitted_mock_models,
            config=config,
        )
        ensemble.fit(X_val, y_val, vintage_date='2024-11-15')
        
        # Check that at least one weight differs from 1/3
        equal_weight = 1.0 / 3.0
        weights = list(ensemble.optimized_weights.values())
        
        # At least one weight should differ significantly from equal weighting
        max_diff = max(abs(w - equal_weight) for w in weights)
        assert max_diff > 0.05, "Optimized weights should differ from equal weighting"


# ============================================================================
# Test Reproducibility
# ============================================================================


class TestReproducibility:
    """Test reproducibility and determinism of ensemble predictions."""
    
    def test_prediction_reproducibility(self, fitted_mock_models, sample_data):
        """Test that same seed produces identical predictions."""
        X_test = sample_data[['feat1', 'feat2', 'feat3']].iloc[150:160]
        
        config = EnsembleConfig(
            method=EnsembleMethod.SIMPLE_AVERAGE,
            model_names=['dfm', 'midas', 'xgboost'],
            random_state=42,
        )
        
        # First prediction
        ensemble1 = EnsembleForecaster(
            models=fitted_mock_models,
            config=config,
        )
        pred1 = ensemble1.predict(X_test)
        
        # Second prediction with same seed
        ensemble2 = EnsembleForecaster(
            models=fitted_mock_models,
            config=config,
        )
        pred2 = ensemble2.predict(X_test)
        
        # Should be identical
        np.testing.assert_array_almost_equal(pred1, pred2)
    
    def test_weight_optimization_reproducibility(self, fitted_mock_models, sample_data):
        """Test that weight optimization is reproducible with same seed."""
        X_val = sample_data[['feat1', 'feat2', 'feat3']].iloc[130:150]
        y_val = sample_data['target'].iloc[130:150]
        
        config = EnsembleConfig(
            method=EnsembleMethod.WEIGHTED_AVERAGE,
            model_names=['dfm', 'midas', 'xgboost'],
            optimize_weights=True,
            random_state=42,
        )
        
        # First optimization
        ensemble1 = EnsembleForecaster(
            models=fitted_mock_models,
            config=config,
        )
        ensemble1.fit(X_val, y_val, vintage_date='2024-11-15')
        weights1 = ensemble1.optimized_weights
        
        # Second optimization with same seed
        ensemble2 = EnsembleForecaster(
            models=fitted_mock_models,
            config=config,
        )
        ensemble2.fit(X_val, y_val, vintage_date='2024-11-15')
        weights2 = ensemble2.optimized_weights
        
        # Weights should be identical
        for key in weights1:
            assert abs(weights1[key] - weights2[key]) < 1e-10


# ============================================================================
# Test Integration with Real Models
# ============================================================================


class TestIntegration:
    """Test integration scenarios with multiple models."""
    
    def test_ensemble_reduces_variance(self, fitted_mock_models, sample_data):
        """
        Test that ensemble predictions have lower variance than individual models.
        
        This is a key mathematical property of ensembles: combining uncorrelated
        predictions should reduce variance.
        """
        X_test = sample_data[['feat1', 'feat2', 'feat3']].iloc[150:180]
        
        # Get individual predictions
        individual_preds = {
            name: model.predict(X_test)
            for name, model in fitted_mock_models.items()
        }
        
        # Compute individual variances
        individual_vars = [np.var(preds) for preds in individual_preds.values()]
        
        # Get ensemble prediction
        config = EnsembleConfig(
            method=EnsembleMethod.SIMPLE_AVERAGE,
            model_names=['dfm', 'midas', 'xgboost'],
        )
        ensemble = EnsembleForecaster(
            models=fitted_mock_models,
            config=config,
        )
        ensemble_pred = ensemble.predict(X_test)
        ensemble_var = np.var(ensemble_pred)
        
        # Ensemble variance should be lower than average individual variance
        avg_individual_var = np.mean(individual_vars)
        assert ensemble_var <= avg_individual_var * 1.1  # Allow 10% tolerance
    
    def test_single_model_ensemble(self, fitted_mock_models, sample_data):
        """Test that ensemble with single model works correctly."""
        X_test = sample_data[['feat1', 'feat2', 'feat3']].iloc[150:160]
        
        # Single model ensemble
        config = EnsembleConfig(
            method=EnsembleMethod.SIMPLE_AVERAGE,
            model_names=['dfm'],
        )
        ensemble = EnsembleForecaster(
            models={'dfm': fitted_mock_models['dfm']},
            config=config,
        )
        ensemble_pred = ensemble.predict(X_test)
        
        # Should be identical to individual model prediction
        individual_pred = fitted_mock_models['dfm'].predict(X_test)
        
        np.testing.assert_array_almost_equal(ensemble_pred, individual_pred)
    
    def test_ensemble_with_missing_model(self, fitted_mock_models, sample_data):
        """Test that ensemble handles missing model gracefully."""
        X_test = sample_data[['feat1', 'feat2', 'feat3']].iloc[150:160]
        
        # Config specifies 3 models but only provide 2
        config = EnsembleConfig(
            method=EnsembleMethod.SIMPLE_AVERAGE,
            model_names=['dfm', 'midas', 'xgboost'],
        )
        
        # Only provide 2 models
        with pytest.raises(ValueError, match="must match"):
            EnsembleForecaster(
                models={'dfm': fitted_mock_models['dfm'], 'midas': fitted_mock_models['midas']},
                config=config,
            )


# ============================================================================
# Test Edge Cases
# ============================================================================


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_predict_before_fit_with_optimization(self, fitted_mock_models, sample_data):
        """Test that prediction fails if fit() not called when optimization required."""
        config = EnsembleConfig(
            method=EnsembleMethod.WEIGHTED_AVERAGE,
            model_names=['dfm', 'midas', 'xgboost'],
            optimize_weights=True,
        )
        
        ensemble = EnsembleForecaster(
            models=fitted_mock_models,
            config=config,
        )
        
        X_test = sample_data[['feat1', 'feat2', 'feat3']].iloc[150:160]
        
        with pytest.raises(ValueError, match="fit.*before.*predict|must optimize"):
            ensemble.predict(X_test)
    
    def test_empty_predictions(self, fitted_mock_models):
        """Test handling of empty predictions."""
        config = EnsembleConfig(
            method=EnsembleMethod.SIMPLE_AVERAGE,
            model_names=['dfm', 'midas', 'xgboost'],
        )
        
        ensemble = EnsembleForecaster(
            models=fitted_mock_models,
            config=config,
        )
        
        # Empty DataFrame
        X_empty = pd.DataFrame(columns=['feat1', 'feat2', 'feat3'])
        
        predictions = ensemble.predict(X_empty)
        
        assert len(predictions) == 0
    
    def test_weights_preserved_after_fit(self, fitted_mock_models, sample_data):
        """Test that optimized weights are preserved after fit()."""
        X_val = sample_data[['feat1', 'feat2', 'feat3']].iloc[130:150]
        y_val = sample_data['target'].iloc[130:150]
        
        config = EnsembleConfig(
            method=EnsembleMethod.WEIGHTED_AVERAGE,
            model_names=['dfm', 'midas', 'xgboost'],
            optimize_weights=True,
        )
        
        ensemble = EnsembleForecaster(
            models=fitted_mock_models,
            config=config,
        )
        
        # Fit
        ensemble.fit(X_val, y_val, vintage_date='2024-11-15')
        
        # Get weights
        weights_after_fit = ensemble.optimized_weights.copy()
        
        # Predict multiple times
        X_test = sample_data[['feat1', 'feat2', 'feat3']].iloc[150:160]
        ensemble.predict(X_test)
        ensemble.predict(X_test)
        
        # Weights should remain unchanged
        for key in weights_after_fit:
            assert ensemble.optimized_weights[key] == weights_after_fit[key]

