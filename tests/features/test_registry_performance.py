"""
Tests for feature registry query performance.

Tests query speed, batch operations, index effectiveness, and performance
regression detection for the feature registry database backend.

Phase 5.2.3 - Query Performance Tests
"""

import pytest
import os
import time
from typing import List, Dict, Any
from pathlib import Path
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from features.registry import FeatureRegistry, FeatureMetadata


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture(scope="module")
def postgres_available():
    """Check if PostgreSQL is available before running performance tests."""
    import psycopg2
    
    try:
        conn = psycopg2.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', '5432')),
            database=os.getenv('POSTGRES_DB', 'forecast_labor'),
            user=os.getenv('POSTGRES_USER', 'forecast_labor'),
            password=os.getenv('POSTGRES_PASSWORD', 'forecast_labor'),
        )
        conn.close()
        return True
    except Exception as e:
        pytest.skip(f"PostgreSQL not available for performance tests: {e}")


@pytest.fixture
def perf_registry(postgres_available):
    """Create a database-backed feature registry for performance testing."""
    db_config = {
        'host': os.getenv('POSTGRES_HOST', 'localhost'),
        'port': int(os.getenv('POSTGRES_PORT', '5432')),
        'database': os.getenv('POSTGRES_DB', 'forecast_labor'),
        'user': os.getenv('POSTGRES_USER', 'forecast_labor'),
        'password': os.getenv('POSTGRES_PASSWORD', 'forecast_labor'),
    }
    
    registry = FeatureRegistry(backend='database', db_config=db_config)
    
    yield registry
    
    # Cleanup: Delete test features
    try:
        test_features = registry.search(name='perf_test_feature')
        for feature in test_features:
            if 'feature_id' in feature:
                registry._db_backend.delete_feature(feature['feature_id'])
    except:
        pass  # Best effort cleanup


@pytest.fixture
def large_feature_set(perf_registry):
    """Create a large set of test features for performance testing."""
    feature_ids = []
    
    # Register 100 features with varied metadata
    for i in range(100):
        feature_data = {
            'name': f'perf_test_feature_{i:04d}',
            'source': ['ces', 'laus', 'treasury', 'claims'][i % 4],
            'frequency': ['daily', 'weekly', 'monthly'][i % 3],
            'vintage_date': f'2024-{(i % 12) + 1:02d}-15',
            'version': f'{(i // 50) + 1}.0.0',
            'description': f'Performance test feature {i}' * 10,  # ~300 chars
            'metadata': {
                'importance': i / 100.0,
                'category': f'category_{i % 10}',
                'tags': [f'tag_{j}' for j in range(i % 5)],
            },
        }
        
        feature_id = perf_registry.register(feature_data)
        feature_ids.append(feature_id)
    
    yield feature_ids
    
    # Cleanup
    for feature_id in feature_ids:
        try:
            perf_registry.delete(feature_id)
        except:
            pass


# ============================================================================
# Query Performance Tests
# ============================================================================


class TestQueryPerformance:
    """Test query performance for feature registry database operations."""
    
    def test_single_feature_retrieval_speed(self, perf_registry, large_feature_set):
        """Test that single feature retrieval is fast (< 100ms)."""
        # Select a feature from the middle
        feature_id = large_feature_set[50]
        
        # Measure query time
        start_time = time.time()
        feature = perf_registry.get(feature_id)
        query_time = time.time() - start_time
        
        # Assertions
        assert feature is not None
        assert query_time < 0.1, f"Query took {query_time:.3f}s (expected < 0.1s)"
    
    def test_batch_retrieval_performance(self, perf_registry, large_feature_set):
        """Test that batch retrieval is efficient (< 500ms for 50 features)."""
        # Select 50 features
        batch_ids = large_feature_set[:50]
        
        # Measure batch retrieval time
        start_time = time.time()
        features = []
        for feature_id in batch_ids:
            features.append(perf_registry.get(feature_id))
        batch_time = time.time() - start_time
        
        # Assertions
        assert len(features) == 50
        assert batch_time < 0.5, f"Batch retrieval took {batch_time:.3f}s (expected < 0.5s)"
        
        # Calculate average query time
        avg_time = batch_time / 50
        assert avg_time < 0.01, f"Average query time {avg_time:.3f}s (expected < 0.01s)"
    
    def test_search_by_source_performance(self, perf_registry, large_feature_set):
        """Test that search by source is fast (< 200ms)."""
        # Search for 'ces' features (should be ~25 out of 100)
        start_time = time.time()
        results = perf_registry.search(source='ces')
        search_time = time.time() - start_time
        
        # Assertions
        assert len(results) >= 25
        assert search_time < 0.2, f"Search took {search_time:.3f}s (expected < 0.2s)"
    
    def test_search_by_frequency_performance(self, perf_registry, large_feature_set):
        """Test that search by frequency is fast (< 200ms)."""
        # Search for 'monthly' features (should be ~33 out of 100)
        start_time = time.time()
        results = perf_registry.search(frequency='monthly')
        search_time = time.time() - start_time
        
        # Assertions
        assert len(results) >= 33
        assert search_time < 0.2, f"Search took {search_time:.3f}s (expected < 0.2s)"
    
    def test_search_by_vintage_date_performance(self, perf_registry, large_feature_set):
        """Test that search by vintage date is fast (< 200ms)."""
        # Search for specific vintage date
        start_time = time.time()
        results = perf_registry.search(vintage_date='2024-06-15')
        search_time = time.time() - start_time
        
        # Assertions
        assert len(results) >= 8  # Should have ~8-9 features with this date
        assert search_time < 0.2, f"Search took {search_time:.3f}s (expected < 0.2s)"
    
    def test_list_all_features_performance(self, perf_registry, large_feature_set):
        """Test that listing all features is reasonable (< 500ms for 100+ features)."""
        start_time = time.time()
        all_features = perf_registry.list_all()  # List all features
        list_time = time.time() - start_time
        
        # Assertions (may have features from other tests, so >= 100 is valid)
        assert len(all_features) >= 100
        assert list_time < 0.5, f"List all took {list_time:.3f}s (expected < 0.5s)"
    
    def test_get_versions_performance(self, perf_registry):
        """Test that getting feature versions is fast (< 100ms)."""
        # Register 5 versions of the same feature (with unique vintage dates to avoid constraint violation)
        import time as time_module
        feature_name = f'perf_test_versioned_feature_{int(time_module.time() * 1000)}'
        version_ids = []
        
        for i in range(5):
            feature_data = {
                'name': feature_name,
                'version': f'{i+1}.0.0',
                'source': 'ces',
                'frequency': 'monthly',
                'vintage_date': f'2024-{(i % 12) + 1:02d}-15',  # Different vintage dates
            }
            version_id = perf_registry.register(feature_data)
            version_ids.append(version_id)
        
        try:
            # Measure version query time
            start_time = time.time()
            versions = perf_registry.get_versions(feature_name)
            query_time = time.time() - start_time
            
            # Assertions
            assert len(versions) >= 5
            assert query_time < 0.1, f"Get versions took {query_time:.3f}s (expected < 0.1s)"
        
        finally:
            # Cleanup
            for version_id in version_ids:
                try:
                    perf_registry.delete(version_id)
                except:
                    pass
    
    def test_get_latest_version_performance(self, perf_registry):
        """Test that getting latest version is fast (< 100ms)."""
        # Register 5 versions (with unique vintage dates to avoid constraint violation)
        import time as time_module
        feature_name = f'perf_test_latest_feature_{int(time_module.time() * 1000)}'
        version_ids = []
        
        for i in range(5):
            feature_data = {
                'name': feature_name,
                'version': f'{i+1}.0.0',
                'source': 'laus',
                'frequency': 'weekly',
                'vintage_date': f'2024-{(i % 12) + 1:02d}-15',  # Different vintage dates
            }
            version_id = perf_registry.register(feature_data)
            version_ids.append(version_id)
        
        try:
            # Measure latest version query time
            start_time = time.time()
            latest = perf_registry.get_latest(feature_name)
            query_time = time.time() - start_time
            
            # Assertions
            assert latest is not None
            assert latest['version'] == '5.0.0'
            assert query_time < 0.1, f"Get latest took {query_time:.3f}s (expected < 0.1s)"
        
        finally:
            # Cleanup
            for version_id in version_ids:
                try:
                    perf_registry.delete(version_id)
                except:
                    pass


# ============================================================================
# Batch Operations Performance Tests
# ============================================================================


class TestBatchOperationsPerformance:
    """Test performance of batch operations."""
    
    def test_bulk_register_performance(self, perf_registry):
        """Test that bulk registration is efficient (< 2s for 100 features)."""
        # Prepare 100 features for bulk registration
        features = []
        for i in range(100):
            features.append({
                'name': f'perf_bulk_test_feature_{i:04d}',
                'source': 'treasury',
                'frequency': 'daily',
                'vintage_date': '2024-03-15',
                'version': '1.0.0',
            })
        
        # Measure bulk registration time
        start_time = time.time()
        feature_ids = perf_registry.bulk_register(features)
        bulk_time = time.time() - start_time
        
        try:
            # Assertions
            assert len(feature_ids) == 100
            assert bulk_time < 2.0, f"Bulk register took {bulk_time:.3f}s (expected < 2.0s)"
            
            # Calculate average registration time
            avg_time = bulk_time / 100
            assert avg_time < 0.02, f"Average registration time {avg_time:.3f}s (expected < 0.02s)"
        
        finally:
            # Cleanup
            for feature_id in feature_ids:
                try:
                    perf_registry.delete(feature_id)
                except:
                    pass
    
    def test_bulk_update_performance(self, perf_registry, large_feature_set):
        """Test that bulk updates are efficient (< 1s for 50 updates)."""
        # Select 50 features to update
        update_ids = large_feature_set[:50]
        
        # Measure bulk update time
        start_time = time.time()
        for feature_id in update_ids:
            perf_registry._db_backend.update_feature(feature_id, {'description': 'Updated for performance test'})
        bulk_update_time = time.time() - start_time
        
        # Assertions
        assert bulk_update_time < 1.0, f"Bulk update took {bulk_update_time:.3f}s (expected < 1.0s)"
        
        # Verify updates were applied
        updated_feature = perf_registry.get(update_ids[0])
        assert updated_feature['description'] == 'Updated for performance test'


# ============================================================================
# Lineage Query Performance Tests
# ============================================================================


class TestLineagePerformance:
    """Test performance of lineage tracking queries."""
    
    def test_lineage_query_performance(self, perf_registry):
        """Test that lineage queries are fast (< 200ms)."""
        # Create a lineage chain: parent -> child1 -> grandchild
        parent_data = {
            'name': 'perf_test_parent',
            'source': 'ces',
            'frequency': 'monthly',
            'vintage_date': '2024-04-15',
        }
        parent_id = perf_registry.register(parent_data)
        
        child_data = {
            'name': 'perf_test_child',
            'source': 'ces',
            'frequency': 'monthly',
            'vintage_date': '2024-04-15',
            'depends_on': [parent_id],
        }
        child_id = perf_registry.register(child_data)
        
        grandchild_data = {
            'name': 'perf_test_grandchild',
            'source': 'ces',
            'frequency': 'monthly',
            'vintage_date': '2024-04-15',
            'depends_on': [child_id],
        }
        grandchild_id = perf_registry.register(grandchild_data)
        
        try:
            # Measure lineage query time
            start_time = time.time()
            lineage = perf_registry.get_lineage(grandchild_id)
            query_time = time.time() - start_time
            
            # Assertions (lineage returns list of feature IDs)
            assert parent_id in lineage
            assert child_id in lineage
            assert query_time < 0.2, f"Lineage query took {query_time:.3f}s (expected < 0.2s)"
        
        finally:
            # Cleanup (in reverse order)
            for feature_id in [grandchild_id, child_id, parent_id]:
                try:
                    perf_registry.delete(feature_id)
                except:
                    pass


# ============================================================================
# Memory Mode Performance Baseline Tests
# ============================================================================


class TestMemoryModePerformance:
    """Test performance of in-memory registry (baseline comparison)."""
    
    def test_memory_mode_registration_speed(self):
        """Test that memory mode registration is very fast (< 10ms for 100 features)."""
        registry = FeatureRegistry(backend='memory')
        
        features = [
            {'name': f'memory_test_feature_{i}', 'source': 'ces'}
            for i in range(100)
        ]
        
        start_time = time.time()
        feature_ids = registry.bulk_register(features)
        bulk_time = time.time() - start_time
        
        assert len(feature_ids) == 100
        assert bulk_time < 0.01, f"Memory bulk register took {bulk_time:.3f}s (expected < 0.01s)"
    
    def test_memory_mode_retrieval_speed(self):
        """Test that memory mode retrieval is very fast (< 1ms per feature)."""
        registry = FeatureRegistry(backend='memory')
        
        # Register 100 features
        features = [
            {'name': f'memory_test_feature_{i}', 'source': 'laus'}
            for i in range(100)
        ]
        feature_ids = registry.bulk_register(features)
        
        # Measure retrieval time
        start_time = time.time()
        for feature_id in feature_ids:
            registry.get(feature_id)
        retrieval_time = time.time() - start_time
        
        avg_time = retrieval_time / 100
        assert avg_time < 0.001, f"Average memory retrieval time {avg_time:.3f}s (expected < 0.001s)"


# ============================================================================
# Performance Regression Detection Tests
# ============================================================================


class TestPerformanceRegression:
    """Test for performance regressions over time."""
    
    def test_query_time_consistency(self, perf_registry, large_feature_set):
        """Test that query times are consistent across multiple runs."""
        feature_id = large_feature_set[50]
        
        query_times = []
        for _ in range(10):
            start_time = time.time()
            perf_registry.get(feature_id)
            query_time = time.time() - start_time
            query_times.append(query_time)
        
        # Calculate statistics
        avg_time = sum(query_times) / len(query_times)
        max_time = max(query_times)
        min_time = min(query_times)
        
        # Assertions: max time should not be > 10x min time (reasonable variance)
        # Note: For very fast queries (< 1ms), variance can be relatively high
        if min_time > 0.001:  # Only check variance if queries are > 1ms
            assert max_time < min_time * 10, (
                f"Query time variance too high: min={min_time:.4f}s, max={max_time:.4f}s"
            )
        assert avg_time < 0.1, f"Average query time {avg_time:.3f}s (expected < 0.1s)"
    
    def test_search_performance_with_growing_dataset(self, perf_registry):
        """Test that search performance degrades gracefully as dataset grows."""
        # This test validates that indexes are working properly
        # Search time should not grow linearly with dataset size
        
        feature_ids = []
        search_times = []
        
        # Test search performance at 50, 100, 150, 200 features
        for batch_size in [50, 50, 50, 50]:
            # Add features
            for i in range(batch_size):
                feature_data = {
                    'name': f'perf_scaling_test_feature_{len(feature_ids):04d}',
                    'source': 'scaling_test',
                    'frequency': 'monthly',
                    'vintage_date': '2024-05-15',
                }
                feature_id = perf_registry.register(feature_data)
                feature_ids.append(feature_id)
            
            # Measure search time
            start_time = time.time()
            results = perf_registry.search(source='scaling_test')
            search_time = time.time() - start_time
            search_times.append(search_time)
        
        try:
            # Assertions: search time should not grow linearly
            # With proper indexes, 4x data should not take 4x time
            assert len(search_times) == 4
            assert search_times[-1] < search_times[0] * 2, (
                f"Search time grew too much: {search_times[0]:.4f}s -> {search_times[-1]:.4f}s"
            )
        
        finally:
            # Cleanup
            for feature_id in feature_ids:
                try:
                    perf_registry.delete(feature_id)
                except:
                    pass

