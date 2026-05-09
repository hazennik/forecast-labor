"""
Tests for BaseForecaster abstract class

Validates:
- Abstract method enforcement
- Seed reproducibility
- Vintage-aware interface
- Model lifecycle (fit/predict/save/load)
"""

import pytest
import numpy as np
import pandas as pd

from models_src.utils.base_model import BaseForecaster


class ConcreteForecaster(BaseForecaster):
    """Concrete implementation for testing BaseForecaster"""

    def __init__(self, random_state: int = 42):
        """Initialize with random state"""
        super().__init__(random_state=random_state)
        self.model_params = {}
        self.is_fitted = False

    def fit(self, X: pd.DataFrame, y: pd.Series, vintage_date: str) -> "ConcreteForecaster":
        """Fit the model"""
        self.vintage_date = vintage_date
        self.feature_names = list(X.columns)
        self.n_features = X.shape[1]
        self.is_fitted = True

        # Simulate deterministic training with random_state
        np.random.seed(self.random_state)
        self.model_params["weights"] = np.random.randn(self.n_features)

        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Generate predictions"""
        if not self.is_fitted:
            raise ValueError("Model must be fitted before prediction")

        # Simple deterministic prediction
        np.random.seed(self.random_state)
        predictions = X.values @ self.model_params["weights"]

        return predictions

    def get_params(self) -> dict:
        """Get model parameters"""
        return {
            "random_state": self.random_state,
            "is_fitted": self.is_fitted,
            "feature_names": getattr(self, "feature_names", None),
            "n_features": getattr(self, "n_features", None),
            "vintage_date": getattr(self, "vintage_date", None),
        }


class TestBaseForecasterAbstraction:
    """Test abstract base class enforcement"""

    def test_cannot_instantiate_base_class(self):
        """Test that BaseForecaster cannot be instantiated directly"""
        with pytest.raises(TypeError) as exc_info:
            BaseForecaster(random_state=42)

        assert "Can't instantiate abstract class" in str(exc_info.value)

    def test_must_implement_fit(self):
        """Test that subclass must implement fit()"""

        class IncompleteForecast(BaseForecaster):
            def predict(self, X):
                return np.zeros(len(X))

            def get_params(self):
                return {}

        with pytest.raises(TypeError) as exc_info:
            IncompleteForecast(random_state=42)

        assert "fit" in str(exc_info.value).lower()

    def test_must_implement_predict(self):
        """Test that subclass must implement predict()"""

        class IncompleteForecast(BaseForecaster):
            def fit(self, X, y, vintage_date):
                return self

            def get_params(self):
                return {}

        with pytest.raises(TypeError) as exc_info:
            IncompleteForecast(random_state=42)

        assert "predict" in str(exc_info.value).lower()

    def test_must_implement_get_params(self):
        """Test that subclass must implement get_params()"""

        class IncompleteForecast(BaseForecaster):
            def fit(self, X, y, vintage_date):
                return self

            def predict(self, X):
                return np.zeros(len(X))

        with pytest.raises(TypeError) as exc_info:
            IncompleteForecast(random_state=42)

        assert "get_params" in str(exc_info.value).lower()

    def test_concrete_implementation_works(self):
        """Test that complete implementation can be instantiated"""
        model = ConcreteForecaster(random_state=42)
        assert isinstance(model, BaseForecaster)
        assert model.random_state == 42


class TestBaseForecasterInterface:
    """Test BaseForecaster interface and lifecycle"""

    @pytest.fixture
    def sample_data(self):
        """Create sample training data"""
        np.random.seed(42)
        X = pd.DataFrame(
            {
                "feature_1": np.random.randn(100),
                "feature_2": np.random.randn(100),
                "feature_3": np.random.randn(100),
            }
        )
        y = pd.Series(np.random.randn(100))

        return X, y

    def test_initialization_with_random_state(self):
        """Test model initialization with random state"""
        model = ConcreteForecaster(random_state=123)

        assert model.random_state == 123
        assert hasattr(model, "created_at")
        assert hasattr(model, "model_id")
        assert isinstance(model.model_id, str)

    def test_fit_accepts_vintage_date(self, sample_data):
        """Test that fit() accepts vintage_date parameter"""
        X, y = sample_data
        model = ConcreteForecaster(random_state=42)

        # Fit with vintage date
        result = model.fit(X, y, vintage_date="2024-11-15")

        assert result is model  # Should return self for chaining
        assert model.vintage_date == "2024-11-15"
        assert model.is_fitted is True

    def test_predict_requires_fitted_model(self, sample_data):
        """Test that predict() requires model to be fitted first"""
        X, _ = sample_data
        model = ConcreteForecaster(random_state=42)

        # Should fail before fitting
        with pytest.raises(ValueError) as exc_info:
            model.predict(X)

        assert "fitted" in str(exc_info.value).lower()

    def test_predict_after_fit_works(self, sample_data):
        """Test that predict() works after fitting"""
        X, y = sample_data
        model = ConcreteForecaster(random_state=42)

        # Fit then predict
        model.fit(X, y, vintage_date="2024-11-15")
        predictions = model.predict(X)

        assert isinstance(predictions, np.ndarray)
        assert len(predictions) == len(X)

    def test_get_params_returns_dict(self, sample_data):
        """Test that get_params() returns dictionary"""
        X, y = sample_data
        model = ConcreteForecaster(random_state=42)
        model.fit(X, y, vintage_date="2024-11-15")

        params = model.get_params()

        assert isinstance(params, dict)
        assert "random_state" in params
        assert params["random_state"] == 42


class TestDeterminism:
    """Test deterministic behavior with random_state"""

    @pytest.fixture
    def sample_data(self):
        """Create sample training data"""
        np.random.seed(42)
        X = pd.DataFrame(
            {
                "feature_1": np.random.randn(100),
                "feature_2": np.random.randn(100),
            }
        )
        y = pd.Series(np.random.randn(100))

        return X, y

    def test_same_seed_produces_same_predictions(self, sample_data):
        """Test that same random_state produces identical predictions"""
        X, y = sample_data

        # Train two models with same seed
        model_1 = ConcreteForecaster(random_state=42)
        model_1.fit(X, y, vintage_date="2024-11-15")
        predictions_1 = model_1.predict(X)

        model_2 = ConcreteForecaster(random_state=42)
        model_2.fit(X, y, vintage_date="2024-11-15")
        predictions_2 = model_2.predict(X)

        # Should be identical
        np.testing.assert_array_equal(predictions_1, predictions_2)

    def test_different_seed_produces_different_predictions(self, sample_data):
        """Test that different random_state produces different predictions"""
        X, y = sample_data

        # Train two models with different seeds
        model_1 = ConcreteForecaster(random_state=42)
        model_1.fit(X, y, vintage_date="2024-11-15")
        predictions_1 = model_1.predict(X)

        model_2 = ConcreteForecaster(random_state=123)
        model_2.fit(X, y, vintage_date="2024-11-15")
        predictions_2 = model_2.predict(X)

        # Should be different
        assert not np.array_equal(predictions_1, predictions_2)

    def test_seed_reproducibility_across_runs(self, sample_data):
        """Test reproducibility across multiple fit/predict cycles"""
        X, y = sample_data

        predictions_list = []

        for _ in range(3):
            model = ConcreteForecaster(random_state=42)
            model.fit(X, y, vintage_date="2024-11-15")
            predictions = model.predict(X)
            predictions_list.append(predictions)

        # All predictions should be identical
        for i in range(1, 3):
            np.testing.assert_array_equal(predictions_list[0], predictions_list[i])


class TestSaveLoadInterface:
    """Test save/load interface (if implemented)"""

    @pytest.fixture
    def sample_data(self):
        """Create sample training data"""
        np.random.seed(42)
        X = pd.DataFrame(
            {
                "feature_1": np.random.randn(50),
                "feature_2": np.random.randn(50),
            }
        )
        y = pd.Series(np.random.randn(50))

        return X, y

    def test_save_method_exists(self):
        """Test that save() method is defined"""
        model = ConcreteForecaster(random_state=42)
        assert hasattr(model, "save")
        assert callable(model.save)

    def test_load_method_exists(self):
        """Test that load() class method is defined"""
        assert hasattr(BaseForecaster, "load")
        assert callable(BaseForecaster.load)


class TestVintageParameterValidation:
    """Test vintage_date parameter validation"""

    @pytest.fixture
    def sample_data(self):
        """Create sample training data"""
        X = pd.DataFrame({"feature": [1, 2, 3]})
        y = pd.Series([1, 2, 3])
        return X, y

    def test_vintage_date_string_format(self, sample_data):
        """Test that vintage_date accepts string format"""
        X, y = sample_data
        model = ConcreteForecaster(random_state=42)

        # Should accept ISO date string
        model.fit(X, y, vintage_date="2024-11-15")
        assert model.vintage_date == "2024-11-15"

    def test_get_params_includes_vintage_date(self, sample_data):
        """Test that get_params() includes vintage_date"""
        X, y = sample_data
        model = ConcreteForecaster(random_state=42)
        model.fit(X, y, vintage_date="2024-11-15")

        params = model.get_params()

        assert "vintage_date" in params
        assert params["vintage_date"] == "2024-11-15"
