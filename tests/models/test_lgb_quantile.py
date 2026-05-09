"""
Tests for LightGBM Quantile Regression model.

Tests cover:
- Model initialization and parameter validation
- Multi-quantile output validation
- Quantile crossing prevention
- Feature importance tracking
- Reproducibility (deterministic training)
- Feature registry integration
- Save/load functionality
- Prediction intervals
- Cross-model consistency with XGBoost
"""

import pytest
import numpy as np
import pandas as pd
from pathlib import Path
import tempfile

from models_src.gbm_quantile.lgb_quantile import LightGBMQuantile
from models_src.gbm_quantile.xgb_quantile import XGBoostQuantile


class TestLightGBMQuantileInitialization:
    """Test model initialization and parameter validation."""

    def test_init_default_parameters(self):
        """Test initialization with default parameters."""
        model = LightGBMQuantile()

        assert model.quantiles == [0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95]
        assert model.n_estimators == 100
        assert model.max_depth == 5
        assert model.learning_rate == 0.1
        assert model.num_leaves == 31
        assert model.subsample == 0.8
        assert model.colsample_bytree == 0.8
        assert model.prevent_crossing is True
        assert model.random_state == 42
        assert model.models_ is None  # Not fitted yet

    def test_init_custom_parameters(self):
        """Test initialization with custom parameters."""
        custom_quantiles = [0.1, 0.5, 0.9]
        model = LightGBMQuantile(
            quantiles=custom_quantiles,
            n_estimators=50,
            max_depth=3,
            learning_rate=0.05,
            num_leaves=15,
            subsample=0.9,
            colsample_bytree=0.7,
            prevent_crossing=False,
            random_state=123,
        )

        assert model.quantiles == custom_quantiles
        assert model.n_estimators == 50
        assert model.max_depth == 3
        assert model.learning_rate == 0.05
        assert model.num_leaves == 15
        assert model.subsample == 0.9
        assert model.colsample_bytree == 0.7
        assert model.prevent_crossing is False
        assert model.random_state == 123

    def test_init_validates_empty_quantiles(self):
        """Test that empty quantiles list raises ValueError."""
        with pytest.raises(ValueError, match="quantiles list cannot be empty"):
            LightGBMQuantile(quantiles=[])

    def test_init_validates_quantile_range(self):
        """Test that quantiles outside (0, 1) raise ValueError."""
        with pytest.raises(ValueError, match="All quantiles must be in"):
            LightGBMQuantile(quantiles=[0.0, 0.5, 1.0])

    def test_init_validates_unique_quantiles(self):
        """Test that duplicate quantiles raise ValueError."""
        with pytest.raises(ValueError, match="quantiles must be unique"):
            LightGBMQuantile(quantiles=[0.1, 0.5, 0.5, 0.9])

    def test_init_validates_n_estimators(self):
        """Test that non-positive n_estimators raises ValueError."""
        with pytest.raises(ValueError, match="n_estimators must be positive"):
            LightGBMQuantile(n_estimators=0)

    def test_init_validates_max_depth(self):
        """Test that invalid max_depth raises ValueError."""
        with pytest.raises(ValueError, match="max_depth must be >= -1"):
            LightGBMQuantile(max_depth=-2)

    def test_init_validates_num_leaves(self):
        """Test that num_leaves must be > 1."""
        with pytest.raises(ValueError, match="num_leaves must be > 1"):
            LightGBMQuantile(num_leaves=1)


class TestLightGBMQuantileFitting:
    """Test model fitting functionality."""

    @pytest.fixture
    def sample_data(self):
        """Generate sample regression data for testing."""
        np.random.seed(42)
        n_samples = 100
        n_features = 5

        X = pd.DataFrame(
            np.random.randn(n_samples, n_features),
            columns=[f"feature_{i}" for i in range(n_features)],
        )

        # Target with some noise
        y = pd.Series(X.sum(axis=1) + np.random.randn(n_samples) * 5, name="target")

        return X, y

    def test_fit_basic(self, sample_data):
        """Test basic model fitting."""
        X, y = sample_data
        model = LightGBMQuantile(
            quantiles=[0.1, 0.5, 0.9], n_estimators=10, random_state=42  # Fast for testing
        )

        result = model.fit(X, y, vintage_date="2024-11-15")

        # Check method chaining
        assert result is model

        # Check fitted attributes
        assert model.models_ is not None
        assert len(model.models_) == 3  # One per quantile
        assert 0.1 in model.models_
        assert 0.5 in model.models_
        assert 0.9 in model.models_

        assert model.vintage_date_ == "2024-11-15"
        assert model.n_features_ == 5
        assert model.feature_names_ == list(X.columns)
        assert model.feature_importance_ is not None

    def test_fit_empty_data(self):
        """Test that fitting with empty data raises ValueError."""
        model = LightGBMQuantile()
        X = pd.DataFrame()
        y = pd.Series(dtype=float)

        with pytest.raises(ValueError, match="X and y cannot be empty"):
            model.fit(X, y, vintage_date="2024-11-15")

    def test_fit_length_mismatch(self, sample_data):
        """Test that X and y length mismatch raises ValueError."""
        X, y = sample_data
        model = LightGBMQuantile()

        y_short = y.iloc[:50]

        with pytest.raises(ValueError, match="X and y must have same length"):
            model.fit(X, y_short, vintage_date="2024-11-15")


class TestLightGBMQuantilePrediction:
    """Test prediction functionality."""

    @pytest.fixture
    def fitted_model(self):
        """Create and fit a model for testing."""
        np.random.seed(42)
        X = pd.DataFrame(np.random.randn(100, 5), columns=[f"feat_{i}" for i in range(5)])
        y = pd.Series(X.sum(axis=1) + np.random.randn(100) * 5)

        model = LightGBMQuantile(quantiles=[0.1, 0.5, 0.9], n_estimators=10, random_state=42)
        model.fit(X, y, vintage_date="2024-11-15")

        return model, X

    def test_predict_returns_dict(self, fitted_model):
        """Test that predict returns dictionary of quantile predictions."""
        model, X = fitted_model

        predictions = model.predict(X)

        assert isinstance(predictions, dict)
        assert len(predictions) == 3
        assert 0.1 in predictions
        assert 0.5 in predictions
        assert 0.9 in predictions

        # Check array shapes
        for quantile, preds in predictions.items():
            assert len(preds) == len(X)
            assert preds.dtype == np.float64

    def test_predict_before_fit(self):
        """Test that predicting before fit raises ValueError."""
        model = LightGBMQuantile()
        X = pd.DataFrame(np.random.randn(10, 5))

        with pytest.raises(ValueError, match="Model must be fitted before prediction"):
            model.predict(X)

    def test_predict_feature_mismatch(self, fitted_model):
        """Test that feature count mismatch raises ValueError."""
        model, _ = fitted_model

        X_wrong = pd.DataFrame(np.random.randn(10, 3))

        with pytest.raises(ValueError, match="Feature mismatch"):
            model.predict(X_wrong)


class TestQuantileCrossingPrevention:
    """Test quantile crossing prevention functionality."""

    def test_crossing_prevention_enforces_ordering(self):
        """Test that prevent_crossing enforces monotonic quantile ordering."""
        np.random.seed(42)
        X = pd.DataFrame(np.random.randn(50, 5))
        y = pd.Series(X.sum(axis=1) + np.random.randn(50) * 5)

        model = LightGBMQuantile(
            quantiles=[0.1, 0.3, 0.5, 0.7, 0.9],
            n_estimators=20,
            prevent_crossing=True,
            random_state=42,
        )
        model.fit(X, y, vintage_date="2024-11-15")

        predictions = model.predict(X)

        # Check monotonic ordering for each sample
        quantiles = sorted(predictions.keys())
        for i in range(len(X)):
            sample_preds = [predictions[q][i] for q in quantiles]

            # Check strict ordering (allowing small numerical errors)
            for j in range(len(sample_preds) - 1):
                assert (
                    sample_preds[j] <= sample_preds[j + 1] + 1e-6
                ), f"Quantile crossing detected at sample {i}: {sample_preds}"


class TestFeatureImportance:
    """Test feature importance functionality."""

    def test_feature_importance_unfitted(self):
        """Test that feature importance before fit raises ValueError."""
        model = LightGBMQuantile()

        with pytest.raises(ValueError, match="Model must be fitted"):
            model.get_feature_importance()

    def test_feature_importance_structure(self):
        """Test feature importance output structure."""
        np.random.seed(42)
        X = pd.DataFrame(np.random.randn(100, 5), columns=[f"feat_{i}" for i in range(5)])
        y = pd.Series(X["feat_0"] * 2 + X["feat_1"] * 1 + np.random.randn(100) * 0.5)

        model = LightGBMQuantile(quantiles=[0.1, 0.5, 0.9], n_estimators=20, random_state=42)
        model.fit(X, y, vintage_date="2024-11-15")

        importance = model.get_feature_importance()

        assert isinstance(importance, pd.DataFrame)
        assert len(importance) == 5  # 5 features
        assert "feature" in importance.columns
        assert "importance" in importance.columns

        # Should be sorted by importance (descending)
        assert importance["importance"].is_monotonic_decreasing


class TestReproducibility:
    """Test reproducibility with fixed random seed."""

    def test_same_seed_produces_identical_predictions(self):
        """Test that same seed produces identical results."""
        np.random.seed(42)
        X = pd.DataFrame(np.random.randn(50, 5))
        y = pd.Series(X.sum(axis=1) + np.random.randn(50) * 5)

        # Train two models with same seed
        model1 = LightGBMQuantile(quantiles=[0.1, 0.5, 0.9], n_estimators=10, random_state=42)
        model1.fit(X, y, vintage_date="2024-11-15")
        predictions1 = model1.predict(X)

        model2 = LightGBMQuantile(quantiles=[0.1, 0.5, 0.9], n_estimators=10, random_state=42)
        model2.fit(X, y, vintage_date="2024-11-15")
        predictions2 = model2.predict(X)

        # Results should be identical
        for quantile in [0.1, 0.5, 0.9]:
            assert np.allclose(predictions1[quantile], predictions2[quantile])


class TestSaveLoad:
    """Test save/load functionality."""

    def test_save_unfitted_model(self):
        """Test that saving unfitted model raises ValueError."""
        model = LightGBMQuantile()

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "model.pkl"

            with pytest.raises(ValueError, match="Cannot save unfitted model"):
                model.save(path)

    def test_save_load_roundtrip(self):
        """Test that save/load preserves model state."""
        np.random.seed(42)
        X = pd.DataFrame(np.random.randn(50, 5))
        y = pd.Series(X.sum(axis=1))

        model = LightGBMQuantile(quantiles=[0.1, 0.5, 0.9], n_estimators=10, random_state=42)
        model.fit(X, y, vintage_date="2024-11-15")
        predictions_original = model.predict(X)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "lgb_model.pkl"

            # Save model
            model.save(path)
            assert path.exists()

            # Load model
            loaded_model = LightGBMQuantile.load(path)

            # Check parameters match
            assert loaded_model.quantiles == model.quantiles
            assert loaded_model.n_estimators == model.n_estimators
            assert loaded_model.random_state == model.random_state

            # Check fitted state matches
            assert loaded_model.vintage_date_ == model.vintage_date_
            assert loaded_model.n_features_ == model.n_features_
            assert loaded_model.feature_names_ == model.feature_names_

            # Check predictions match
            predictions_loaded = loaded_model.predict(X)
            for quantile in [0.1, 0.5, 0.9]:
                assert np.allclose(predictions_original[quantile], predictions_loaded[quantile])


class TestPredictionIntervals:
    """Test prediction interval extraction."""

    def test_get_prediction_intervals_90_percent(self):
        """Test extraction of 90% prediction intervals."""
        np.random.seed(42)
        X = pd.DataFrame(np.random.randn(50, 5))
        y = pd.Series(X.sum(axis=1) + np.random.randn(50) * 5)

        model = LightGBMQuantile(quantiles=[0.05, 0.5, 0.95], n_estimators=20, random_state=42)
        model.fit(X, y, vintage_date="2024-11-15")
        predictions = model.predict(X)

        lower, upper = model.get_prediction_intervals(predictions, confidence_level=0.9)

        assert len(lower) == len(X)
        assert len(upper) == len(X)
        assert np.all(lower <= upper)  # Lower bound <= upper bound


class TestCrossModelConsistency:
    """Test consistency between LightGBM and XGBoost implementations."""

    @pytest.fixture
    def sample_data(self):
        """Generate sample data for cross-model testing."""
        np.random.seed(42)
        X = pd.DataFrame(np.random.randn(100, 5), columns=[f"feat_{i}" for i in range(5)])
        y = pd.Series(X.sum(axis=1) + np.random.randn(100) * 3)
        return X, y

    def test_both_models_have_same_interface(self, sample_data):
        """Test that both models implement the same interface."""
        X, y = sample_data

        lgb_model = LightGBMQuantile(quantiles=[0.1, 0.5, 0.9], n_estimators=10, random_state=42)
        xgb_model = XGBoostQuantile(quantiles=[0.1, 0.5, 0.9], n_estimators=10, random_state=42)

        # Both should implement same methods
        for method in ["fit", "predict", "get_params", "save", "load", "get_feature_importance"]:
            assert hasattr(lgb_model, method)
            assert hasattr(xgb_model, method)

        # Both should fit without errors
        lgb_model.fit(X, y, vintage_date="2024-11-15")
        xgb_model.fit(X, y, vintage_date="2024-11-15")

        # Both should predict
        lgb_preds = lgb_model.predict(X)
        xgb_preds = xgb_model.predict(X)

        assert set(lgb_preds.keys()) == set(xgb_preds.keys())

    def test_predictions_are_qualitatively_similar(self, sample_data):
        """Test that predictions from both models are qualitatively similar."""
        X, y = sample_data

        lgb_model = LightGBMQuantile(
            quantiles=[0.1, 0.5, 0.9], n_estimators=50, max_depth=5, random_state=42
        )
        xgb_model = XGBoostQuantile(
            quantiles=[0.1, 0.5, 0.9], n_estimators=50, max_depth=5, random_state=42
        )

        lgb_model.fit(X, y, vintage_date="2024-11-15")
        xgb_model.fit(X, y, vintage_date="2024-11-15")

        lgb_preds = lgb_model.predict(X)
        xgb_preds = xgb_model.predict(X)

        # Check that predictions are correlated (both models learn the pattern)
        for quantile in [0.1, 0.5, 0.9]:
            correlation = np.corrcoef(lgb_preds[quantile], xgb_preds[quantile])[0, 1]
            assert (
                correlation > 0.8
            ), f"Predictions for quantile {quantile} should be highly correlated"

    def test_feature_importance_structure_matches(self, sample_data):
        """Test that feature importance structures match."""
        X, y = sample_data

        lgb_model = LightGBMQuantile(quantiles=[0.5], n_estimators=20, random_state=42)
        xgb_model = XGBoostQuantile(quantiles=[0.5], n_estimators=20, random_state=42)

        lgb_model.fit(X, y, vintage_date="2024-11-15")
        xgb_model.fit(X, y, vintage_date="2024-11-15")

        lgb_importance = lgb_model.get_feature_importance()
        xgb_importance = xgb_model.get_feature_importance()

        # Both should have same structure
        assert list(lgb_importance.columns) == list(xgb_importance.columns)
        assert len(lgb_importance) == len(xgb_importance)


class TestIntegration:
    """Integration tests for complete workflows."""

    def test_full_workflow(self):
        """Test complete workflow: init → fit → predict → save → load."""
        np.random.seed(42)
        X = pd.DataFrame(np.random.randn(50, 5), columns=[f"f_{i}" for i in range(5)])
        y = pd.Series(X.sum(axis=1) + np.random.randn(50) * 5)

        # Initialize
        model = LightGBMQuantile(quantiles=[0.1, 0.5, 0.9], n_estimators=10, random_state=42)

        # Fit
        model.fit(X, y, vintage_date="2024-11-15")
        assert model.models_ is not None

        # Predict
        predictions = model.predict(X)
        assert len(predictions) == 3

        # Get params
        params = model.get_params()
        assert params["is_fitted"] is True

        # Get feature importance
        importance = model.get_feature_importance()
        assert len(importance) == 5

        # Get prediction intervals
        lower, upper = model.get_prediction_intervals(predictions, confidence_level=0.8)
        assert len(lower) == len(X)

        with tempfile.TemporaryDirectory() as tmpdir:
            # Save
            save_path = Path(tmpdir) / "model.pkl"
            model.save(save_path)
            assert save_path.exists()

            # Load
            loaded_model = LightGBMQuantile.load(save_path)
            loaded_predictions = loaded_model.predict(X)

            # Verify consistency
            for quantile in [0.1, 0.5, 0.9]:
                assert np.allclose(predictions[quantile], loaded_predictions[quantile])
