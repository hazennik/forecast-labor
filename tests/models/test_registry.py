"""
Tests for model registry integration.

This module tests model registry operations including:
- Model registration to MLflow
- Feature registry linkage
- Model promotion (staging/production)
- Model retrieval by name/stage
- Feature lineage queries
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch

from models_src.utils.registry import (
    ModelRegistryClient,
    register_model,
    get_model_by_name,
    promote_model,
)
from models_src.utils.base_model import BaseForecaster


# ============================================================================
# Test Helpers
# ============================================================================


class MockForecaster(BaseForecaster):
    """Mock forecaster for testing registry operations."""

    def __init__(self, random_state=42):
        super().__init__(random_state=random_state)
        self._is_fitted = False

    def fit(self, X, y, vintage_date):
        """Fit mock model."""
        self._is_fitted = True
        self.vintage_date = vintage_date
        self.feature_names = X.columns.tolist()
        return self

    def predict(self, X):
        """Generate mock predictions."""
        if not self._is_fitted:
            raise ValueError("Model must be fitted before prediction")
        return X.iloc[:, 0].values

    def get_params(self):
        """Return mock parameters."""
        return {
            "random_state": self.random_state,
            "is_fitted": self._is_fitted,
        }


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_mlflow_client():
    """Create mock MLflow client."""
    client = Mock()

    # Mock model registration
    client.create_registered_model.return_value = Mock(name="test_model")
    client.create_model_version.return_value = Mock(version=1, run_id="run123")

    # Mock model retrieval
    mock_model_version = Mock()
    mock_model_version.name = "test_model"
    mock_model_version.version = 1
    mock_model_version.current_stage = "None"
    mock_model_version.run_id = "run123"
    client.get_latest_versions.return_value = [mock_model_version]
    client.get_model_version.return_value = mock_model_version

    # Mock stage transition
    client.transition_model_version_stage.return_value = mock_model_version

    return client


@pytest.fixture
def mock_feature_registry():
    """Create mock feature registry."""
    registry = Mock()

    # Mock feature search
    registry.search.return_value = [
        {
            "feature_id": "feat-1",
            "name": "feature_1",
            "source": "ces",
            "frequency": "monthly",
            "version": "1.0.0",
        },
        {
            "feature_id": "feat-2",
            "name": "feature_2",
            "source": "laus",
            "frequency": "monthly",
            "version": "1.0.0",
        },
    ]

    return registry


@pytest.fixture
def mock_model():
    """Create mock model instance."""
    return MockForecaster(random_state=42)


@pytest.fixture
def sample_model_metadata():
    """Sample model metadata."""
    return {
        "model_name": "test_model",
        "model_type": "MockForecaster",
        "features": ["feature_1", "feature_2", "feature_3"],
        "vintage_date": "2024-12-31",
        "training_date": datetime.now().isoformat(),
        "metrics": {"rmse": 100.0, "mae": 80.0},
    }


# ============================================================================
# Test ModelRegistryClient
# ============================================================================


class TestModelRegistryClient:
    """Test model registry client initialization and configuration."""

    def test_client_initialization(self):
        """Test that client initializes correctly."""
        client = ModelRegistryClient(tracking_uri="http://localhost:5000")

        assert client.tracking_uri == "http://localhost:5000"
        assert client._mlflow_client is not None

    def test_client_default_tracking_uri(self):
        """Test that client works with default tracking URI."""
        client = ModelRegistryClient()

        assert client._mlflow_client is not None

    @patch("models_src.utils.registry.MlflowClient")
    def test_client_mlflow_initialization(self, mock_mlflow_class):
        """Test that MLflow client is initialized correctly."""
        mock_client = Mock()
        mock_mlflow_class.return_value = mock_client

        ModelRegistryClient(tracking_uri="http://localhost:5000")

        # Verify MLflow client was called
        mock_mlflow_class.assert_called_once()


# ============================================================================
# Test Model Registration
# ============================================================================


class TestModelRegistration:
    """Test model registration to MLflow registry."""

    @patch("models_src.utils.registry.MlflowClient")
    def test_register_model_basic(self, mock_mlflow_class, sample_model_metadata):
        """Test basic model registration."""
        mock_client = Mock()
        mock_mlflow_class.return_value = mock_client

        # Mock successful registration
        mock_client.create_model_version.return_value = Mock(version=1)

        client = ModelRegistryClient()
        result = client.register_model(
            model_uri="runs:/run123/model",
            name="test_model",
            metadata=sample_model_metadata,
        )

        assert result is not None
        assert "version" in result

    @patch("models_src.utils.registry.MlflowClient")
    def test_register_model_with_features(self, mock_mlflow_class, sample_model_metadata):
        """Test model registration with feature linkage."""
        mock_client = Mock()
        mock_mlflow_class.return_value = mock_client
        mock_client.create_model_version.return_value = Mock(version=1)

        client = ModelRegistryClient()
        result = client.register_model(
            model_uri="runs:/run123/model",
            name="test_model",
            metadata=sample_model_metadata,
            features=["feature_1", "feature_2"],
        )

        assert result is not None
        # Should have called MLflow with features in tags/metadata

    @patch("models_src.utils.registry.MlflowClient")
    def test_register_model_creates_if_not_exists(self, mock_mlflow_class):
        """Test that registration creates model if it doesn't exist."""
        mock_client = Mock()
        mock_mlflow_class.return_value = mock_client

        # First call raises error (model doesn't exist), second succeeds
        mock_client.get_registered_model.side_effect = Exception("Not found")
        mock_client.create_registered_model.return_value = Mock(name="new_model")
        mock_client.create_model_version.return_value = Mock(version=1)

        client = ModelRegistryClient()
        client.register_model(
            model_uri="runs:/run123/model",
            name="new_model",
            metadata={},
        )

        # Should have created the model
        mock_client.create_registered_model.assert_called_once()

    @patch("models_src.utils.registry.MlflowClient")
    def test_register_model_error_handling(self, mock_mlflow_class):
        """Test that registration errors are handled gracefully."""
        mock_client = Mock()
        mock_mlflow_class.return_value = mock_client
        mock_client.create_model_version.side_effect = Exception("Registration failed")

        client = ModelRegistryClient()

        with pytest.raises(Exception, match="Registration failed"):
            client.register_model(
                model_uri="runs:/run123/model",
                name="test_model",
                metadata={},
            )


# ============================================================================
# Test Model Promotion
# ============================================================================


class TestModelPromotion:
    """Test model stage promotion (None -> Staging -> Production)."""

    @patch("models_src.utils.registry.MlflowClient")
    def test_promote_to_staging(self, mock_mlflow_class):
        """Test promoting model to Staging."""
        mock_client = Mock()
        mock_mlflow_class.return_value = mock_client

        client = ModelRegistryClient()
        client.promote_model(
            name="test_model",
            version=1,
            stage="Staging",
        )

        # Should have called transition_model_version_stage
        mock_client.transition_model_version_stage.assert_called_once_with(
            name="test_model",
            version=1,
            stage="Staging",
            archive_existing_versions=False,
        )

    @patch("models_src.utils.registry.MlflowClient")
    def test_promote_to_production(self, mock_mlflow_class):
        """Test promoting model to Production."""
        mock_client = Mock()
        mock_mlflow_class.return_value = mock_client

        client = ModelRegistryClient()
        client.promote_model(
            name="test_model",
            version=2,
            stage="Production",
        )

        mock_client.transition_model_version_stage.assert_called_once_with(
            name="test_model",
            version=2,
            stage="Production",
            archive_existing_versions=False,
        )

    @patch("models_src.utils.registry.MlflowClient")
    def test_promote_archives_existing(self, mock_mlflow_class):
        """Test that promotion can archive existing versions."""
        mock_client = Mock()
        mock_mlflow_class.return_value = mock_client

        client = ModelRegistryClient()
        client.promote_model(
            name="test_model",
            version=3,
            stage="Production",
            archive_existing=True,
        )

        mock_client.transition_model_version_stage.assert_called_once_with(
            name="test_model",
            version=3,
            stage="Production",
            archive_existing_versions=True,
        )

    @patch("models_src.utils.registry.MlflowClient")
    def test_promote_invalid_stage(self, mock_mlflow_class):
        """Test that invalid stage raises error."""
        mock_client = Mock()
        mock_mlflow_class.return_value = mock_client

        client = ModelRegistryClient()

        with pytest.raises(ValueError, match="Invalid stage"):
            client.promote_model(
                name="test_model",
                version=1,
                stage="InvalidStage",
            )


# ============================================================================
# Test Model Retrieval
# ============================================================================


class TestModelRetrieval:
    """Test retrieving models by name/stage."""

    @patch("models_src.utils.registry.MlflowClient")
    def test_get_model_by_name(self, mock_mlflow_class):
        """Test retrieving model by name."""
        mock_client = Mock()
        mock_mlflow_class.return_value = mock_client

        # Mock model version
        mock_version = Mock()
        mock_version.name = "test_model"
        mock_version.version = 1
        mock_version.current_stage = "Production"
        mock_version.run_id = "run123"
        mock_client.get_latest_versions.return_value = [mock_version]

        client = ModelRegistryClient()
        result = client.get_model_by_name("test_model")

        assert result is not None
        assert result["name"] == "test_model"
        assert result["version"] == 1

    @patch("models_src.utils.registry.MlflowClient")
    def test_get_model_by_stage(self, mock_mlflow_class):
        """Test retrieving model by stage."""
        mock_client = Mock()
        mock_mlflow_class.return_value = mock_client

        mock_version = Mock()
        mock_version.name = "test_model"
        mock_version.version = 2
        mock_version.current_stage = "Production"
        mock_version.run_id = "run456"
        mock_client.get_latest_versions.return_value = [mock_version]

        client = ModelRegistryClient()
        result = client.get_model_by_stage("test_model", "Production")

        assert result is not None
        assert result["stage"] == "Production"
        assert result["version"] == 2

    @patch("models_src.utils.registry.MlflowClient")
    def test_get_model_not_found(self, mock_mlflow_class):
        """Test that missing model returns None."""
        mock_client = Mock()
        mock_mlflow_class.return_value = mock_client
        mock_client.get_latest_versions.return_value = []

        client = ModelRegistryClient()
        result = client.get_model_by_name("nonexistent_model")

        assert result is None

    @patch("models_src.utils.registry.MlflowClient")
    def test_get_all_versions(self, mock_mlflow_class):
        """Test retrieving all versions of a model."""
        mock_client = Mock()
        mock_mlflow_class.return_value = mock_client

        # Mock multiple versions
        mock_versions = [
            Mock(version=1, current_stage="Archived"),
            Mock(version=2, current_stage="Staging"),
            Mock(version=3, current_stage="Production"),
        ]
        mock_client.search_model_versions.return_value = mock_versions

        client = ModelRegistryClient()
        results = client.get_all_versions("test_model")

        assert len(results) == 3
        assert results[0]["version"] == 1


# ============================================================================
# Test Feature Linkage
# ============================================================================


class TestFeatureLinkage:
    """Test linking models to features from feature registry."""

    @patch("models_src.utils.registry.get_global_registry")
    @patch("models_src.utils.registry.MlflowClient")
    def test_link_model_to_features(self, mock_mlflow_class, mock_get_registry):
        """Test linking model to features."""
        mock_client = Mock()
        mock_mlflow_class.return_value = mock_client

        mock_registry = Mock()
        mock_registry.search.return_value = [
            {"feature_id": "feat-1", "name": "feature_1"},
        ]
        mock_get_registry.return_value = mock_registry

        client = ModelRegistryClient()
        result = client.link_features(
            model_name="test_model",
            model_version=1,
            feature_names=["feature_1", "feature_2"],
        )

        assert result is not None
        # Should have queried feature registry
        mock_registry.search.assert_called()

    @patch("models_src.utils.registry.get_global_registry")
    @patch("models_src.utils.registry.MlflowClient")
    def test_get_model_features(self, mock_mlflow_class, mock_get_registry):
        """Test retrieving features used by a model."""
        mock_client = Mock()
        mock_mlflow_class.return_value = mock_client

        # Mock model version with feature tags
        mock_version = Mock()
        mock_version.tags = {"features": "feature_1,feature_2,feature_3"}
        mock_client.get_model_version.return_value = mock_version

        client = ModelRegistryClient()
        features = client.get_model_features("test_model", version=1)

        assert len(features) == 3
        assert "feature_1" in features

    @patch("models_src.utils.registry.get_global_registry")
    @patch("models_src.utils.registry.MlflowClient")
    def test_get_models_using_feature(self, mock_mlflow_class, mock_get_registry):
        """Test finding all models that use a specific feature."""
        mock_client = Mock()
        mock_mlflow_class.return_value = mock_client

        # Mock multiple models
        mock_versions = [
            Mock(name="model1", version=1, tags={"features": "feature_1,feature_2"}),
            Mock(name="model2", version=1, tags={"features": "feature_1,feature_3"}),
            Mock(name="model3", version=1, tags={"features": "feature_2,feature_3"}),
        ]
        mock_client.search_model_versions.return_value = mock_versions

        client = ModelRegistryClient()
        models = client.get_models_using_feature("feature_1")

        # Should find model1 and model2
        assert len(models) == 2
        model_names = [m["name"] for m in models]
        assert "model1" in model_names
        assert "model2" in model_names
        assert "model3" not in model_names


# ============================================================================
# Test Feature Lineage Queries
# ============================================================================


class TestFeatureLineage:
    """Test feature lineage queries (model -> features -> sources)."""

    @patch("models_src.utils.registry.get_global_registry")
    @patch("models_src.utils.registry.MlflowClient")
    def test_get_feature_lineage(self, mock_mlflow_class, mock_get_registry):
        """Test retrieving complete feature lineage for a model."""
        mock_client = Mock()
        mock_mlflow_class.return_value = mock_client

        # Mock model with features
        mock_version = Mock()
        mock_version.tags = {"features": "feature_1,feature_2"}
        mock_client.get_model_version.return_value = mock_version

        # Mock feature registry with lineage
        mock_registry = Mock()
        mock_registry.search.return_value = [
            {
                "feature_id": "feat-1",
                "name": "feature_1",
                "source": "ces",
                "depends_on": [],
            },
        ]
        mock_registry.get_lineage.return_value = []
        mock_get_registry.return_value = mock_registry

        client = ModelRegistryClient()
        lineage = client.get_feature_lineage("test_model", version=1)

        assert lineage is not None
        assert "features" in lineage

    @patch("models_src.utils.registry.get_global_registry")
    @patch("models_src.utils.registry.MlflowClient")
    def test_get_data_sources(self, mock_mlflow_class, mock_get_registry):
        """Test retrieving all data sources used by a model."""
        mock_client = Mock()
        mock_mlflow_class.return_value = mock_client

        mock_version = Mock()
        mock_version.tags = {"features": "feature_1,feature_2"}
        mock_client.get_model_version.return_value = mock_version

        mock_registry = Mock()
        mock_registry.search.return_value = [
            {"feature_id": "feat-1", "name": "feature_1", "source": "ces"},
            {"feature_id": "feat-2", "name": "feature_2", "source": "laus"},
        ]
        mock_get_registry.return_value = mock_registry

        client = ModelRegistryClient()
        sources = client.get_data_sources("test_model", version=1)

        assert "ces" in sources
        assert "laus" in sources


# ============================================================================
# Test Standalone Functions
# ============================================================================


class TestStandaloneFunctions:
    """Test standalone convenience functions."""

    @patch("models_src.utils.registry.ModelRegistryClient")
    def test_register_model_function(self, mock_client_class):
        """Test standalone register_model function."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.register_model.return_value = {"version": 1}

        result = register_model(
            model_uri="runs:/run123/model",
            name="test_model",
            metadata={},
        )

        assert result is not None
        mock_client.register_model.assert_called_once()

    @patch("models_src.utils.registry.ModelRegistryClient")
    def test_get_model_by_name_function(self, mock_client_class):
        """Test standalone get_model_by_name function."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get_model_by_name.return_value = {"name": "test_model"}

        result = get_model_by_name("test_model")

        assert result is not None
        mock_client.get_model_by_name.assert_called_once_with("test_model")

    @patch("models_src.utils.registry.ModelRegistryClient")
    def test_promote_model_function(self, mock_client_class):
        """Test standalone promote_model function."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.promote_model.return_value = {"stage": "Production"}

        result = promote_model("test_model", version=1, stage="Production")

        assert result is not None
        mock_client.promote_model.assert_called_once()


# ============================================================================
# Test Error Handling
# ============================================================================


class TestErrorHandling:
    """Test error handling in registry operations."""

    @patch("models_src.utils.registry.MlflowClient")
    def test_mlflow_unavailable(self, mock_mlflow_class):
        """Test handling when MLflow is unavailable."""
        mock_mlflow_class.side_effect = Exception("MLflow not available")

        with pytest.raises(Exception, match="MLflow not available"):
            ModelRegistryClient()

    @patch("models_src.utils.registry.MlflowClient")
    def test_feature_registry_unavailable(self, mock_mlflow_class):
        """Test handling when feature registry is unavailable."""
        mock_client = Mock()
        mock_mlflow_class.return_value = mock_client

        client = ModelRegistryClient()

        # Should handle gracefully when feature registry is unavailable
        with patch("models_src.utils.registry.get_global_registry", side_effect=ImportError):
            # Should not crash, just return empty or None
            result = client.get_model_features("test_model", version=1)
            # Behavior depends on implementation (None or empty list)
            assert result is None or result == []
