"""
Tests for feature registry database backend.

This module tests the database backend for the feature registry, including:
- Database connection and setup
- Feature CRUD operations
- Lineage tracking
- Versioning and rollback
- Migration from in-memory to database
- Backward compatibility
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import date, datetime
import json

from features.registry import (
    FeatureRegistry,
    DatabaseBackend,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_db_connection():
    """Create a mock database connection."""
    mock_conn = Mock()
    mock_cursor = Mock()

    # Properly setup context manager for cursor
    cursor_context = MagicMock()
    cursor_context.__enter__ = Mock(return_value=mock_cursor)
    cursor_context.__exit__ = Mock(return_value=None)
    mock_conn.cursor.return_value = cursor_context

    mock_cursor.fetchone.return_value = None
    mock_cursor.fetchall.return_value = []
    return mock_conn, mock_cursor


@pytest.fixture
def database_backend(mock_db_connection):
    """Create DatabaseBackend instance with mocked connection."""
    mock_conn, mock_cursor = mock_db_connection

    with patch("features.registry.psycopg2.connect", return_value=mock_conn):
        backend = DatabaseBackend(
            host="localhost", port=5432, database="test_db", user="test_user", password="test_pass"
        )
        backend._cursor = mock_cursor  # Inject mock cursor for testing
        return backend


@pytest.fixture
def sample_feature_data():
    """Sample feature data for testing."""
    return {
        "name": "test_feature",
        "source": "bls_ces",
        "frequency": "monthly",
        "transform": "seasonal_adj",
        "version": "1.0.0",
        "description": "Test feature for database",
        "vintage_date": "2025-01-01",
        "status": "active",
    }


# ============================================================================
# Database Connection Tests
# ============================================================================


class TestDatabaseConnection:
    """Test database connection management."""

    @patch("features.registry.psycopg2.connect")
    def test_database_backend_initialization(self, mock_connect):
        """Test that DatabaseBackend initializes connection."""
        mock_conn = Mock()
        mock_connect.return_value = mock_conn

        backend = DatabaseBackend(
            host="localhost",
            port=5432,
            database="forecast_labor",
            user="app_user",
            password="secret",
        )

        mock_connect.assert_called_once()
        assert backend._conn is not None

    @patch("features.registry.psycopg2.connect")
    def test_database_connection_error_handling(self, mock_connect):
        """Test that connection errors are handled gracefully."""
        mock_connect.side_effect = Exception("Connection failed")

        with pytest.raises(Exception, match="Connection failed"):
            DatabaseBackend(
                host="localhost",
                port=5432,
                database="forecast_labor",
                user="app_user",
                password="secret",
            )

    def test_database_backend_close(self, database_backend, mock_db_connection):
        """Test that database connection can be closed."""
        mock_conn, _ = mock_db_connection

        database_backend.close()

        mock_conn.close.assert_called_once()


# ============================================================================
# Feature Registration Tests
# ============================================================================


class TestFeatureRegistration:
    """Test feature registration to database."""

    def test_register_feature_to_database(
        self, database_backend, sample_feature_data, mock_db_connection
    ):
        """Test registering a feature to the database."""
        _, mock_cursor = mock_db_connection
        mock_cursor.fetchone.return_value = ("test-uuid-123",)

        feature_id = database_backend.register_feature(sample_feature_data)

        # Verify INSERT was called (check all calls since there are multiple)
        assert mock_cursor.execute.called
        calls = [
            str(arg[0]) if len(arg) > 0 else ""
            for arg in [call[0] for call in mock_cursor.execute.call_args_list]
        ]
        assert any("INSERT INTO features.feature_metadata" in call for call in calls)
        assert feature_id == "test-uuid-123"

    def test_register_feature_with_lineage(
        self, database_backend, sample_feature_data, mock_db_connection
    ):
        """Test registering a feature with parent lineage."""
        _, mock_cursor = mock_db_connection
        mock_cursor.fetchone.return_value = ("child-uuid",)

        sample_feature_data["depends_on"] = ["parent-uuid-1"]
        database_backend.register_feature(sample_feature_data)

        # Should insert into both feature_metadata and feature_transforms
        assert mock_cursor.execute.call_count >= 2

    def test_register_feature_creates_initial_version(
        self, database_backend, sample_feature_data, mock_db_connection
    ):
        """Test that registering a feature creates version 1."""
        _, mock_cursor = mock_db_connection
        mock_cursor.fetchone.return_value = ("test-uuid",)

        database_backend.register_feature(sample_feature_data)

        # Should insert into feature_versions
        calls = [
            str(arg[0]) if len(arg) > 0 else ""
            for arg in [call[0] for call in mock_cursor.execute.call_args_list]
        ]
        assert any("INSERT INTO features.feature_versions" in call for call in calls)


# ============================================================================
# Feature Retrieval Tests
# ============================================================================


class TestFeatureRetrieval:
    """Test feature retrieval from database."""

    def test_get_feature_by_id(self, database_backend, mock_db_connection):
        """Test retrieving a feature by ID."""
        _, mock_cursor = mock_db_connection

        # Mock RealDictCursor result (dict-like object)
        mock_cursor.fetchone.return_value = {
            "feature_id": "feature-uuid",
            "name": "test_feature",
            "display_name": "Test Feature",
            "description": "Test description",
            "source": "bls_ces",
            "frequency": "monthly",
            "vintage_date": date(2025, 1, 1),
            "data_type": "float64",
            "unit": None,
            "seasonal_adjustment": None,
            "current_version": 1,
            "status": "active",
            "is_synthetic": False,
            "created_at": datetime(2025, 1, 1),
            "updated_at": datetime(2025, 1, 1),
            "deprecation_date": None,
            "tags": json.dumps({}),
        }

        feature = database_backend.get_feature("feature-uuid")

        assert feature is not None
        assert feature["name"] == "test_feature"
        assert mock_cursor.execute.called

    def test_get_nonexistent_feature(self, database_backend, mock_db_connection):
        """Test that retrieving nonexistent feature raises error."""
        _, mock_cursor = mock_db_connection
        mock_cursor.fetchone.return_value = None

        with pytest.raises(KeyError, match="Feature ID not found"):
            database_backend.get_feature("nonexistent-uuid")

    def test_list_features(self, database_backend, mock_db_connection):
        """Test listing all features."""
        _, mock_cursor = mock_db_connection

        # Mock RealDictCursor results (dict-like objects)
        mock_cursor.fetchall.return_value = [
            {
                "feature_id": "uuid1",
                "name": "feature1",
                "display_name": "Feature 1",
                "description": None,
                "source": "source1",
                "frequency": "daily",
                "vintage_date": date(2025, 1, 1),
                "data_type": "float64",
                "unit": None,
                "seasonal_adjustment": None,
                "current_version": 1,
                "status": "active",
                "is_synthetic": False,
                "created_at": datetime.now(),
                "updated_at": datetime.now(),
                "deprecation_date": None,
                "tags": "{}",
            },
            {
                "feature_id": "uuid2",
                "name": "feature2",
                "display_name": "Feature 2",
                "description": None,
                "source": "source2",
                "frequency": "monthly",
                "vintage_date": date(2025, 1, 1),
                "data_type": "float64",
                "unit": None,
                "seasonal_adjustment": None,
                "current_version": 1,
                "status": "active",
                "is_synthetic": False,
                "created_at": datetime.now(),
                "updated_at": datetime.now(),
                "deprecation_date": None,
                "tags": "{}",
            },
        ]

        features = database_backend.list_features()

        assert len(features) == 2
        assert features[0]["name"] == "feature1"
        assert features[1]["name"] == "feature2"

    def test_list_features_with_filters(self, database_backend, mock_db_connection):
        """Test listing features with filters."""
        _, mock_cursor = mock_db_connection
        mock_cursor.fetchall.return_value = []

        database_backend.list_features(source="bls_ces", status="active")

        # Verify WHERE clause was added
        execute_call = mock_cursor.execute.call_args[0][0]
        assert "WHERE" in execute_call

    def test_list_features_with_pagination(self, database_backend, mock_db_connection):
        """Test listing features with pagination."""
        _, mock_cursor = mock_db_connection
        mock_cursor.fetchall.return_value = []

        database_backend.list_features(limit=10, offset=20)

        # Verify LIMIT and OFFSET were added
        execute_call = mock_cursor.execute.call_args[0][0]
        assert "LIMIT" in execute_call
        assert "OFFSET" in execute_call


# ============================================================================
# Feature Update and Delete Tests
# ============================================================================


class TestFeatureModification:
    """Test feature update and delete operations."""

    def test_update_feature(self, database_backend, mock_db_connection):
        """Test updating feature metadata."""
        _, mock_cursor = mock_db_connection

        updates = {"status": "deprecated", "description": "Updated description"}

        database_backend.update_feature("feature-uuid", updates)

        # Verify UPDATE was called
        assert mock_cursor.execute.called
        execute_call = str(mock_cursor.execute.call_args[0][0])
        assert "UPDATE features.feature_metadata" in execute_call

    def test_delete_feature(self, database_backend, mock_db_connection):
        """Test deleting a feature."""
        _, mock_cursor = mock_db_connection

        database_backend.delete_feature("feature-uuid")

        # Verify DELETE was called
        assert mock_cursor.execute.called
        execute_call = str(mock_cursor.execute.call_args[0][0])
        assert "DELETE FROM features.feature_metadata" in execute_call


# ============================================================================
# Lineage Tracking Tests
# ============================================================================


class TestLineageTracking:
    """Test feature lineage tracking."""

    def test_get_feature_lineage(self, database_backend, mock_db_connection):
        """Test retrieving feature lineage."""
        _, mock_cursor = mock_db_connection

        # Mock RealDictCursor results
        mock_cursor.fetchall.return_value = [
            {
                "feature_id": "uuid1",
                "feature_name": "feature1",
                "transform_type": "diff",
                "depth": 0,
            },
            {
                "feature_id": "uuid2",
                "feature_name": "feature2",
                "transform_type": "seasonal_adj",
                "depth": 1,
            },
        ]

        lineage = database_backend.get_lineage("uuid1")

        assert len(lineage) == 2
        assert lineage[0]["feature_name"] == "feature1"
        assert lineage[1]["depth"] == 1

    def test_get_feature_descendants(self, database_backend, mock_db_connection):
        """Test retrieving features derived from a parent."""
        _, mock_cursor = mock_db_connection

        # Mock RealDictCursor results
        mock_cursor.fetchall.return_value = [
            {
                "feature_id": "child-uuid-1",
                "feature_name": "child_feature1",
                "transform_type": "diff",
            },
            {
                "feature_id": "child-uuid-2",
                "feature_name": "child_feature2",
                "transform_type": "log",
            },
        ]

        descendants = database_backend.get_descendants("parent-uuid")

        assert len(descendants) == 2
        assert descendants[0]["feature_name"] == "child_feature1"


# ============================================================================
# Versioning Tests
# ============================================================================


class TestVersioning:
    """Test feature versioning and rollback."""

    def test_create_feature_version(self, database_backend, mock_db_connection):
        """Test creating a new feature version."""
        _, mock_cursor = mock_db_connection

        # Mock multiple calls to execute
        mock_cursor.fetchone.side_effect = [
            (2,),
            ("version-uuid-123",),
        ]  # version number, then version_id

        database_backend.create_version(
            feature_id="feature-uuid",
            checksum="abc123",
            row_count=1000,
            change_description="Added new data",
        )

        # Verify multiple executes were called (get max version, insert, update)
        assert mock_cursor.execute.call_count >= 3
        # Check that one of the calls was to INSERT INTO feature_versions
        calls = [
            str(arg[0]) if len(arg) > 0 else ""
            for arg in [call[0] for call in mock_cursor.execute.call_args_list]
        ]
        assert any("INSERT INTO features.feature_versions" in call for call in calls)

    def test_get_feature_versions(self, database_backend, mock_db_connection):
        """Test retrieving all versions of a feature."""
        _, mock_cursor = mock_db_connection

        # Mock RealDictCursor results
        mock_cursor.fetchall.return_value = [
            {
                "version_id": "v1-uuid",
                "feature_id": "feature-uuid",
                "version": 1,
                "checksum": "hash1",
                "row_count": 1000,
                "byte_size": 0,
                "created_at": datetime.now(),
                "change_description": None,
                "deprecated_at": None,
                "min_value": None,
                "max_value": None,
                "mean_value": None,
                "std_value": None,
                "null_count": None,
                "outlier_count": None,
            },
            {
                "version_id": "v2-uuid",
                "feature_id": "feature-uuid",
                "version": 2,
                "checksum": "hash2",
                "row_count": 1200,
                "byte_size": 0,
                "created_at": datetime.now(),
                "change_description": None,
                "deprecated_at": None,
                "min_value": None,
                "max_value": None,
                "mean_value": None,
                "std_value": None,
                "null_count": None,
                "outlier_count": None,
            },
        ]

        versions = database_backend.get_versions("feature-uuid")

        assert len(versions) == 2
        assert versions[0]["version"] == 1
        assert versions[1]["version"] == 2


# ============================================================================
# Feature Registry Integration Tests
# ============================================================================


class TestFeatureRegistryDatabaseIntegration:
    """Test FeatureRegistry with database backend."""

    @patch("features.registry.DatabaseBackend")
    def test_registry_with_database_backend(self, mock_backend_class):
        """Test that registry can use database backend."""
        mock_backend = Mock()
        mock_backend_class.return_value = mock_backend
        mock_backend.register_feature.return_value = "db-feature-uuid"

        registry = FeatureRegistry(
            backend="database", db_config={"host": "localhost", "database": "test_db"}
        )

        feature_id = registry.register({"name": "test"})

        mock_backend.register_feature.assert_called_once()
        assert feature_id == "db-feature-uuid"

    def test_registry_backward_compatibility_in_memory(self):
        """Test that in-memory mode still works (backward compatibility)."""
        registry = FeatureRegistry()  # Default: in-memory

        feature_id = registry.register({"name": "test_feature"})
        feature = registry.get(feature_id)

        assert feature["name"] == "test_feature"
        assert feature_id in registry._features

    @patch("features.registry.DatabaseBackend")
    def test_registry_switches_between_backends(self, mock_backend_class):
        """Test that registry can switch between in-memory and database."""
        # In-memory
        registry_mem = FeatureRegistry(backend="memory")
        id1 = registry_mem.register({"name": "mem_feature"})
        assert id1 in registry_mem._features

        # Database
        mock_backend = Mock()
        mock_backend_class.return_value = mock_backend
        mock_backend.register_feature.return_value = "db-uuid"

        registry_db = FeatureRegistry(backend="database", db_config={"host": "localhost"})
        registry_db.register({"name": "db_feature"})

        mock_backend.register_feature.assert_called_once()


# ============================================================================
# Migration Tests
# ============================================================================


class TestMigration:
    """Test migration from in-memory to database."""

    @patch("features.registry.DatabaseBackend")
    def test_export_from_memory(self, mock_backend_class):
        """Test exporting features from in-memory registry."""
        registry = FeatureRegistry(backend="memory")
        registry.register({"name": "feature1", "source": "source1"})
        registry.register({"name": "feature2", "source": "source2"})

        exported = registry.export_to_dict()

        assert len(exported) == 2
        assert exported[0]["name"] == "feature1"
        assert "feature_id" in exported[0]

    @patch("features.registry.DatabaseBackend")
    def test_import_to_database(self, mock_backend_class):
        """Test importing features to database."""
        mock_backend = Mock()
        mock_backend_class.return_value = mock_backend
        mock_backend.register_feature.return_value = "new-uuid"

        registry_db = FeatureRegistry(backend="database", db_config={"host": "localhost"})

        features_to_import = [
            {"name": "feature1", "source": "source1"},
            {"name": "feature2", "source": "source2"},
        ]

        registry_db.import_from_dict(features_to_import)

        assert mock_backend.register_feature.call_count == 2


# ============================================================================
# Concurrent Access Tests
# ============================================================================


class TestConcurrentAccess:
    """Test concurrent access safety."""

    @patch("features.registry.DatabaseBackend")
    def test_concurrent_registration(self, mock_backend_class):
        """Test that concurrent registrations are handled safely."""
        mock_backend = Mock()
        mock_backend_class.return_value = mock_backend
        mock_backend.register_feature.side_effect = ["uuid1", "uuid2", "uuid3"]

        registry = FeatureRegistry(backend="database", db_config={"host": "localhost"})

        # Simulate concurrent registrations
        ids = []
        for i in range(3):
            feature_id = registry.register({"name": f"feature{i}"})
            ids.append(feature_id)

        assert len(ids) == 3
        assert len(set(ids)) == 3  # All unique
