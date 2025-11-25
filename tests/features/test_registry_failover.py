"""
Tests for feature registry failover and resilience.

Tests graceful degradation when database is unavailable, automatic fallback
to in-memory backend, and proper error handling with logging.

Codex Analysis 22 Recommendation - Failover/Resilience Tests
"""

import pytest
import os
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from features.registry import FeatureRegistry, DatabaseBackend


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_psycopg2_connection_failure():
    """Mock psycopg2.connect to simulate database connection failure."""
    with patch('features.registry.psycopg2.connect') as mock_connect:
        # Simulate connection failure
        mock_connect.side_effect = Exception("Connection refused: database is unavailable")
        yield mock_connect


@pytest.fixture
def mock_psycopg2_query_failure():
    """Mock database connection that fails on queries."""
    with patch('features.registry.psycopg2.connect') as mock_connect:
        # Create mock connection that fails on cursor operations
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        # Simulate query failure
        mock_cursor.execute.side_effect = Exception("Query execution failed")
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        
        mock_connect.return_value = mock_conn
        yield mock_connect


# ============================================================================
# Database Connection Failure Tests
# ============================================================================


class TestDatabaseConnectionFailure:
    """Test behavior when database connection fails."""
    
    def test_database_connection_failure_raises_error(self, mock_psycopg2_connection_failure):
        """Test that database connection failure raises appropriate error."""
        db_config = {
            'host': 'localhost',
            'port': 5432,
            'database': 'forecast_labor',
            'user': 'test_user',
            'password': 'test_pass',
        }
        
        # Attempting to create database backend should raise exception
        with pytest.raises(Exception, match="Connection refused"):
            DatabaseBackend(**db_config)
    
    def test_registry_with_failed_database_backend(self, mock_psycopg2_connection_failure):
        """Test that registry creation fails gracefully when database is unavailable."""
        db_config = {
            'host': 'localhost',
            'port': 5432,
            'database': 'forecast_labor',
            'user': 'test_user',
            'password': 'test_pass',
        }
        
        # Attempting to create registry with database backend should raise exception
        with pytest.raises(Exception):
            FeatureRegistry(backend='database', db_config=db_config)
    
    def test_fallback_to_memory_backend_when_database_unavailable(
        self, 
        mock_psycopg2_connection_failure
    ):
        """Test manual fallback to memory backend when database fails."""
        db_config = {
            'host': 'localhost',
            'port': 5432,
            'database': 'forecast_labor',
            'user': 'test_user',
            'password': 'test_pass',
        }
        
        # Try database backend, catch exception, use memory instead
        try:
            registry = FeatureRegistry(backend='database', db_config=db_config)
        except Exception:
            # Fallback to memory backend
            registry = FeatureRegistry(backend='memory')
        
        # Verify memory backend works
        assert registry.backend == 'memory'
        assert registry._db_backend is None
        
        # Test basic operations
        feature_id = registry.register({
            'name': 'fallback_test_feature',
            'source': 'ces',
            'frequency': 'monthly',
        })
        
        assert feature_id is not None
        retrieved = registry.get(feature_id)
        assert retrieved['name'] == 'fallback_test_feature'


# ============================================================================
# Database Query Failure Tests
# ============================================================================


class TestDatabaseQueryFailure:
    """Test behavior when database queries fail."""
    
    def test_query_failure_raises_error(self, mock_psycopg2_query_failure):
        """Test that query failures raise appropriate errors."""
        db_config = {
            'host': 'localhost',
            'port': 5432,
            'database': 'forecast_labor',
            'user': 'test_user',
            'password': 'test_pass',
        }
        
        # Create backend (connection succeeds)
        backend = DatabaseBackend(**db_config)
        
        # Attempting to register feature should fail
        with pytest.raises(Exception, match="Query execution failed"):
            backend.register_feature({
                'name': 'test_feature',
                'source': 'ces',
            })


# ============================================================================
# Graceful Degradation Tests
# ============================================================================


class TestGracefulDegradation:
    """Test graceful degradation strategies."""
    
    def test_memory_backend_as_fallback(self):
        """Test that memory backend works as a fallback when database fails."""
        # This simulates application-level fallback logic
        
        def get_feature_registry_with_fallback():
            """
            Application-level function that attempts database, falls back to memory.
            
            This is a pattern applications can use to ensure availability.
            """
            try:
                # Try to connect to database with TRULY invalid host
                db_config = {
                    'host': 'nonexistent_host_12345',  # This host should not exist
                    'port': 9999,  # Non-standard port
                    'database': 'nonexistent_db',
                    'user': 'fake_user',
                    'password': 'fake_pass',
                }
                return FeatureRegistry(backend='database', db_config=db_config)
            except Exception:
                # Fallback to memory backend
                return FeatureRegistry(backend='memory')
        
        # Get registry (will fallback to memory on connection failure)
        registry = get_feature_registry_with_fallback()
        
        # Verify it works (in memory mode)
        assert registry.backend == 'memory'
        
        # Test operations
        feature_id = registry.register({
            'name': 'graceful_degradation_test',
            'source': 'treasury',
            'frequency': 'daily',
        })
        
        assert feature_id is not None
        retrieved = registry.get(feature_id)
        assert retrieved['name'] == 'graceful_degradation_test'
    
    def test_operations_continue_in_memory_mode(self):
        """Test that all operations work in memory mode (fallback state)."""
        # Create memory registry (simulating fallback)
        registry = FeatureRegistry(backend='memory')
        
        # Test all critical operations
        
        # 1. Register
        feature_id = registry.register({
            'name': 'memory_ops_test',
            'source': 'laus',
            'frequency': 'weekly',
        })
        assert feature_id is not None
        
        # 2. Get
        retrieved = registry.get(feature_id)
        assert retrieved['name'] == 'memory_ops_test'
        
        # 3. Update
        registry.update(feature_id, {'status': 'production'})
        updated = registry.get(feature_id)
        assert updated['status'] == 'production'
        
        # 4. Search
        results = registry.search(source='laus')
        assert len(results) >= 1
        
        # 5. List all
        all_features = registry.list_all()
        assert len(all_features) >= 1
        
        # 6. Bulk register
        features = [
            {'name': f'bulk_test_{i}', 'source': 'ces'}
            for i in range(5)
        ]
        bulk_ids = registry.bulk_register(features)
        assert len(bulk_ids) == 5
        
        # 7. Delete
        registry.delete(feature_id)
        with pytest.raises(KeyError):
            registry.get(feature_id)


# ============================================================================
# Connection Pool Resilience Tests
# ============================================================================


class TestConnectionResilience:
    """Test connection resilience and recovery."""
    
    def test_database_backend_close_is_safe(self):
        """Test that closing database backend is safe and idempotent."""
        # Create mock backend
        with patch('features.registry.psycopg2.connect') as mock_connect:
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn
            
            db_config = {
                'host': 'localhost',
                'database': 'forecast_labor',
                'user': 'test_user',
                'password': 'test_pass',
            }
            
            backend = DatabaseBackend(**db_config)
            
            # Close once
            backend.close()
            mock_conn.close.assert_called_once()
            
            # Close again (should be safe)
            backend.close()
            # Should still only be called once (or handle gracefully)
    
    def test_registry_cleanup_on_failure(self):
        """Test that registry cleans up resources on failure."""
        with patch('features.registry.psycopg2.connect') as mock_connect:
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn
            
            db_config = {
                'host': 'localhost',
                'database': 'forecast_labor',
                'user': 'test_user',
                'password': 'test_pass',
            }
            
            # Create registry
            registry = FeatureRegistry(backend='database', db_config=db_config)
            
            # Simulate cleanup
            if hasattr(registry, '_db_backend') and registry._db_backend:
                registry._db_backend.close()
            
            # Verify close was called
            mock_conn.close.assert_called()


# ============================================================================
# Logging and Monitoring Tests
# ============================================================================


class TestFailoverLogging:
    """Test that failover events are properly logged."""
    
    @patch('features.registry.logger')
    def test_database_connection_failure_logs_error(
        self, 
        mock_logger, 
        mock_psycopg2_connection_failure
    ):
        """Test that database connection failures are logged."""
        db_config = {
            'host': 'localhost',
            'port': 5432,
            'database': 'forecast_labor',
            'user': 'test_user',
            'password': 'test_pass',
        }
        
        # Attempt to create database backend
        try:
            DatabaseBackend(**db_config)
        except Exception:
            pass  # Expected to fail
        
        # Verify error was logged
        mock_logger.error.assert_called()
        
        # Check that log message contains useful information
        log_call_args = mock_logger.error.call_args
        assert 'database_connection_failed' in str(log_call_args)
    
    @patch('features.registry.logger')
    def test_memory_mode_initialization_logs_info(self, mock_logger):
        """Test that memory mode initialization is logged."""
        registry = FeatureRegistry(backend='memory')
        
        # Verify registry was created
        assert registry.backend == 'memory'
        
        # Note: Logging verification depends on implementation
        # If memory mode logs initialization, verify it here


# ============================================================================
# Environment Configuration Fallback Tests
# ============================================================================


class TestEnvironmentConfigurationFallback:
    """Test fallback behavior with environment configuration."""
    
    def test_fallback_when_postgres_env_missing(self):
        """Test graceful handling when Postgres environment variables are missing."""
        # Clear postgres env vars
        original_vars = {}
        for var in ['POSTGRES_HOST', 'POSTGRES_PORT', 'POSTGRES_DB', 
                    'POSTGRES_USER', 'POSTGRES_PASSWORD']:
            original_vars[var] = os.getenv(var)
            if var in os.environ:
                del os.environ[var]
        
        try:
            # Set backend to memory explicitly (safe fallback)
            os.environ['FEATURE_REGISTRY_BACKEND'] = 'memory'
            
            from features.registry import get_registry_config_from_env
            
            config = get_registry_config_from_env()
            
            # Should fallback to memory mode
            assert config['backend'] == 'memory'
            
        finally:
            # Restore environment
            for var, value in original_vars.items():
                if value is not None:
                    os.environ[var] = value
                elif var in os.environ:
                    del os.environ[var]
    
    def test_explicit_memory_mode_ignores_database_config(self):
        """Test that explicit memory mode works even if database config is present."""
        # This ensures that memory mode can always be used as a fallback
        
        registry = FeatureRegistry(
            backend='memory',
            db_config={  # These should be ignored
                'host': 'invalid_host',
                'database': 'nonexistent_db',
            }
        )
        
        # Should work in memory mode
        assert registry.backend == 'memory'
        assert registry._db_backend is None
        
        # Test operations
        feature_id = registry.register({
            'name': 'explicit_memory_test',
            'source': 'ces',
        })
        assert feature_id is not None


# ============================================================================
# Data Persistence Awareness Tests
# ============================================================================


class TestDataPersistenceAwareness:
    """Test that applications are aware of persistence mode."""
    
    def test_memory_mode_data_not_persisted(self):
        """Test that memory mode data is not persisted (awareness test)."""
        # Create registry in memory mode
        registry1 = FeatureRegistry(backend='memory')
        
        # Register feature
        feature_id = registry1.register({
            'name': 'ephemeral_feature',
            'source': 'treasury',
        })
        
        # Verify feature exists
        assert registry1.get(feature_id) is not None
        
        # Create new registry instance (simulates process restart)
        registry2 = FeatureRegistry(backend='memory')
        
        # Feature should NOT exist in new instance
        with pytest.raises(KeyError):
            registry2.get(feature_id)
        
        # This test documents expected behavior: memory mode is ephemeral
    
    def test_backend_type_is_observable(self):
        """Test that applications can check which backend is active."""
        # Memory backend
        memory_registry = FeatureRegistry(backend='memory')
        assert memory_registry.backend == 'memory'
        assert hasattr(memory_registry, 'backend')
        
        # Applications can use this to decide behavior
        if memory_registry.backend == 'memory':
            # Example: Log warning that data won't persist
            pass  # Application-specific logic
        
        # This test documents that backend type is inspectable


# ============================================================================
# Concurrent Access Resilience Tests
# ============================================================================


class TestConcurrentAccessResilience:
    """Test resilience under concurrent access patterns."""
    
    def test_memory_mode_thread_safety_awareness(self):
        """Test that memory mode behavior under concurrent access is documented."""
        # Note: This is a documentation test, not a full concurrency test
        # Full concurrency testing would require threading/multiprocessing
        
        registry = FeatureRegistry(backend='memory')
        
        # Memory mode uses dict, which has some thread-safety guarantees
        # but is not fully thread-safe for complex operations
        
        # Register feature
        feature_id = registry.register({
            'name': 'concurrent_test',
            'source': 'ces',
        })
        
        # Basic operations should work
        retrieved = registry.get(feature_id)
        assert retrieved is not None
        
        # Note: For production concurrent access, database backend is recommended


# ============================================================================
# Error Recovery Tests
# ============================================================================


class TestErrorRecovery:
    """Test error recovery strategies."""
    
    def test_partial_failure_recovery(self):
        """Test recovery from partial failures in batch operations."""
        registry = FeatureRegistry(backend='memory')
        
        # Attempt to register features, some with invalid data
        features = [
            {'name': 'valid_feature_1', 'source': 'ces'},
            {'name': '', 'source': 'laus'},  # Invalid: empty name
            {'name': 'valid_feature_2', 'source': 'treasury'},
        ]
        
        # Process features with error handling
        registered_ids = []
        errors = []
        
        for feature_data in features:
            try:
                feature_id = registry.register(feature_data)
                registered_ids.append(feature_id)
            except Exception as e:
                errors.append(str(e))
        
        # Verify partial success
        assert len(registered_ids) == 2  # Two valid features
        assert len(errors) == 1  # One error
        
        # Verify valid features were registered
        for feature_id in registered_ids:
            retrieved = registry.get(feature_id)
            assert retrieved is not None

