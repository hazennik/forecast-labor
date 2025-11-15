"""
Feature registry for metadata tracking and versioning.

⚠️ IMPORTANT: Phase 4 implementation is IN-MEMORY ONLY
Features are NOT persisted across process restarts.
Database persistence is planned for Phase 5+.

Tracks:
- Feature names and descriptions
- Source data and transformations
- Versions and dependencies
- Vintage dates (for reproducibility)

Enables:
- Feature discovery (within session)
- Lineage tracking
- Version management
- Reproducibility validation

Storage:
- Phase 4: In-memory dictionary (current)
- Phase 5+: PostgreSQL database (planned)
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime
import uuid
import json
from loguru import logger


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


class FeatureRegistry:
    """
    Registry for tracking feature metadata.
    
    ⚠️ IN-MEMORY ONLY: Features are not persisted across process restarts.
    
    Provides:
    - Feature registration and retrieval (in-memory)
    - Version management
    - Lineage tracking
    - Search and discovery
    - Database persistence (planned for Phase 5+, currently TODO)

    Storage:
    - Phase 4: In-memory dictionary (self._features)
    - Phase 5+: PostgreSQL database (to be implemented)
    
    Example:
        >>> registry = FeatureRegistry()
        >>> feature_id = registry.register({
        ...     'name': 'treasury_lag_0',
        ...     'source': 'treasury',
        ...     'frequency': 'daily',
        ...     'transform': 'midas_lag'
        ... })
        >>> metadata = registry.get(feature_id)
        >>> # NOTE: metadata is lost when process ends
    """

    def __init__(self, use_database: bool = False):
        """
        Initialize feature registry.

        Args:
            use_database: If True, persist to PostgreSQL database
        """
        self.use_database = use_database
        self._features: Dict[str, FeatureMetadata] = {}

        logger.info("feature_registry_initialized", use_database=use_database)

    def register(self, feature_data: Dict[str, Any]) -> str:
        """
        Register a new feature.

        Args:
            feature_data: Feature metadata dictionary

        Returns:
            Unique feature ID

        Example:
            >>> feature_id = registry.register({
            ...     'name': 'test_feature',
            ...     'source': 'ces',
            ...     'frequency': 'monthly'
            ... })
        """
        # Create metadata object
        metadata = FeatureMetadata(**feature_data)

        # Generate unique ID
        feature_id = str(uuid.uuid4())

        # Store in memory
        self._features[feature_id] = metadata

        # Optionally persist to database
        if self.use_database:
            self._persist_to_database(feature_id, metadata)

        logger.info(
            "feature_registered",
            feature_id=feature_id,
            feature_name=metadata.name,
            version=metadata.version,
        )

        return feature_id

    def get(self, feature_id: str) -> Dict[str, Any]:
        """
        Get feature metadata by ID.

        Args:
            feature_id: Feature ID

        Returns:
            Feature metadata dictionary

        Raises:
            KeyError: If feature ID not found
        """
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
        Update feature metadata.

        Args:
            feature_id: Feature ID
            updates: Dictionary of fields to update

        Raises:
            KeyError: If feature ID not found
        """
        if feature_id not in self._features:
            raise KeyError(f"Feature ID not found: {feature_id}")

        metadata = self._features[feature_id]

        # Update fields
        for key, value in updates.items():
            if hasattr(metadata, key):
                setattr(metadata, key, value)

        # Update timestamp
        metadata.updated_at = datetime.now().isoformat()

        # Persist if using database
        if self.use_database:
            self._persist_to_database(feature_id, metadata)

        logger.info("feature_updated", feature_id=feature_id, updated_fields=list(updates.keys()))

    def delete(self, feature_id: str) -> None:
        """
        Delete a feature from registry.

        Args:
            feature_id: Feature ID

        Raises:
            KeyError: If feature ID not found
        """
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

    def _persist_to_database(self, feature_id: str, metadata: FeatureMetadata) -> None:
        """
        Persist feature to database.

        Args:
            feature_id: Feature ID
            metadata: Feature metadata

        Note:
            Database persistence is planned for future implementation.
            For now, features are stored in-memory only.
            Database integration will be added in Phase 5+ when model infrastructure is complete.
        """
        # TODO: Implement database persistence in Phase 5+
        # Will require:
        # 1. Database connection pool
        # 2. features.feature_registry table schema
        # 3. SQL INSERT/UPDATE logic
        
        logger.debug(
            "database_persistence_not_yet_implemented",
            feature_id=feature_id,
            note="Planned for Phase 5+ - features stored in-memory for now"
        )


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

