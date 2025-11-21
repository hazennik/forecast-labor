"""
Integration test for Feature Registry with real PostgreSQL database.

Tests the complete feature registry workflow using an actual Postgres container,
not mocks. This ensures the database backend works in practice.

NOTE: Requires PostgreSQL service to be running (docker compose up postgres)
"""

import pytest
import os
from pathlib import Path
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from features.registry import FeatureRegistry, get_registry_config_from_env


@pytest.fixture(scope="module")
def postgres_available():
    """Check if PostgreSQL is available before running integration tests."""
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
        pytest.skip(f"PostgreSQL not available: {e}")


@pytest.fixture
def db_registry(postgres_available):
    """Create a database-backed feature registry for testing."""
    # Force database backend via direct config (not environment)
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
        test_features = registry.search(name='test_integration_feature')
        for feature in test_features:
            if 'feature_id' in feature:
                registry._db_backend.delete_feature(feature['feature_id'])
    except:
        pass  # Best effort cleanup


class TestPostgresIntegration:
    """Integration tests with real PostgreSQL database."""
    
    def test_database_connection(self, db_registry):
        """Test that database connection is established."""
        assert db_registry.backend == 'database'
        assert db_registry._db_backend is not None
        assert db_registry._db_backend.conn is not None
    
    def test_register_and_retrieve_feature(self, db_registry):
        """Test full workflow: register → retrieve → verify."""
        # Register a test feature
        feature_data = {
            'name': 'test_integration_feature_001',
            'source': 'integration_test',
            'frequency': 'monthly',
            'vintage_date': '2024-01-15',
            'description': 'Test feature for integration testing',
        }
        
        feature_id = db_registry.register(feature_data)
        
        # Verify feature was registered
        assert feature_id is not None
        assert isinstance(feature_id, str)
        
        # Retrieve the feature
        retrieved = db_registry.get(feature_id)
        
        # Verify retrieved data matches
        assert retrieved['name'] == feature_data['name']
        assert retrieved['source'] == feature_data['source']
        assert retrieved['frequency'] == feature_data['frequency']
        assert retrieved['vintage_date'] == feature_data['vintage_date']
    
    def test_search_features(self, db_registry):
        """Test searching for features by metadata."""
        # Register multiple test features
        for i in range(3):
            db_registry.register({
                'name': f'test_integration_feature_{i:03d}',
                'source': 'integration_test',
                'frequency': 'daily' if i % 2 == 0 else 'weekly',
                'vintage_date': '2024-01-15',
            })
        
        # Search by source
        results = db_registry._db_backend.search_features(source='integration_test')
        assert len(results) >= 3
        
        # Search by frequency
        daily_results = db_registry._db_backend.search_features(frequency='daily')
        assert len(daily_results) >= 2
    
    def test_feature_lineage(self, db_registry):
        """Test lineage tracking in database."""
        # Register parent feature
        parent_data = {
            'name': 'test_parent_feature',
            'source': 'integration_test',
            'frequency': 'monthly',
            'vintage_date': '2024-01-15',
        }
        parent_id = db_registry.register(parent_data)
        
        # Register child feature with lineage
        child_data = {
            'name': 'test_child_feature',
            'source': 'integration_test',
            'frequency': 'monthly',
            'vintage_date': '2024-01-15',
            'parent_features': [parent_id],
            'transformations': [{'type': 'lag', 'params': {'n_lags': 5}}],
        }
        child_id = db_registry.register(child_data)
        
        # Verify lineage is tracked
        child_retrieved = db_registry.get(child_id)
        assert 'parent_features' in child_retrieved or 'transformations' in child_retrieved
    
    def test_environment_configuration(self, postgres_available):
        """Test that registry uses environment variables correctly."""
        # Set environment to use database
        original_backend = os.getenv('FEATURE_REGISTRY_BACKEND')
        
        try:
            os.environ['FEATURE_REGISTRY_BACKEND'] = 'database'
            
            # Get config from environment
            config = get_registry_config_from_env()
            
            assert config['backend'] == 'database'
            assert 'db_config' in config
            assert config['db_config']['database'] == 'forecast_labor'
            
            # Create registry using environment config
            registry = FeatureRegistry(**config)
            assert registry.backend == 'database'
            
        finally:
            # Restore original environment
            if original_backend:
                os.environ['FEATURE_REGISTRY_BACKEND'] = original_backend
            else:
                os.environ.pop('FEATURE_REGISTRY_BACKEND', None)
    
    def test_backward_compatibility_memory_mode(self):
        """Test that memory mode still works (backward compatibility)."""
        # Create registry with memory backend (no postgres needed)
        registry = FeatureRegistry(backend='memory')
        
        assert registry.backend == 'memory'
        assert registry._db_backend is None
        
        # Register feature in memory
        feature_id = registry.register({
            'name': 'memory_test_feature',
            'source': 'test',
            'frequency': 'daily',
        })
        
        # Retrieve feature
        retrieved = registry.get(feature_id)
        assert retrieved['name'] == 'memory_test_feature'


class TestFeatureBuilderIntegration:
    """Test FeatureBuilder with database-backed registry."""
    
    def test_feature_builder_uses_env_config(self, postgres_available, tmp_path):
        """Test that FeatureBuilder respects FEATURE_REGISTRY_BACKEND environment variable."""
        from scripts.build_features import FeatureBuilder
        
        # Set environment to use database
        original_backend = os.getenv('FEATURE_REGISTRY_BACKEND')
        
        try:
            os.environ['FEATURE_REGISTRY_BACKEND'] = 'database'
            
            # Create FeatureBuilder
            builder = FeatureBuilder(
                vintage_date='2024-01-15',
                output_dir=tmp_path / 'features'
            )
            
            # Verify it uses database backend
            assert builder.registry.backend == 'database'
            assert builder.registry._db_backend is not None
            
        finally:
            # Restore original environment
            if original_backend:
                os.environ['FEATURE_REGISTRY_BACKEND'] = original_backend
            else:
                os.environ.pop('FEATURE_REGISTRY_BACKEND', None)


class TestModelIOIntegration:
    """Test model I/O with feature registry integration."""
    
    def test_save_model_with_feature_info(self, db_registry, tmp_path):
        """Test saving a model with feature registry information included."""
        from models_src.utils.io import save_model_with_metadata, ModelMetadata
        from datetime import datetime
        
        # Register some features in the database
        feature_names = []
        for i in range(3):
            feature_id = db_registry.register({
                'name': f'model_test_feature_{i}',
                'source': 'ces',
                'frequency': 'monthly',
                'vintage_date': '2024-01-15',
            })
            feature_names.append(f'model_test_feature_{i}')
        
        # Create mock model
        class MockModel:
            def __init__(self):
                self.coef_ = [1.0, 2.0, 3.0]
        
        model = MockModel()
        
        # Create metadata with feature names
        metadata = ModelMetadata(
            model_name='test_model',
            model_type='linear_regression',
            version='1.0.0',
            training_date=datetime.now().isoformat(),
            feature_names=feature_names,
            hyperparameters={'alpha': 0.1},
            metrics={'rmse': 0.5},
            vintage_date='2024-01-15',
        )
        
        # Set environment to use database registry
        original_backend = os.getenv('FEATURE_REGISTRY_BACKEND')
        try:
            os.environ['FEATURE_REGISTRY_BACKEND'] = 'database'
            
            # Save model with feature info
            artifact = save_model_with_metadata(
                model=model,
                metadata=metadata,
                output_dir=tmp_path,
                model_name='test_model',
                include_feature_info=True,
            )
            
            # Verify artifact was created
            assert artifact.model_path.exists()
            assert artifact.metadata_path.exists()
            
            # Read metadata file and verify feature info is included
            import json
            with open(artifact.metadata_path, 'r') as f:
                saved_metadata = json.load(f)
            
            assert 'feature_registry_info' in saved_metadata
            assert saved_metadata['feature_registry_info']['feature_count'] == 3
            assert saved_metadata['feature_registry_info']['registry_backend'] == 'database'
            
        finally:
            # Restore original environment
            if original_backend:
                os.environ['FEATURE_REGISTRY_BACKEND'] = original_backend
            else:
                os.environ.pop('FEATURE_REGISTRY_BACKEND', None)

