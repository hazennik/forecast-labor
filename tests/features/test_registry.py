"""
Tests for feature registry.

Tests feature metadata tracking, versioning, database logging, and lineage.
"""

import pytest
from unittest.mock import Mock, patch


class TestFeatureRegistry:
    """Test feature registry functionality."""

    def test_registry_initialization(self):
        """Test FeatureRegistry initialization."""
        from features.registry import FeatureRegistry

        registry = FeatureRegistry()
        assert registry is not None

    def test_register_feature(self):
        """Test registering a new feature."""
        from features.registry import FeatureRegistry

        registry = FeatureRegistry()

        feature_metadata = {
            "name": "treasury_withholdings_lag_0",
            "source": "treasury",
            "frequency": "daily",
            "transform": "midas_lag",
            "version": "1.0.0",
        }

        feature_id = registry.register(feature_metadata)

        assert feature_id is not None
        assert isinstance(feature_id, str)

    def test_get_feature_metadata(self):
        """Test retrieving feature metadata."""
        from features.registry import FeatureRegistry

        registry = FeatureRegistry()

        metadata = {
            "name": "test_feature",
            "source": "ces",
            "frequency": "monthly",
        }

        feature_id = registry.register(metadata)
        retrieved = registry.get(feature_id)

        assert retrieved["name"] == "test_feature"
        assert retrieved["source"] == "ces"

    def test_list_all_features(self):
        """Test listing all registered features."""
        from features.registry import FeatureRegistry

        registry = FeatureRegistry()

        # Register multiple features
        registry.register({"name": "feature1", "source": "ces"})
        registry.register({"name": "feature2", "source": "laus"})

        all_features = registry.list_all()

        assert len(all_features) >= 2

    def test_search_by_source(self):
        """Test searching features by source."""
        from features.registry import FeatureRegistry

        registry = FeatureRegistry()

        registry.register({"name": "ces_feature", "source": "ces"})
        registry.register({"name": "laus_feature", "source": "laus"})

        ces_features = registry.search(source="ces")

        assert len(ces_features) >= 1
        assert all(f["source"] == "ces" for f in ces_features)

    def test_search_by_frequency(self):
        """Test searching features by frequency."""
        from features.registry import FeatureRegistry

        registry = FeatureRegistry()

        registry.register({"name": "daily_feature", "frequency": "daily"})
        registry.register({"name": "monthly_feature", "frequency": "monthly"})

        daily_features = registry.search(frequency="daily")

        assert len(daily_features) >= 1

    def test_feature_versioning(self):
        """Test feature version tracking."""
        from features.registry import FeatureRegistry

        registry = FeatureRegistry()

        # Register v1
        v1_id = registry.register(
            {"name": "test_feature", "version": "1.0.0", "description": "Original"}
        )

        # Register v2
        v2_id = registry.register(
            {"name": "test_feature", "version": "2.0.0", "description": "Updated"}
        )

        # Should be different IDs
        assert v1_id != v2_id

        # Should be able to retrieve both versions
        versions = registry.get_versions("test_feature")
        assert len(versions) >= 2

    def test_get_latest_version(self):
        """Test retrieving latest version of a feature."""
        from features.registry import FeatureRegistry

        registry = FeatureRegistry()

        registry.register({"name": "test_feature", "version": "1.0.0"})
        registry.register({"name": "test_feature", "version": "2.0.0"})

        latest = registry.get_latest("test_feature")

        assert latest["version"] == "2.0.0"

    def test_database_logging(self):
        """Test that database backend can be mocked for testing."""
        from features.registry import FeatureRegistry

        # Test backward compatibility with deprecated use_database parameter
        # Should use in-memory when no db_config provided
        with patch("features.registry.DatabaseBackend") as mock_backend_class:
            mock_backend = Mock()
            mock_backend_class.return_value = mock_backend
            mock_backend.register_feature.return_value = "mock-uuid"

            # Using deprecated parameter but with db_config
            registry = FeatureRegistry(use_database=True, db_config={"host": "localhost"})

            feature_id = registry.register({"name": "test_feature", "source": "ces"})

            # Should register via database backend
            assert feature_id == "mock-uuid"
            mock_backend.register_feature.assert_called_once()

    def test_feature_lineage_tracking(self):
        """Test tracking feature lineage (dependencies)."""
        from features.registry import FeatureRegistry

        registry = FeatureRegistry()

        # Register base feature
        base_id = registry.register({"name": "base_series", "source": "treasury"})

        # Register derived feature
        derived_id = registry.register(
            {
                "name": "derived_feature",
                "source": "treasury",
                "depends_on": [base_id],
            }
        )

        # Should be able to get lineage
        lineage = registry.get_lineage(derived_id)

        assert base_id in lineage

    def test_vintage_tracking(self):
        """Test tracking which vintage a feature was computed from."""
        from features.registry import FeatureRegistry

        registry = FeatureRegistry()

        feature_id = registry.register(
            {
                "name": "test_feature",
                "source": "ces",
                "vintage_date": "2024-01-15",
            }
        )

        metadata = registry.get(feature_id)

        assert metadata["vintage_date"] == "2024-01-15"

    def test_update_feature_metadata(self):
        """Test updating feature metadata."""
        from features.registry import FeatureRegistry

        registry = FeatureRegistry()

        feature_id = registry.register({"name": "test_feature", "status": "draft"})

        # Update status
        registry.update(feature_id, {"status": "production"})

        updated = registry.get(feature_id)
        assert updated["status"] == "production"

    def test_delete_feature(self):
        """Test deleting a feature from registry."""
        from features.registry import FeatureRegistry

        registry = FeatureRegistry()

        feature_id = registry.register({"name": "test_feature"})

        registry.delete(feature_id)

        # Should raise error when trying to get deleted feature
        with pytest.raises(KeyError):
            registry.get(feature_id)

    def test_bulk_register(self):
        """Test bulk registration of multiple features."""
        from features.registry import FeatureRegistry

        registry = FeatureRegistry()

        features = [
            {"name": "feature1", "source": "ces"},
            {"name": "feature2", "source": "laus"},
            {"name": "feature3", "source": "claims"},
        ]

        feature_ids = registry.bulk_register(features)

        assert len(feature_ids) == 3

    def test_export_registry(self):
        """Test exporting registry to file."""
        from features.registry import FeatureRegistry

        registry = FeatureRegistry()

        registry.register({"name": "feature1"})
        registry.register({"name": "feature2"})

        exported = registry.export_to_dict()

        assert len(exported) >= 2

    def test_import_registry(self):
        """Test importing registry from file."""
        from features.registry import FeatureRegistry

        registry = FeatureRegistry()

        features_data = [
            {"name": "feature1", "source": "ces"},
            {"name": "feature2", "source": "laus"},
        ]

        registry.import_from_dict(features_data)

        all_features = registry.list_all()
        assert len(all_features) >= 2


class TestFeatureMetadata:
    """Test feature metadata model."""

    def test_metadata_creation(self):
        """Test creating feature metadata."""
        from features.registry import FeatureMetadata

        metadata = FeatureMetadata(
            name="test_feature",
            source="ces",
            frequency="monthly",
            version="1.0.0",
        )

        assert metadata.name == "test_feature"
        assert metadata.source == "ces"

    def test_metadata_validation(self):
        """Test metadata validation."""
        from features.registry import FeatureMetadata

        # Missing required field should raise TypeError (dataclass requirement)
        with pytest.raises(TypeError):
            FeatureMetadata(source="ces")  # Missing name

        # Empty name should raise ValueError in __post_init__
        with pytest.raises(ValueError, match="Feature name is required"):
            FeatureMetadata(name="")  # Empty name not allowed

    def test_metadata_to_dict(self):
        """Test converting metadata to dictionary."""
        from features.registry import FeatureMetadata

        metadata = FeatureMetadata(
            name="test_feature",
            source="ces",
            frequency="monthly",
        )

        data_dict = metadata.to_dict()

        assert isinstance(data_dict, dict)
        assert data_dict["name"] == "test_feature"

    def test_metadata_from_dict(self):
        """Test creating metadata from dictionary."""
        from features.registry import FeatureMetadata

        data = {
            "name": "test_feature",
            "source": "ces",
            "frequency": "monthly",
        }

        metadata = FeatureMetadata.from_dict(data)

        assert metadata.name == "test_feature"
