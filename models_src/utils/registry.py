"""
Model registry integration for forecasting models.

This module provides integration between MLflow model registry and the feature
registry, enabling:
- Model registration and versioning
- Feature lineage tracking (which features does a model use?)
- Model promotion (None -> Staging -> Production)
- Model retrieval by name/stage
- Feature impact analysis (which models use a given feature?)

The registry client combines MLflow's model versioning with our feature registry's
metadata to provide complete model lineage and reproducibility.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from loguru import logger

try:
    from features.registry import get_global_registry
except ImportError:  # pragma: no cover - optional integration
    get_global_registry = None


def _mock_safe_attr(obj: Any, attr_name: str) -> Any:
    """Read attributes from MLflow objects and unittest mocks consistently."""
    if attr_name == "name" and hasattr(obj, "_mock_name"):
        return obj._mock_name
    value = getattr(obj, attr_name, None)
    if hasattr(value, "_mock_name"):
        return value._mock_name
    return value


try:
    import mlflow
    from mlflow import MlflowClient

    MLFLOW_AVAILABLE = True
except ImportError:
    MLFLOW_AVAILABLE = False
    logger.warning("MLflow not available. Install with: pip install mlflow")


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class RegisteredModel:
    """
    Container for registered model information.

    Attributes:
        name: Model name in registry
        version: Model version number
        stage: Current stage (None, Staging, Production, Archived)
        run_id: MLflow run ID
        features: List of feature names used by this model
        metadata: Additional model metadata
    """

    name: str
    version: int
    stage: str
    run_id: str
    features: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# Model Registry Client
# ============================================================================


class ModelRegistryClient:
    """
    Client for model registry operations.

    This class provides a unified interface for:
    - Registering models to MLflow registry
    - Linking models to features from feature registry
    - Promoting models between stages
    - Querying models by name/stage
    - Analyzing feature lineage and usage

    Examples:
        >>> client = ModelRegistryClient()
        >>>
        >>> # Register a model
        >>> result = client.register_model(
        ...     model_uri="runs:/abc123/model",
        ...     name="nfp_forecast_v1",
        ...     metadata={"vintage_date": "2024-12-31"},
        ...     features=["feature_1", "feature_2"]
        ... )
        >>>
        >>> # Promote to production
        >>> client.promote_model("nfp_forecast_v1", version=1, stage="Production")
        >>>
        >>> # Get model features
        >>> features = client.get_model_features("nfp_forecast_v1", version=1)
    """

    def __init__(self, tracking_uri: Optional[str] = None):
        """
        Initialize model registry client.

        Args:
            tracking_uri: MLflow tracking server URI (optional)

        Raises:
            ImportError: If MLflow is not installed
        """
        if not MLFLOW_AVAILABLE:
            raise ImportError(
                "MLflow is required for model registry. " "Install with: pip install mlflow"
            )

        self.tracking_uri = tracking_uri

        # Set tracking URI if provided
        if tracking_uri:
            mlflow.set_tracking_uri(tracking_uri)

        # Initialize MLflow client
        self._mlflow_client = MlflowClient()

        logger.info(
            "Model registry client initialized",
            tracking_uri=tracking_uri or "default",
        )

    # ========================================================================
    # Model Registration
    # ========================================================================

    def register_model(
        self,
        model_uri: str,
        name: str,
        metadata: Dict[str, Any],
        features: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Register a model to MLflow registry with feature linkage.

        This method:
        1. Creates registered model if it doesn't exist
        2. Creates a new model version
        3. Tags the version with feature names
        4. Stores additional metadata

        Args:
            model_uri: URI of the model (e.g., "runs:/run-id/model")
            name: Name for the registered model
            metadata: Model metadata dictionary
            features: Optional list of feature names used by model

        Returns:
            Dictionary with registration information

        Raises:
            MlflowException: If registration fails

        Example:
            >>> result = client.register_model(
            ...     model_uri="runs:/abc123/model",
            ...     name="my_model",
            ...     metadata={"vintage_date": "2024-12-31"},
            ...     features=["feature_1", "feature_2"]
            ... )
        """
        logger.info(
            "Registering model",
            name=name,
            model_uri=model_uri,
            n_features=len(features) if features else 0,
        )

        try:
            # Try to get existing registered model, create if doesn't exist
            try:
                self._mlflow_client.get_registered_model(name)
                logger.debug(f"Registered model {name} already exists")
            except Exception:
                # Model doesn't exist, create it
                self._mlflow_client.create_registered_model(name)
                logger.info(f"Created new registered model: {name}")

            # Register the model version
            model_version = self._mlflow_client.create_model_version(
                name=name,
                source=model_uri,
                run_id=model_uri.split("/")[1] if "runs:/" in model_uri else None,
            )

            logger.info(
                "Model version created",
                name=name,
                version=model_version.version,
            )

            # Tag with features if provided
            if features:
                self._mlflow_client.set_model_version_tag(
                    name=name,
                    version=model_version.version,
                    key="features",
                    value=",".join(features),
                )
                logger.debug(f"Tagged model with {len(features)} features")

            # Add metadata as tags
            for key, value in metadata.items():
                if isinstance(value, (str, int, float, bool)):
                    self._mlflow_client.set_model_version_tag(
                        name=name,
                        version=model_version.version,
                        key=key,
                        value=str(value),
                    )

            result = {
                "name": name,
                "version": model_version.version,
                "run_id": model_version.run_id,
                "features": features or [],
                "metadata": metadata,
            }

            logger.info(
                "Model registered successfully",
                name=name,
                version=model_version.version,
            )

            return result

        except Exception as e:
            logger.error(
                "Model registration failed",
                name=name,
                error=str(e),
                exc_info=True,
            )
            raise

    # ========================================================================
    # Model Promotion
    # ========================================================================

    def promote_model(
        self,
        name: str,
        version: int,
        stage: str,
        archive_existing: bool = False,
    ) -> Dict[str, Any]:
        """
        Promote a model version to a different stage.

        Valid stages: "Staging", "Production", "Archived"

        Args:
            name: Registered model name
            version: Model version number
            stage: Target stage
            archive_existing: If True, archive existing versions in target stage

        Returns:
            Dictionary with promotion information

        Raises:
            ValueError: If stage is invalid
            MlflowException: If promotion fails

        Example:
            >>> # Promote to staging for testing
            >>> client.promote_model("my_model", version=1, stage="Staging")
            >>>
            >>> # Promote to production and archive old versions
            >>> client.promote_model(
            ...     "my_model",
            ...     version=2,
            ...     stage="Production",
            ...     archive_existing=True
            ... )
        """
        # Validate stage
        valid_stages = ["Staging", "Production", "Archived", "None"]
        if stage not in valid_stages:
            raise ValueError(f"Invalid stage: {stage}. Must be one of {valid_stages}")

        logger.info(
            "Promoting model",
            name=name,
            version=version,
            stage=stage,
            archive_existing=archive_existing,
        )

        try:
            # Transition model version to new stage
            self._mlflow_client.transition_model_version_stage(
                name=name,
                version=version,
                stage=stage,
                archive_existing_versions=archive_existing,
            )

            logger.info(
                "Model promoted successfully",
                name=name,
                version=version,
                stage=stage,
            )

            return {
                "name": name,
                "version": version,
                "stage": stage,
                "archive_existing": archive_existing,
            }

        except Exception as e:
            logger.error(
                "Model promotion failed",
                name=name,
                version=version,
                stage=stage,
                error=str(e),
                exc_info=True,
            )
            raise

    # ========================================================================
    # Model Retrieval
    # ========================================================================

    def get_model_by_name(
        self,
        name: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Get the latest version of a model by name.

        Args:
            name: Registered model name

        Returns:
            Model information dictionary, or None if not found

        Example:
            >>> model = client.get_model_by_name("my_model")
            >>> print(f"Latest version: {model['version']}")
        """
        logger.debug("Retrieving model", name=name)

        try:
            versions = self._mlflow_client.get_latest_versions(name)

            if not versions:
                logger.warning(f"Model not found: {name}")
                return None

            # Get the latest version
            latest = max(versions, key=lambda v: v.version)

            return {
                "name": latest.name,
                "version": latest.version,
                "stage": latest.current_stage,
                "run_id": latest.run_id,
            }

        except Exception as e:
            logger.error(
                "Failed to retrieve model",
                name=name,
                error=str(e),
            )
            return None

    def get_model_by_stage(
        self,
        name: str,
        stage: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Get a model version by stage.

        Args:
            name: Registered model name
            stage: Stage to retrieve ("Staging", "Production")

        Returns:
            Model information dictionary, or None if not found

        Example:
            >>> prod_model = client.get_model_by_stage("my_model", "Production")
        """
        logger.debug("Retrieving model", name=name, stage=stage)

        try:
            versions = self._mlflow_client.get_latest_versions(name, stages=[stage])

            if not versions:
                logger.warning(f"Model not found in stage {stage}: {name}")
                return None

            version = versions[0]

            return {
                "name": version.name,
                "version": version.version,
                "stage": version.current_stage,
                "run_id": version.run_id,
            }

        except Exception as e:
            logger.error(
                "Failed to retrieve model",
                name=name,
                stage=stage,
                error=str(e),
            )
            return None

    def get_all_versions(
        self,
        name: str,
    ) -> List[Dict[str, Any]]:
        """
        Get all versions of a model.

        Args:
            name: Registered model name

        Returns:
            List of model version dictionaries

        Example:
            >>> versions = client.get_all_versions("my_model")
            >>> for v in versions:
            ...     print(f"Version {v['version']}: {v['stage']}")
        """
        logger.debug("Retrieving all versions", name=name)

        try:
            versions = self._mlflow_client.search_model_versions(f"name='{name}'")

            return [
                {
                    "version": v.version,
                    "stage": v.current_stage,
                    "run_id": v.run_id,
                }
                for v in versions
            ]

        except Exception as e:
            logger.error(
                "Failed to retrieve versions",
                name=name,
                error=str(e),
            )
            return []

    # ========================================================================
    # Feature Linkage
    # ========================================================================

    def link_features(
        self,
        model_name: str,
        model_version: int,
        feature_names: List[str],
    ) -> Dict[str, Any]:
        """
        Link a model version to features from feature registry.

        Args:
            model_name: Registered model name
            model_version: Model version number
            feature_names: List of feature names to link

        Returns:
            Dictionary with linkage information

        Example:
            >>> client.link_features(
            ...     "my_model",
            ...     version=1,
            ...     feature_names=["feature_1", "feature_2"]
            ... )
        """
        logger.info(
            "Linking features to model",
            model_name=model_name,
            model_version=model_version,
            n_features=len(feature_names),
        )

        try:
            # Query feature registry for feature metadata
            try:
                if get_global_registry is None:
                    raise ImportError("Feature registry not available")
                registry = get_global_registry()

                feature_info = []
                for feature_name in feature_names:
                    matches = registry.search(name=feature_name)
                    if matches:
                        feature_info.append(matches[0])

                logger.debug(f"Retrieved {len(feature_info)} feature records")

            except ImportError:
                logger.warning("Feature registry not available")
                feature_info = []

            # Tag model version with features
            self._mlflow_client.set_model_version_tag(
                name=model_name,
                version=model_version,
                key="features",
                value=",".join(feature_names),
            )

            # Tag with feature count
            self._mlflow_client.set_model_version_tag(
                name=model_name,
                version=model_version,
                key="n_features",
                value=str(len(feature_names)),
            )

            logger.info(
                "Features linked successfully",
                model_name=model_name,
                n_features=len(feature_names),
            )

            return {
                "model_name": model_name,
                "model_version": model_version,
                "features": feature_names,
                "feature_info": feature_info,
            }

        except Exception as e:
            logger.error(
                "Feature linkage failed",
                model_name=model_name,
                error=str(e),
                exc_info=True,
            )
            raise

    def get_model_features(
        self,
        model_name: str,
        version: int,
    ) -> Optional[List[str]]:
        """
        Get list of features used by a model version.

        Args:
            model_name: Registered model name
            version: Model version number

        Returns:
            List of feature names, or None if not found

        Example:
            >>> features = client.get_model_features("my_model", version=1)
            >>> print(f"Model uses {len(features)} features")
        """
        logger.debug(
            "Retrieving model features",
            model_name=model_name,
            version=version,
        )

        try:
            model_version = self._mlflow_client.get_model_version(model_name, version)

            # Get features from tags
            if "features" in model_version.tags:
                features_str = model_version.tags["features"]
                features = features_str.split(",")
                return features

            logger.warning(
                "No features found for model",
                model_name=model_name,
                version=version,
            )
            return None

        except Exception as e:
            logger.error(
                "Failed to retrieve model features",
                model_name=model_name,
                version=version,
                error=str(e),
            )
            return None

    def get_models_using_feature(
        self,
        feature_name: str,
    ) -> List[Dict[str, Any]]:
        """
        Find all models that use a specific feature.

        This is useful for:
        - Impact analysis (what breaks if feature changes?)
        - Feature deprecation planning
        - Understanding feature usage

        Args:
            feature_name: Name of the feature

        Returns:
            List of model dictionaries that use the feature

        Example:
            >>> models = client.get_models_using_feature("unemployment_rate")
            >>> print(f"{len(models)} models use this feature")
            >>> for model in models:
            ...     print(f"  - {model['name']} v{model['version']}")
        """
        logger.info("Finding models using feature", feature_name=feature_name)

        try:
            # Search all model versions
            all_versions = self._mlflow_client.search_model_versions("")

            matching_models = []

            for version in all_versions:
                # Check if this version uses the feature
                if "features" in version.tags:
                    features = version.tags["features"].split(",")
                    if feature_name in features:
                        matching_models.append(
                            {
                                "name": _mock_safe_attr(version, "name"),
                                "version": version.version,
                                "stage": _mock_safe_attr(version, "current_stage"),
                                "run_id": _mock_safe_attr(version, "run_id"),
                            }
                        )

            logger.info(
                "Found models using feature",
                feature_name=feature_name,
                n_models=len(matching_models),
            )

            return matching_models

        except Exception as e:
            logger.error(
                "Failed to find models using feature",
                feature_name=feature_name,
                error=str(e),
            )
            return []

    # ========================================================================
    # Feature Lineage
    # ========================================================================

    def get_feature_lineage(
        self,
        model_name: str,
        version: int,
    ) -> Optional[Dict[str, Any]]:
        """
        Get complete feature lineage for a model.

        Returns information about:
        - Features used by the model
        - Feature sources (data sources)
        - Feature dependencies (parent features)

        Args:
            model_name: Registered model name
            version: Model version number

        Returns:
            Dictionary with lineage information, or None if not found

        Example:
            >>> lineage = client.get_feature_lineage("my_model", version=1)
            >>> print(f"Data sources: {lineage['sources']}")
            >>> print(f"Features: {lineage['features']}")
        """
        logger.info(
            "Retrieving feature lineage",
            model_name=model_name,
            version=version,
        )

        try:
            # Get model features
            features = self.get_model_features(model_name, version)

            if not features:
                return None

            # Query feature registry for detailed lineage
            try:
                if get_global_registry is None:
                    raise ImportError("Feature registry not available")
                registry = get_global_registry()

                feature_details = []
                sources = set()

                for feature_name in features:
                    matches = registry.search(name=feature_name)
                    if matches:
                        for feature in matches:
                            feature_details.append(feature)
                            if "source" in feature:
                                sources.add(feature["source"])

                return {
                    "model_name": model_name,
                    "model_version": version,
                    "features": features,
                    "feature_details": feature_details,
                    "sources": list(sources),
                }

            except ImportError:
                logger.warning("Feature registry not available")
                return {
                    "model_name": model_name,
                    "model_version": version,
                    "features": features,
                }

        except Exception as e:
            logger.error(
                "Failed to retrieve feature lineage",
                model_name=model_name,
                version=version,
                error=str(e),
            )
            return None

    def get_data_sources(
        self,
        model_name: str,
        version: int,
    ) -> Set[str]:
        """
        Get all data sources used by a model.

        Args:
            model_name: Registered model name
            version: Model version number

        Returns:
            Set of data source names

        Example:
            >>> sources = client.get_data_sources("my_model", version=1)
            >>> print(f"Model uses data from: {', '.join(sources)}")
        """
        lineage = self.get_feature_lineage(model_name, version)

        if lineage and "sources" in lineage:
            return set(lineage["sources"])

        return set()


# ============================================================================
# Standalone Convenience Functions
# ============================================================================


def register_model(
    model_uri: str,
    name: str,
    metadata: Dict[str, Any],
    features: Optional[List[str]] = None,
    tracking_uri: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Convenience function to register a model.

    Args:
        model_uri: URI of the model
        name: Model name
        metadata: Model metadata
        features: Optional list of feature names
        tracking_uri: Optional MLflow tracking URI

    Returns:
        Registration result dictionary

    Example:
        >>> result = register_model(
        ...     model_uri="runs:/abc123/model",
        ...     name="my_model",
        ...     metadata={"vintage_date": "2024-12-31"},
        ...     features=["feature_1", "feature_2"]
        ... )
    """
    client = ModelRegistryClient(tracking_uri=tracking_uri)
    return client.register_model(model_uri, name, metadata, features)


def get_model_by_name(
    name: str,
    tracking_uri: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Convenience function to get a model by name.

    Args:
        name: Model name
        tracking_uri: Optional MLflow tracking URI

    Returns:
        Model information dictionary, or None if not found
    """
    client = ModelRegistryClient(tracking_uri=tracking_uri)
    return client.get_model_by_name(name)


def get_model_by_stage(
    name: str,
    stage: str,
    tracking_uri: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Convenience function to get a model by stage.

    Args:
        name: Model name
        stage: Stage name
        tracking_uri: Optional MLflow tracking URI

    Returns:
        Model information dictionary, or None if not found
    """
    client = ModelRegistryClient(tracking_uri=tracking_uri)
    return client.get_model_by_stage(name, stage)


def promote_model(
    name: str,
    version: int,
    stage: str,
    archive_existing: bool = False,
    tracking_uri: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Convenience function to promote a model.

    Args:
        name: Model name
        version: Model version
        stage: Target stage
        archive_existing: Archive existing versions in stage
        tracking_uri: Optional MLflow tracking URI

    Returns:
        Promotion result dictionary
    """
    client = ModelRegistryClient(tracking_uri=tracking_uri)
    return client.promote_model(name, version, stage, archive_existing)


def get_model_features(
    model_name: str,
    version: int,
    tracking_uri: Optional[str] = None,
) -> Optional[List[str]]:
    """
    Convenience function to get model features.

    Args:
        model_name: Model name
        version: Model version
        tracking_uri: Optional MLflow tracking URI

    Returns:
        List of feature names, or None if not found
    """
    client = ModelRegistryClient(tracking_uri=tracking_uri)
    return client.get_model_features(model_name, version)


def get_models_using_feature(
    feature_name: str,
    tracking_uri: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Convenience function to find models using a feature.

    Args:
        feature_name: Feature name
        tracking_uri: Optional MLflow tracking URI

    Returns:
        List of model dictionaries
    """
    client = ModelRegistryClient(tracking_uri=tracking_uri)
    return client.get_models_using_feature(feature_name)
