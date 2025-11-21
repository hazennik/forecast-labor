"""
Feature registry for metadata tracking and versioning.

Supports two backend modes:
- In-memory (default): Features stored in process memory (for testing/dev)
- Database: Features persisted to PostgreSQL (for production)

Tracks:
- Feature names and descriptions
- Source data and transformations
- Versions and dependencies
- Vintage dates (for reproducibility)
- Feature lineage (parent-child relationships)

Enables:
- Feature discovery
- Lineage tracking
- Version management and rollback
- Reproducibility validation
- Persistent storage (database mode)

Storage Options:
- backend='memory': In-memory dictionary (default, for testing)
- backend='database': PostgreSQL database (production)
"""

from typing import Dict, List, Optional, Any, Literal
from dataclasses import dataclass, field, asdict
from datetime import datetime, date
import uuid
import json
from loguru import logger

try:
    import psycopg2
    from psycopg2 import sql
    from psycopg2.extras import RealDictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False
    logger.warning("psycopg2 not available. Database backend will not work. Install with: pip install psycopg2-binary")


@dataclass
class FeatureMetadata:
    """
    Metadata for a single feature.

    Attributes:
        name: Feature name (e.g., 'treasury_withholdings_lag_0')
        source: Data source (e.g., 'treasury', 'ces', 'laus')
        frequency: Temporal frequency ('daily', 'weekly', 'monthly')
        transform: Transformation applied (e.g., 'midas_lag', 'standardize')
        version: Feature version (semantic versioning: '1.0.0')
        description: Human-readable description
        depends_on: List of feature IDs this feature depends on
        vintage_date: Vintage date used to compute feature
        created_at: Timestamp when feature was registered
        updated_at: Timestamp of last update
        status: Status ('draft', 'production', 'deprecated')
        metadata: Additional arbitrary metadata
    """

    name: str
    source: Optional[str] = None
    frequency: Optional[str] = None
    transform: Optional[str] = None
    version: str = "1.0.0"
    description: Optional[str] = None
    depends_on: List[str] = field(default_factory=list)
    vintage_date: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    status: str = "draft"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate and set timestamps."""
        if not self.name:
            raise ValueError("Feature name is required")

        if self.created_at is None:
            self.created_at = datetime.now().isoformat()

        if self.updated_at is None:
            self.updated_at = self.created_at

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FeatureMetadata":
        """Create from dictionary."""
        return cls(**data)


# ============================================================================
# Database Backend
# ============================================================================


class DatabaseBackend:
    """
    PostgreSQL backend for feature registry persistence.
    
    This class handles all database operations for the feature registry,
    including CRUD operations, lineage tracking, and versioning.
    
    Attributes:
        _conn: PostgreSQL connection
        _cursor: Database cursor for queries
    
    Examples:
        >>> backend = DatabaseBackend(
        ...     host="localhost",
        ...     database="forecast_labor",
        ...     user="app_user",
        ...     password="secret"
        ... )
        >>> feature_id = backend.register_feature({
        ...     "name": "test_feature",
        ...     "source": "bls_ces"
        ... })
    """
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "forecast_labor",
        user: str = "forecast_labor",
        password: str = "forecast_labor",
    ):
        """
        Initialize database backend with connection parameters.
        
        Args:
            host: Database host
            port: Database port
            database: Database name
            user: Database user
            password: Database password
        
        Raises:
            ImportError: If psycopg2 is not installed
            Exception: If database connection fails
        """
        if not PSYCOPG2_AVAILABLE:
            raise ImportError(
                "psycopg2 is required for database backend. "
                "Install with: pip install psycopg2-binary"
            )
        
        try:
            self._conn = psycopg2.connect(
                host=host,
                port=port,
                database=database,
                user=user,
                password=password,
            )
            self._conn.autocommit = False  # Use transactions
            
            logger.info(
                "database_backend_connected",
                host=host,
                database=database,
                user=user,
            )
        
        except Exception as e:
            logger.error(
                "database_connection_failed",
                host=host,
                database=database,
                error=str(e),
                exc_info=True,
            )
            raise
    
    def close(self) -> None:
        """Close database connection."""
        if hasattr(self, '_conn') and self._conn:
            self._conn.close()
            logger.info("database_connection_closed")
    
    def register_feature(self, feature_data: Dict[str, Any]) -> str:
        """
        Register a new feature to the database.
        
        Args:
            feature_data: Feature metadata dictionary
        
        Returns:
            Feature ID (UUID as string)
        """
        with self._conn.cursor() as cur:
            try:
                # Insert into feature_metadata
                insert_query = sql.SQL("""
                    INSERT INTO features.feature_metadata (
                        name, display_name, description, source, frequency,
                        vintage_date, data_type, unit, seasonal_adjustment,
                        current_version, status, is_synthetic, tags
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    RETURNING feature_id
                """)
                
                cur.execute(insert_query, (
                    feature_data.get('name'),
                    feature_data.get('display_name', feature_data.get('name')),
                    feature_data.get('description'),
                    feature_data.get('source'),
                    feature_data.get('frequency'),
                    feature_data.get('vintage_date'),
                    feature_data.get('data_type', 'float64'),
                    feature_data.get('unit'),
                    feature_data.get('seasonal_adjustment'),
                    1,  # current_version starts at 1
                    feature_data.get('status', 'active'),
                    feature_data.get('is_synthetic', False),
                    json.dumps(feature_data.get('metadata', {})),
                ))
                
                feature_id = cur.fetchone()[0]
                
                # Insert lineage if depends_on is provided
                depends_on = feature_data.get('depends_on', [])
                if depends_on:
                    for parent_id in depends_on:
                        lineage_query = sql.SQL("""
                            INSERT INTO features.feature_transforms (
                                feature_id, transform_type, transform_params, parent_feature_id
                            ) VALUES (%s, %s, %s, %s)
                        """)
                        cur.execute(lineage_query, (
                            feature_id,
                            feature_data.get('transform', 'custom'),
                            json.dumps(feature_data.get('transform_params', {})),
                            parent_id,
                        ))
                
                # Create initial version
                version_query = sql.SQL("""
                    INSERT INTO features.feature_versions (
                        feature_id, version, checksum, change_description
                    ) VALUES (%s, %s, %s, %s)
                """)
                cur.execute(version_query, (
                    feature_id,
                    1,
                    feature_data.get('checksum', ''),
                    'Initial version',
                ))
                
                self._conn.commit()
                
                logger.info(
                    "feature_registered_to_database",
                    feature_id=feature_id,
                    feature_name=feature_data.get('name'),
                )
                
                return str(feature_id)
            
            except Exception as e:
                self._conn.rollback()
                logger.error(
                    "feature_registration_failed",
                    feature_name=feature_data.get('name'),
                    error=str(e),
                    exc_info=True,
                )
                raise
    
    def get_feature(self, feature_id: str) -> Dict[str, Any]:
        """
        Get feature metadata by ID.
        
        Args:
            feature_id: Feature UUID
        
        Returns:
            Feature metadata dictionary
        
        Raises:
            KeyError: If feature not found
        """
        with self._conn.cursor(cursor_factory=RealDictCursor) as cur:
            query = sql.SQL("""
                SELECT * FROM features.feature_metadata
                WHERE feature_id = %s
            """)
            
            cur.execute(query, (feature_id,))
            row = cur.fetchone()
            
            if not row:
                raise KeyError(f"Feature ID not found: {feature_id}")
            
            # Convert to regular dict and handle types
            feature = dict(row)
            feature['feature_id'] = str(feature['feature_id'])
            if feature.get('vintage_date'):
                feature['vintage_date'] = feature['vintage_date'].isoformat()
            if feature.get('tags'):
                feature['tags'] = json.loads(feature['tags']) if isinstance(feature['tags'], str) else feature['tags']
            
            return feature
    
    def list_features(
        self,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        **filters,
    ) -> List[Dict[str, Any]]:
        """
        List features with optional filtering and pagination.
        
        Args:
            limit: Maximum number of results
            offset: Number of results to skip
            **filters: Field filters (e.g., source='bls_ces', status='active')
        
        Returns:
            List of feature dictionaries
        """
        with self._conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Build query with filters
            query_parts = ["SELECT * FROM features.feature_metadata"]
            params = []
            
            if filters:
                where_clauses = []
                for key, value in filters.items():
                    where_clauses.append(f"{key} = %s")
                    params.append(value)
                query_parts.append("WHERE " + " AND ".join(where_clauses))
            
            query_parts.append("ORDER BY created_at DESC")
            
            if limit:
                query_parts.append(f"LIMIT {limit}")
            if offset:
                query_parts.append(f"OFFSET {offset}")
            
            query = " ".join(query_parts)
            cur.execute(query, params)
            
            rows = cur.fetchall()
            features = []
            
            for row in rows:
                feature = dict(row)
                feature['feature_id'] = str(feature['feature_id'])
                if feature.get('vintage_date'):
                    feature['vintage_date'] = feature['vintage_date'].isoformat()
                if feature.get('tags'):
                    feature['tags'] = json.loads(feature['tags']) if isinstance(feature['tags'], str) else feature['tags']
                features.append(feature)
            
            return features
    
    def update_feature(self, feature_id: str, updates: Dict[str, Any]) -> None:
        """
        Update feature metadata.
        
        Args:
            feature_id: Feature UUID
            updates: Dictionary of fields to update
        """
        if not updates:
            return
        
        with self._conn.cursor() as cur:
            try:
                # Build UPDATE query
                set_clauses = []
                params = []
                
                for key, value in updates.items():
                    set_clauses.append(f"{key} = %s")
                    if key == 'tags' and isinstance(value, dict):
                        params.append(json.dumps(value))
                    else:
                        params.append(value)
                
                # Always update updated_at
                set_clauses.append("updated_at = NOW()")
                params.append(feature_id)
                
                query = sql.SQL(
                    f"UPDATE features.feature_metadata SET {', '.join(set_clauses)} WHERE feature_id = %s"
                )
                
                cur.execute(query, params)
                self._conn.commit()
                
                logger.info(
                    "feature_updated_in_database",
                    feature_id=feature_id,
                    updated_fields=list(updates.keys()),
                )
            
            except Exception as e:
                self._conn.rollback()
                logger.error(
                    "feature_update_failed",
                    feature_id=feature_id,
                    error=str(e),
                    exc_info=True,
                )
                raise
    
    def delete_feature(self, feature_id: str) -> None:
        """
        Delete a feature from the database.
        
        Args:
            feature_id: Feature UUID
        """
        with self._conn.cursor() as cur:
            try:
                query = sql.SQL("""
                    DELETE FROM features.feature_metadata
                    WHERE feature_id = %s
                """)
                
                cur.execute(query, (feature_id,))
                self._conn.commit()
                
                logger.info("feature_deleted_from_database", feature_id=feature_id)
            
            except Exception as e:
                self._conn.rollback()
                logger.error(
                    "feature_deletion_failed",
                    feature_id=feature_id,
                    error=str(e),
                    exc_info=True,
                )
                raise
    
    def get_lineage(self, feature_id: str) -> List[Dict[str, Any]]:
        """
        Get feature lineage using recursive query.
        
        Args:
            feature_id: Feature UUID
        
        Returns:
            List of lineage dictionaries with depth
        """
        with self._conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Use the database function
            query = sql.SQL("""
                SELECT * FROM features.get_feature_lineage(%s)
            """)
            
            cur.execute(query, (feature_id,))
            rows = cur.fetchall()
            
            lineage = []
            for row in rows:
                item = dict(row)
                item['feature_id'] = str(item['feature_id'])
                lineage.append(item)
            
            return lineage
    
    def get_descendants(self, feature_id: str) -> List[Dict[str, Any]]:
        """
        Get features derived from this feature.
        
        Args:
            feature_id: Feature UUID
        
        Returns:
            List of descendant feature dictionaries
        """
        with self._conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Use the database function
            query = sql.SQL("""
                SELECT * FROM features.get_feature_descendants(%s)
            """)
            
            cur.execute(query, (feature_id,))
            rows = cur.fetchall()
            
            descendants = []
            for row in rows:
                item = dict(row)
                item['feature_id'] = str(item['feature_id'])
                descendants.append(item)
            
            return descendants
    
    def create_version(
        self,
        feature_id: str,
        checksum: str,
        row_count: Optional[int] = None,
        change_description: Optional[str] = None,
    ) -> str:
        """
        Create a new version of a feature.
        
        Args:
            feature_id: Feature UUID
            checksum: SHA256 checksum of feature data
            row_count: Number of rows in feature data
            change_description: Description of changes
        
        Returns:
            Version ID
        """
        with self._conn.cursor() as cur:
            try:
                # Get current max version
                cur.execute("""
                    SELECT COALESCE(MAX(version), 0) + 1
                    FROM features.feature_versions
                    WHERE feature_id = %s
                """, (feature_id,))
                
                new_version = cur.fetchone()[0]
                
                # Insert new version
                query = sql.SQL("""
                    INSERT INTO features.feature_versions (
                        feature_id, version, checksum, row_count, change_description
                    ) VALUES (%s, %s, %s, %s, %s)
                    RETURNING version_id
                """)
                
                cur.execute(query, (
                    feature_id,
                    new_version,
                    checksum,
                    row_count,
                    change_description,
                ))
                
                version_id = cur.fetchone()[0]
                
                # Update current_version in metadata
                cur.execute("""
                    UPDATE features.feature_metadata
                    SET current_version = %s
                    WHERE feature_id = %s
                """, (new_version, feature_id))
                
                self._conn.commit()
                
                logger.info(
                    "feature_version_created",
                    feature_id=feature_id,
                    version=new_version,
                    version_id=version_id,
                )
                
                return str(version_id)
            
            except Exception as e:
                self._conn.rollback()
                logger.error(
                    "version_creation_failed",
                    feature_id=feature_id,
                    error=str(e),
                    exc_info=True,
                )
                raise
    
    def get_versions(self, feature_id: str) -> List[Dict[str, Any]]:
        """
        Get all versions of a feature.
        
        Args:
            feature_id: Feature UUID
        
        Returns:
            List of version dictionaries
        """
        with self._conn.cursor(cursor_factory=RealDictCursor) as cur:
            query = sql.SQL("""
                SELECT * FROM features.feature_versions
                WHERE feature_id = %s
                ORDER BY version DESC
            """)
            
            cur.execute(query, (feature_id,))
            rows = cur.fetchall()
            
            versions = []
            for row in rows:
                version = dict(row)
                version['version_id'] = str(version['version_id'])
                version['feature_id'] = str(version['feature_id'])
                versions.append(version)
            
            return versions


class FeatureRegistry:
    """
    Registry for tracking feature metadata with pluggable backend.
    
    Supports two backends:
    - 'memory': In-memory storage (default, for testing/dev)
    - 'database': PostgreSQL persistence (for production)
    
    Provides:
    - Feature registration and retrieval
    - Version management
    - Lineage tracking
    - Search and discovery
    - Persistent storage (database mode)

    Backend Storage:
    - backend='memory': In-memory dictionary (default)
    - backend='database': PostgreSQL database
    
    Examples:
        # In-memory (default, for testing)
        >>> registry = FeatureRegistry()
        >>> feature_id = registry.register({'name': 'test_feature'})
        
        # Database (for production)
        >>> registry = FeatureRegistry(
        ...     backend='database',
        ...     db_config={'host': 'localhost', 'database': 'forecast_labor'}
        ... )
        >>> feature_id = registry.register({'name': 'prod_feature'})
    """

    def __init__(
        self,
        backend: Literal['memory', 'database'] = 'memory',
        db_config: Optional[Dict[str, Any]] = None,
        use_database: bool = False,  # Deprecated, for backward compatibility
    ):
        """
        Initialize feature registry with specified backend.

        Args:
            backend: Storage backend ('memory' or 'database')
            db_config: Database configuration (required if backend='database')
            use_database: DEPRECATED. Use backend='database' instead.
        
        Raises:
            ValueError: If backend='database' but db_config not provided
            ImportError: If backend='database' but psycopg2 not installed
        """
        # Handle deprecated use_database parameter
        if use_database and backend == 'memory':
            backend = 'database'
            logger.warning(
                "use_database parameter is deprecated. Use backend='database' instead."
            )
        
        self.backend = backend
        self._features: Dict[str, FeatureMetadata] = {}
        self._db_backend: Optional[DatabaseBackend] = None
        
        # Initialize appropriate backend
        if backend == 'database':
            if not db_config:
                raise ValueError(
                    "db_config is required when backend='database'"
                )
            
            self._db_backend = DatabaseBackend(**db_config)
            logger.info(
                "feature_registry_initialized",
                backend="database",
                db_config={k: v for k, v in db_config.items() if k != 'password'},
            )
        else:
            logger.info("feature_registry_initialized", backend="memory")

    def register(self, feature_data: Dict[str, Any]) -> str:
        """
        Register a new feature using the configured backend.

        Args:
            feature_data: Feature metadata dictionary

        Returns:
            Unique feature ID

        Examples:
            >>> registry = FeatureRegistry()
            >>> feature_id = registry.register({
            ...     'name': 'test_feature',
            ...     'source': 'ces',
            ...     'frequency': 'monthly'
            ... })
        """
        if self.backend == 'database' and self._db_backend:
            # Use database backend
            return self._db_backend.register_feature(feature_data)
        else:
            # Use in-memory backend
            metadata = FeatureMetadata(**feature_data)
            feature_id = str(uuid.uuid4())
            self._features[feature_id] = metadata
            
            logger.info(
                "feature_registered",
                feature_id=feature_id,
                feature_name=metadata.name,
                version=metadata.version,
                backend="memory",
            )
            
            return feature_id

    def get(self, feature_id: str) -> Dict[str, Any]:
        """
        Get feature metadata by ID using the configured backend.

        Args:
            feature_id: Feature ID

        Returns:
            Feature metadata dictionary

        Raises:
            KeyError: If feature ID not found
        """
        if self.backend == 'database' and self._db_backend:
            return self._db_backend.get_feature(feature_id)
        else:
            if feature_id not in self._features:
                raise KeyError(f"Feature ID not found: {feature_id}")
            return self._features[feature_id].to_dict()

    def list_all(self) -> List[Dict[str, Any]]:
        """
        List all registered features.

        Returns:
            List of feature metadata dictionaries
        """
        return [metadata.to_dict() for metadata in self._features.values()]

    def search(self, **filters) -> List[Dict[str, Any]]:
        """
        Search features by metadata filters.

        Args:
            **filters: Metadata fields to filter on

        Returns:
            List of matching features

        Example:
            >>> ces_features = registry.search(source='ces')
            >>> daily_features = registry.search(frequency='daily')
        """
        results = []

        for feature_id, metadata in self._features.items():
            match = True

            for key, value in filters.items():
                if not hasattr(metadata, key) or getattr(metadata, key) != value:
                    match = False
                    break

            if match:
                result = metadata.to_dict()
                result["feature_id"] = feature_id
                results.append(result)

        logger.info("feature_search", filters=filters, result_count=len(results))

        return results

    def get_versions(self, feature_name: str) -> List[Dict[str, Any]]:
        """
        Get all versions of a feature.

        Args:
            feature_name: Feature name

        Returns:
            List of feature versions (sorted by version)
        """
        versions = []

        for feature_id, metadata in self._features.items():
            if metadata.name == feature_name:
                version_data = metadata.to_dict()
                version_data["feature_id"] = feature_id
                versions.append(version_data)

        # Sort by version (simple string sort works for semantic versioning)
        versions.sort(key=lambda x: x["version"])

        logger.info("feature_versions_retrieved", feature_name=feature_name, count=len(versions))

        return versions

    def get_latest(self, feature_name: str) -> Dict[str, Any]:
        """
        Get latest version of a feature.

        Args:
            feature_name: Feature name

        Returns:
            Latest version metadata

        Raises:
            KeyError: If feature name not found
        """
        versions = self.get_versions(feature_name)

        if not versions:
            raise KeyError(f"Feature not found: {feature_name}")

        return versions[-1]  # Last in sorted list = latest version

    def get_lineage(self, feature_id: str) -> List[str]:
        """
        Get feature lineage (dependencies).

        Args:
            feature_id: Feature ID

        Returns:
            List of feature IDs this feature depends on
        """
        if feature_id not in self._features:
            raise KeyError(f"Feature ID not found: {feature_id}")

        metadata = self._features[feature_id]

        logger.info(
            "feature_lineage_retrieved",
            feature_id=feature_id,
            dependencies=len(metadata.depends_on),
        )

        return metadata.depends_on

    def update(self, feature_id: str, updates: Dict[str, Any]) -> None:
        """
        Update feature metadata using the configured backend.

        Args:
            feature_id: Feature ID
            updates: Dictionary of fields to update

        Raises:
            KeyError: If feature ID not found
        """
        if self.backend == 'database' and self._db_backend:
            self._db_backend.update_feature(feature_id, updates)
        else:
            if feature_id not in self._features:
                raise KeyError(f"Feature ID not found: {feature_id}")

            metadata = self._features[feature_id]

            # Update fields
            for key, value in updates.items():
                if hasattr(metadata, key):
                    setattr(metadata, key, value)

            # Update timestamp
            metadata.updated_at = datetime.now().isoformat()

            logger.info("feature_updated", feature_id=feature_id, updated_fields=list(updates.keys()))

    def delete(self, feature_id: str) -> None:
        """
        Delete a feature from registry using the configured backend.

        Args:
            feature_id: Feature ID

        Raises:
            KeyError: If feature ID not found
        """
        if self.backend == 'database' and self._db_backend:
            self._db_backend.delete_feature(feature_id)
        else:
            if feature_id not in self._features:
                raise KeyError(f"Feature ID not found: {feature_id}")

            del self._features[feature_id]

            logger.info("feature_deleted", feature_id=feature_id)

    def bulk_register(self, features: List[Dict[str, Any]]) -> List[str]:
        """
        Register multiple features at once.

        Args:
            features: List of feature metadata dictionaries

        Returns:
            List of feature IDs
        """
        feature_ids = []

        for feature_data in features:
            feature_id = self.register(feature_data)
            feature_ids.append(feature_id)

        logger.info("bulk_registration_complete", feature_count=len(feature_ids))

        return feature_ids

    def export_to_dict(self) -> List[Dict[str, Any]]:
        """
        Export entire registry to dictionary.

        Returns:
            List of all features with IDs
        """
        exported = []

        for feature_id, metadata in self._features.items():
            feature_data = metadata.to_dict()
            feature_data["feature_id"] = feature_id
            exported.append(feature_data)

        logger.info("registry_exported", feature_count=len(exported))

        return exported

    def import_from_dict(self, features: List[Dict[str, Any]]) -> None:
        """
        Import features from dictionary.

        Args:
            features: List of feature metadata dictionaries
        """
        for feature_data in features:
            # Extract feature_id if present
            feature_id = feature_data.pop("feature_id", None)

            if feature_id is None:
                # Register new feature
                self.register(feature_data)
            else:
                # Import with specific ID
                metadata = FeatureMetadata(**feature_data)
                self._features[feature_id] = metadata

        logger.info("registry_imported", feature_count=len(features))



# Convenience function
def get_global_registry() -> FeatureRegistry:
    """
    Get global feature registry singleton.

    Returns:
        Global FeatureRegistry instance
    """
    global _GLOBAL_REGISTRY

    if "_GLOBAL_REGISTRY" not in globals():
        _GLOBAL_REGISTRY = FeatureRegistry()

    return _GLOBAL_REGISTRY

