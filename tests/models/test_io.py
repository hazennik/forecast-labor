"""
Tests for model I/O and serialization utilities.

This module tests model persistence, metadata integrity, versioning,
and feature registry integration.
"""

import pytest
import json
from datetime import date, datetime, timezone

from models_src.utils.io import (
    save_model,
    load_model,
    compute_artifact_hash,
    verify_artifact_signature,
    ModelMetadata,
    save_model_with_metadata,
    load_model_with_metadata,
)
from models_src.utils.base_model import BaseForecaster


# ============================================================================
# Test Helpers (Module-level for pickling)
# ============================================================================


class MockForecaster(BaseForecaster):
    """Mock forecaster for testing I/O operations.

    This must be at module level (not inside a fixture) to be pickleable.
    """

    def __init__(self, random_state=42):
        super().__init__(random_state=random_state)
        self.model_param = "test_value"
        self._fitted_at = None

    def fit(self, X, y, vintage_date, **kwargs):
        """Fit mock model."""
        self._is_fitted = True
        self._fitted_at = datetime.now(timezone.utc)
        return self

    def predict(self, X, **kwargs):
        """Generate mock predictions."""
        import pandas as pd

        if not self._is_fitted:
            raise RuntimeError("Model must be fitted before calling predict.")
        return pd.DataFrame({"prediction": [1.0] * len(X)})

    def get_params(self):
        """Return mock parameters."""
        return {
            "random_state": self.random_state,
            "model_param": self.model_param,
            "fitted": self._is_fitted,
            "model_id": self.model_id,
        }


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def temp_model_dir(tmp_path):
    """Create a temporary directory for model artifacts."""
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    yield model_dir
    # Cleanup is automatic with tmp_path


@pytest.fixture
def mock_model():
    """Create a mock model for testing."""
    return MockForecaster(random_state=42)


@pytest.fixture
def sample_metadata():
    """Create sample model metadata."""
    return ModelMetadata(
        model_id="test-model-123",
        model_type="MockForecaster",
        training_date=datetime(2025, 1, 15, 10, 30, tzinfo=timezone.utc),
        vintage_date=date(2025, 1, 1),
        features=["feature1", "feature2", "feature3"],
        hyperparameters={"learning_rate": 0.01, "max_depth": 5},
        metrics={"rmse": 100.5, "smape": 15.2},
        python_version="3.11.0",
        dependencies={"pandas": "2.0.0", "numpy": "1.24.0"},
    )


# ============================================================================
# Basic Save/Load Tests
# ============================================================================


class TestBasicIO:
    """Test basic model save and load operations."""

    def test_save_model_with_pickle(self, mock_model, temp_model_dir):
        """Test saving a model using pickle format."""
        file_path = temp_model_dir / "model.pkl"

        save_model(mock_model, file_path, format="pickle")

        assert file_path.exists()
        assert file_path.stat().st_size > 0

    def test_save_model_with_joblib(self, mock_model, temp_model_dir):
        """Test saving a model using joblib format."""
        file_path = temp_model_dir / "model.joblib"

        save_model(mock_model, file_path, format="joblib")

        assert file_path.exists()
        assert file_path.stat().st_size > 0

    def test_load_model_with_pickle(self, mock_model, temp_model_dir):
        """Test loading a model saved with pickle."""
        file_path = temp_model_dir / "model.pkl"
        save_model(mock_model, file_path, format="pickle")

        loaded_model = load_model(file_path, format="pickle")

        assert loaded_model is not None
        assert loaded_model.random_state == mock_model.random_state
        assert loaded_model.model_param == mock_model.model_param

    def test_load_model_with_joblib(self, mock_model, temp_model_dir):
        """Test loading a model saved with joblib."""
        file_path = temp_model_dir / "model.joblib"
        save_model(mock_model, file_path, format="joblib")

        loaded_model = load_model(file_path, format="joblib")

        assert loaded_model is not None
        assert loaded_model.random_state == mock_model.random_state
        assert loaded_model.model_param == mock_model.model_param

    def test_save_load_roundtrip_pickle(self, mock_model, temp_model_dir):
        """Test that save/load roundtrip preserves model state (pickle)."""
        file_path = temp_model_dir / "model.pkl"

        # Fit the model first
        import pandas as pd
        import numpy as np

        X = pd.DataFrame(np.random.randn(10, 3))
        y = pd.Series(np.random.randn(10))
        mock_model.fit(X, y, vintage_date=date(2025, 1, 1))

        # Save and load
        save_model(mock_model, file_path, format="pickle")
        loaded_model = load_model(file_path, format="pickle")

        # Verify state is preserved
        assert loaded_model._is_fitted == mock_model._is_fitted
        assert loaded_model.model_param == mock_model.model_param
        assert loaded_model.random_state == mock_model.random_state

    def test_save_load_roundtrip_joblib(self, mock_model, temp_model_dir):
        """Test that save/load roundtrip preserves model state (joblib)."""
        file_path = temp_model_dir / "model.joblib"

        # Fit the model first
        import pandas as pd
        import numpy as np

        X = pd.DataFrame(np.random.randn(10, 3))
        y = pd.Series(np.random.randn(10))
        mock_model.fit(X, y, vintage_date=date(2025, 1, 1))

        # Save and load
        save_model(mock_model, file_path, format="joblib")
        loaded_model = load_model(file_path, format="joblib")

        # Verify state is preserved
        assert loaded_model._is_fitted == mock_model._is_fitted
        assert loaded_model.model_param == mock_model.model_param
        assert loaded_model.random_state == mock_model.random_state

    def test_save_model_invalid_format(self, mock_model, temp_model_dir):
        """Test that saving with invalid format raises an error."""
        file_path = temp_model_dir / "model.invalid"

        with pytest.raises(ValueError, match="Unsupported format"):
            save_model(mock_model, file_path, format="invalid_format")

    def test_load_model_nonexistent_file(self, temp_model_dir):
        """Test that loading a nonexistent file raises an error."""
        file_path = temp_model_dir / "nonexistent.pkl"

        with pytest.raises(FileNotFoundError):
            load_model(file_path, format="pickle")


# ============================================================================
# Artifact Hashing & Versioning Tests
# ============================================================================


class TestArtifactVersioning:
    """Test artifact hashing and signature verification."""

    def test_compute_artifact_hash(self, mock_model, temp_model_dir):
        """Test computing SHA256 hash of a model artifact."""
        file_path = temp_model_dir / "model.pkl"
        save_model(mock_model, file_path, format="pickle")

        hash_value = compute_artifact_hash(file_path)

        assert hash_value is not None
        assert len(hash_value) == 64  # SHA256 produces 64-character hex string
        assert all(c in "0123456789abcdef" for c in hash_value)

    def test_artifact_hash_consistency(self, mock_model, temp_model_dir):
        """Test that hashing the same file produces the same hash."""
        file_path = temp_model_dir / "model.pkl"
        save_model(mock_model, file_path, format="pickle")

        hash1 = compute_artifact_hash(file_path)
        hash2 = compute_artifact_hash(file_path)

        assert hash1 == hash2

    def test_artifact_hash_different_for_different_models(self, mock_model, temp_model_dir):
        """Test that different models produce different hashes."""
        file_path1 = temp_model_dir / "model1.pkl"
        file_path2 = temp_model_dir / "model2.pkl"

        # Save same model
        save_model(mock_model, file_path1, format="pickle")

        # Modify model and save
        mock_model.model_param = "different_value"
        save_model(mock_model, file_path2, format="pickle")

        hash1 = compute_artifact_hash(file_path1)
        hash2 = compute_artifact_hash(file_path2)

        assert hash1 != hash2

    def test_verify_artifact_signature_valid(self, mock_model, temp_model_dir):
        """Test that signature verification succeeds for valid artifact."""
        file_path = temp_model_dir / "model.pkl"
        save_model(mock_model, file_path, format="pickle")

        expected_hash = compute_artifact_hash(file_path)
        is_valid = verify_artifact_signature(file_path, expected_hash)

        assert is_valid is True

    def test_verify_artifact_signature_invalid(self, mock_model, temp_model_dir):
        """Test that signature verification fails for tampered artifact."""
        file_path = temp_model_dir / "model.pkl"
        save_model(mock_model, file_path, format="pickle")

        wrong_hash = "a" * 64  # Incorrect hash
        is_valid = verify_artifact_signature(file_path, wrong_hash)

        assert is_valid is False

    def test_verify_artifact_signature_nonexistent_file(self, temp_model_dir):
        """Test that signature verification handles nonexistent files."""
        file_path = temp_model_dir / "nonexistent.pkl"

        with pytest.raises(FileNotFoundError):
            verify_artifact_signature(file_path, "a" * 64)


# ============================================================================
# Metadata Tests
# ============================================================================


class TestModelMetadata:
    """Test model metadata functionality."""

    def test_metadata_creation(self, sample_metadata):
        """Test creating ModelMetadata instance."""
        assert sample_metadata.model_id == "test-model-123"
        assert sample_metadata.model_type == "MockForecaster"
        assert sample_metadata.vintage_date == date(2025, 1, 1)
        assert len(sample_metadata.features) == 3
        assert sample_metadata.hyperparameters["learning_rate"] == 0.01

    def test_metadata_to_dict(self, sample_metadata):
        """Test converting metadata to dictionary."""
        metadata_dict = sample_metadata.to_dict()

        assert metadata_dict["model_id"] == "test-model-123"
        assert metadata_dict["model_type"] == "MockForecaster"
        assert metadata_dict["vintage_date"] == "2025-01-01"
        assert metadata_dict["features"] == ["feature1", "feature2", "feature3"]
        assert metadata_dict["hyperparameters"]["learning_rate"] == 0.01

    def test_metadata_from_dict(self, sample_metadata):
        """Test creating metadata from dictionary."""
        metadata_dict = sample_metadata.to_dict()
        reconstructed = ModelMetadata.from_dict(metadata_dict)

        assert reconstructed.model_id == sample_metadata.model_id
        assert reconstructed.model_type == sample_metadata.model_type
        assert reconstructed.vintage_date == sample_metadata.vintage_date
        assert reconstructed.features == sample_metadata.features
        assert reconstructed.hyperparameters == sample_metadata.hyperparameters

    def test_metadata_serialization_roundtrip(self, sample_metadata):
        """Test that metadata can be serialized and deserialized."""
        metadata_dict = sample_metadata.to_dict()
        json_str = json.dumps(metadata_dict)
        parsed_dict = json.loads(json_str)
        reconstructed = ModelMetadata.from_dict(parsed_dict)

        assert reconstructed.model_id == sample_metadata.model_id
        assert reconstructed.vintage_date == sample_metadata.vintage_date


# ============================================================================
# Model + Metadata Save/Load Tests
# ============================================================================


class TestModelWithMetadata:
    """Test saving and loading models with metadata."""

    def test_save_model_with_metadata(self, mock_model, sample_metadata, temp_model_dir):
        """Test saving model with associated metadata."""
        artifact = save_model_with_metadata(
            model=mock_model,
            metadata=sample_metadata,
            output_dir=temp_model_dir,
            model_name="test_model",
        )

        assert artifact.model_path.exists()
        assert artifact.metadata_path.exists()
        assert artifact.hash_value is not None
        assert len(artifact.hash_value) == 64

    def test_load_model_with_metadata(self, mock_model, sample_metadata, temp_model_dir):
        """Test loading model with metadata."""
        artifact = save_model_with_metadata(
            model=mock_model,
            metadata=sample_metadata,
            output_dir=temp_model_dir,
            model_name="test_model",
        )

        loaded_artifact = load_model_with_metadata(artifact.model_path)

        assert loaded_artifact.model is not None
        assert loaded_artifact.metadata is not None
        assert loaded_artifact.metadata.model_id == sample_metadata.model_id
        assert loaded_artifact.model.random_state == mock_model.random_state

    def test_save_load_metadata_roundtrip(self, mock_model, sample_metadata, temp_model_dir):
        """Test that metadata is preserved during save/load."""
        artifact = save_model_with_metadata(
            model=mock_model,
            metadata=sample_metadata,
            output_dir=temp_model_dir,
            model_name="test_model",
        )

        loaded_artifact = load_model_with_metadata(artifact.model_path)

        # Verify all metadata fields are preserved
        assert loaded_artifact.metadata.model_id == sample_metadata.model_id
        assert loaded_artifact.metadata.model_type == sample_metadata.model_type
        assert loaded_artifact.metadata.vintage_date == sample_metadata.vintage_date
        assert loaded_artifact.metadata.features == sample_metadata.features
        assert loaded_artifact.metadata.hyperparameters == sample_metadata.hyperparameters
        assert loaded_artifact.metadata.metrics == sample_metadata.metrics

    def test_metadata_includes_artifact_hash(self, mock_model, sample_metadata, temp_model_dir):
        """Test that saved metadata includes artifact hash."""
        artifact = save_model_with_metadata(
            model=mock_model,
            metadata=sample_metadata,
            output_dir=temp_model_dir,
            model_name="test_model",
        )

        # Read metadata file
        with open(artifact.metadata_path, "r") as f:
            metadata_dict = json.load(f)

        assert "artifact_hash" in metadata_dict
        assert metadata_dict["artifact_hash"] == artifact.hash_value

    def test_load_verifies_artifact_signature(self, mock_model, sample_metadata, temp_model_dir):
        """Test that loading verifies artifact hasn't been tampered with."""
        artifact = save_model_with_metadata(
            model=mock_model,
            metadata=sample_metadata,
            output_dir=temp_model_dir,
            model_name="test_model",
        )

        # Tamper with the model file
        with open(artifact.model_path, "ab") as f:
            f.write(b"TAMPERED")

        # Loading should detect tampering
        with pytest.raises(ValueError, match="Artifact signature verification failed"):
            load_model_with_metadata(artifact.model_path, verify_signature=True)

    def test_load_without_signature_verification(self, mock_model, sample_metadata, temp_model_dir):
        """Test that signature verification can be disabled."""
        artifact = save_model_with_metadata(
            model=mock_model,
            metadata=sample_metadata,
            output_dir=temp_model_dir,
            model_name="test_model",
        )

        # Tamper with the model file
        with open(artifact.model_path, "ab") as f:
            f.write(b"TAMPERED")

        # Loading without verification should succeed (but we should warn)
        loaded_artifact = load_model_with_metadata(artifact.model_path, verify_signature=False)

        assert loaded_artifact.model is not None


# ============================================================================
# Feature Registry Integration Tests
# ============================================================================


class TestFeatureRegistryIntegration:
    """Test integration between model I/O and feature registry."""

    def test_metadata_includes_feature_registry_info(self, mock_model, temp_model_dir):
        """Test that metadata includes feature registry information."""
        metadata = ModelMetadata(
            model_id="test-model",
            model_type="MockForecaster",
            training_date=datetime.now(timezone.utc),
            vintage_date=date(2025, 1, 1),
            features=["feature1", "feature2"],
            hyperparameters={},
            metrics={},
            python_version="3.11.0",
            dependencies={},
        )

        # When we save with feature registry integration enabled
        # (Full implementation in Phase 5.2, for now just verify flag is accepted)
        artifact = save_model_with_metadata(
            model=mock_model,
            metadata=metadata,
            output_dir=temp_model_dir,
            model_name="test_model",
            include_feature_info=True,
        )

        # Metadata should include feature list
        loaded_artifact = load_model_with_metadata(artifact.model_path)

        # This test verifies the integration point exists
        # Full feature registry implementation will be in Phase 5.2
        assert loaded_artifact.metadata.features == ["feature1", "feature2"]

    def test_model_artifact_tracks_feature_versions(self, mock_model, temp_model_dir):
        """Test that ModelArtifact can track feature versions."""
        metadata = ModelMetadata(
            model_id="test-model",
            model_type="MockForecaster",
            training_date=datetime.now(timezone.utc),
            vintage_date=date(2025, 1, 1),
            features=["feature1", "feature2"],
            hyperparameters={},
            metrics={},
            python_version="3.11.0",
            dependencies={},
            feature_versions={"feature1": "v1.0", "feature2": "v1.1"},
        )

        artifact = save_model_with_metadata(
            model=mock_model,
            metadata=metadata,
            output_dir=temp_model_dir,
            model_name="test_model",
        )

        loaded_artifact = load_model_with_metadata(artifact.model_path)

        assert loaded_artifact.metadata.feature_versions is not None
        assert loaded_artifact.metadata.feature_versions["feature1"] == "v1.0"
        assert loaded_artifact.metadata.feature_versions["feature2"] == "v1.1"
