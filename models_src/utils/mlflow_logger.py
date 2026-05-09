"""
MLflow experiment tracking and model registry integration.

This module provides a clean interface for logging experiments, hyperparameters,
metrics, and artifacts to MLflow. It wraps MLflow functionality with error handling,
validation, and convenience methods for forecasting workflows.

Key features:
- Experiment tracking with automatic setup
- Hyperparameter and metric logging
- Artifact logging (models, plots, data)
- Model registry integration
- Feature metadata tracking
- Vintage date tracking for reproducibility
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from datetime import date
from contextlib import contextmanager
import tempfile

from loguru import logger

try:
    import mlflow
    import mlflow.sklearn
    import mlflow.pyfunc
    from mlflow import MlflowClient

    MLFLOW_AVAILABLE = True
except ImportError:
    MLFLOW_AVAILABLE = False
    logger.warning(
        "MLflow not available. Install with: pip install mlflow",
    )


# ============================================================================
# Configuration
# ============================================================================


@dataclass
class ExperimentConfig:
    """
    Configuration for MLflow experiment tracking.

    Attributes:
        experiment_name: Name of the MLflow experiment
        run_name: Name for this specific run
        tracking_uri: URI of the MLflow tracking server (optional)
        artifact_location: Location to store artifacts (optional)
        tags: Dictionary of tags to apply to the run
    """

    experiment_name: str
    run_name: str
    tracking_uri: Optional[str] = None
    artifact_location: Optional[str] = None
    tags: Dict[str, str] = field(default_factory=dict)


# ============================================================================
# MLflow Logger Class
# ============================================================================


class MLflowLogger:
    """
    Wrapper for MLflow experiment tracking and model registry.

    This class provides a clean interface for logging all aspects of
    model training and evaluation to MLflow, including hyperparameters,
    metrics, artifacts, and model registry integration.

    Examples:
        >>> config = ExperimentConfig(
        ...     experiment_name="nfp_forecasting",
        ...     run_name="dfm_2025_01_15",
        ...     tags={"model_type": "DFM"},
        ... )
        >>> logger = MLflowLogger(config)
        >>> with logger.start_run():
        ...     logger.log_hyperparameters({"learning_rate": 0.01})
        ...     logger.log_metrics({"rmse": 100.5})
    """

    def __init__(self, config: ExperimentConfig):
        """
        Initialize MLflow logger with configuration.

        Args:
            config: ExperimentConfig instance with experiment settings

        Raises:
            ImportError: If MLflow is not installed
        """
        if not MLFLOW_AVAILABLE:
            raise ImportError("MLflow is not installed. Install with: pip install mlflow")

        self.config = config
        self.experiment_name = config.experiment_name
        self.run_name = config.run_name
        self._active_run = None

        # Set tracking URI if provided
        if config.tracking_uri:
            mlflow.set_tracking_uri(config.tracking_uri)
            logger.info(
                "MLflow tracking URI set",
                tracking_uri=config.tracking_uri,
            )

    def setup_experiment(self) -> str:
        """
        Set up MLflow experiment, creating it if it doesn't exist.

        Returns:
            Experiment ID
        """
        experiment = mlflow.get_experiment_by_name(self.experiment_name)

        if experiment is None:
            # Create new experiment
            experiment_id = mlflow.create_experiment(
                name=self.experiment_name,
                artifact_location=self.config.artifact_location,
            )
            logger.info(
                "Created new MLflow experiment",
                experiment_name=self.experiment_name,
                experiment_id=experiment_id,
            )
        else:
            experiment_id = experiment.experiment_id
            logger.debug(
                "Using existing MLflow experiment",
                experiment_name=self.experiment_name,
                experiment_id=experiment_id,
            )

        mlflow.set_experiment(self.experiment_name)
        return experiment_id

    @contextmanager
    def start_run(self, nested: bool = False):
        """
        Start an MLflow run as a context manager.

        Args:
            nested: Whether to allow nested runs (default: False)

        Yields:
            Active MLflow run

        Examples:
            >>> with logger.start_run():
            ...     logger.log_metric("rmse", 100.5)
        """
        self.setup_experiment()

        try:
            with mlflow.start_run(run_name=self.run_name, nested=nested) as run:
                self._active_run = run

                # Set initial tags
                if self.config.tags:
                    mlflow.set_tags(self.config.tags)

                logger.info(
                    "Started MLflow run",
                    run_id=run.info.run_id,
                    experiment_name=self.experiment_name,
                    run_name=self.run_name,
                )

                yield run

        finally:
            self._active_run = None
            logger.debug("MLflow run ended")

    def get_run_id(self) -> Optional[str]:
        """
        Get the current run ID.

        Returns:
            Run ID if run is active, None otherwise
        """
        active_run = mlflow.active_run()
        if active_run:
            return active_run.info.run_id
        return None

    # ========================================================================
    # Hyperparameter Logging
    # ========================================================================

    def log_hyperparameter(self, key: str, value: Any) -> bool:
        """
        Log a single hyperparameter.

        Args:
            key: Parameter name
            value: Parameter value

        Returns:
            True if logged successfully, False otherwise
        """
        if not mlflow.active_run():
            logger.warning("No active MLflow run. Cannot log hyperparameter.")
            return False

        try:
            mlflow.log_param(key, value)
            logger.debug(f"Logged hyperparameter: {key}={value}")
            return True
        except Exception as e:
            logger.error(f"Failed to log hyperparameter {key}: {e}")
            return False

    def log_hyperparameters(
        self,
        params: Dict[str, Any],
        flatten: bool = False,
    ) -> bool:
        """
        Log multiple hyperparameters.

        Args:
            params: Dictionary of hyperparameters
            flatten: If True, flatten nested dictionaries with dot notation

        Returns:
            True if logged successfully, False otherwise

        Examples:
            >>> logger.log_hyperparameters({
            ...     "learning_rate": 0.01,
            ...     "max_depth": 5,
            ... })
        """
        if not mlflow.active_run():
            logger.warning("No active MLflow run. Cannot log hyperparameters.")
            return False

        try:
            if flatten:
                params = self._flatten_dict(params)

            mlflow.log_params(params)
            logger.debug(f"Logged {len(params)} hyperparameters")
            return True
        except Exception as e:
            logger.error(f"Failed to log hyperparameters: {e}")
            return False

    # ========================================================================
    # Metric Logging
    # ========================================================================

    def log_metric(self, key: str, value: float, step: Optional[int] = None) -> bool:
        """
        Log a single metric.

        Args:
            key: Metric name
            value: Metric value
            step: Optional step number (for training curves)

        Returns:
            True if logged successfully, False otherwise
        """
        if not mlflow.active_run():
            logger.warning("No active MLflow run. Cannot log metric.")
            return False

        try:
            mlflow.log_metric(key, value, step=step)
            logger.debug(f"Logged metric: {key}={value} (step={step})")
            return True
        except Exception as e:
            logger.error(f"Failed to log metric {key}: {e}")
            return False

    def log_metrics(
        self,
        metrics: Dict[str, float],
        step: Optional[int] = None,
    ) -> bool:
        """
        Log multiple metrics.

        Args:
            metrics: Dictionary of metrics
            step: Optional step number (for training curves)

        Returns:
            True if logged successfully, False otherwise

        Examples:
            >>> logger.log_metrics({
            ...     "rmse": 100.5,
            ...     "smape": 15.2,
            ... })
        """
        if not mlflow.active_run():
            logger.warning("No active MLflow run. Cannot log metrics.")
            return False

        try:
            mlflow.log_metrics(metrics, step=step)
            logger.debug(f"Logged {len(metrics)} metrics")
            return True
        except Exception as e:
            logger.error(f"Failed to log metrics: {e}")
            return False

    def log_metrics_by_split(
        self,
        metrics: Dict[str, Dict[str, float]],
        step: Optional[int] = None,
    ) -> bool:
        """
        Log metrics organized by data split (train/val/test).

        Args:
            metrics: Dictionary with split names as keys, metric dicts as values
            step: Optional step number

        Returns:
            True if all logged successfully, False otherwise

        Examples:
            >>> logger.log_metrics_by_split({
            ...     "train": {"rmse": 90.0, "smape": 12.0},
            ...     "val": {"rmse": 100.0, "smape": 15.0},
            ... })
        """
        if not mlflow.active_run():
            logger.warning("No active MLflow run. Cannot log metrics.")
            return False

        success = True
        for split_name, split_metrics in metrics.items():
            # Prefix metrics with split name
            prefixed_metrics = {
                f"{split_name}_{key}": value for key, value in split_metrics.items()
            }

            if not self.log_metrics(prefixed_metrics, step=step):
                success = False

        return success

    # ========================================================================
    # Artifact Logging
    # ========================================================================

    def log_artifact(self, local_path: Union[str, Path]) -> bool:
        """
        Log a single file as an artifact.

        Args:
            local_path: Path to the file to log

        Returns:
            True if logged successfully, False otherwise
        """
        if not mlflow.active_run():
            logger.warning("No active MLflow run. Cannot log artifact.")
            return False

        try:
            mlflow.log_artifact(str(local_path))
            logger.debug(f"Logged artifact: {local_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to log artifact {local_path}: {e}")
            return False

    def log_artifacts(
        self,
        local_dir: Union[str, Path],
        artifact_path: Optional[str] = None,
    ) -> bool:
        """
        Log a directory of artifacts.

        Args:
            local_dir: Path to the directory to log
            artifact_path: Optional path within the artifact store

        Returns:
            True if logged successfully, False otherwise
        """
        if not mlflow.active_run():
            logger.warning("No active MLflow run. Cannot log artifacts.")
            return False

        try:
            mlflow.log_artifacts(str(local_dir), artifact_path=artifact_path)
            logger.debug(f"Logged artifacts from: {local_dir}")
            return True
        except Exception as e:
            logger.error(f"Failed to log artifacts from {local_dir}: {e}")
            return False

    def log_figure(
        self,
        figure: Any,
        filename: str,
        artifact_path: Optional[str] = None,
    ) -> bool:
        """
        Log a matplotlib figure as an artifact.

        Args:
            figure: Matplotlib figure object
            filename: Name for the saved figure
            artifact_path: Optional path within the artifact store

        Returns:
            True if logged successfully, False otherwise
        """
        if not mlflow.active_run():
            logger.warning("No active MLflow run. Cannot log figure.")
            return False

        try:
            # Save figure to temporary file
            with tempfile.TemporaryDirectory() as tmpdir:
                filepath = Path(tmpdir) / filename
                figure.savefig(filepath, bbox_inches="tight", dpi=150)

                # Log the saved figure
                if artifact_path:
                    mlflow.log_artifact(str(filepath), artifact_path=artifact_path)
                else:
                    mlflow.log_artifact(str(filepath))

            logger.debug(f"Logged figure: {filename}")
            return True
        except Exception as e:
            logger.error(f"Failed to log figure {filename}: {e}")
            return False

    # ========================================================================
    # Model Registry
    # ========================================================================

    def log_model(
        self,
        model: Any,
        artifact_path: str = "model",
        registered_model_name: Optional[str] = None,
        **kwargs,
    ) -> bool:
        """
        Log a model to MLflow.

        Args:
            model: The model object to log
            artifact_path: Path within the run's artifact directory
            registered_model_name: If provided, register model with this name
            **kwargs: Additional arguments for mlflow.sklearn.log_model

        Returns:
            True if logged successfully, False otherwise
        """
        if not mlflow.active_run():
            logger.warning("No active MLflow run. Cannot log model.")
            return False

        try:
            # Try sklearn log_model first, fall back to pyfunc
            try:
                mlflow.sklearn.log_model(
                    model,
                    artifact_path=artifact_path,
                    registered_model_name=registered_model_name,
                    **kwargs,
                )
            except Exception:
                mlflow.pyfunc.log_model(
                    artifact_path=artifact_path,
                    python_model=model,
                    registered_model_name=registered_model_name,
                    **kwargs,
                )

            logger.info(
                "Logged model to MLflow",
                artifact_path=artifact_path,
                registered_model_name=registered_model_name,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to log model: {e}")
            return False

    def register_model(self, model_uri: str, name: str) -> bool:
        """
        Register a logged model in the model registry.

        Args:
            model_uri: URI of the model (e.g., "runs:/run-id/model")
            name: Name for the registered model

        Returns:
            True if registered successfully, False otherwise
        """
        try:
            mlflow.register_model(model_uri, name)
            logger.info(f"Registered model: {name} from {model_uri}")
            return True
        except Exception as e:
            logger.error(f"Failed to register model {name}: {e}")
            return False

    def transition_model_stage(
        self,
        name: str,
        version: int,
        stage: str,
    ) -> bool:
        """
        Transition a model version to a different stage.

        Args:
            name: Registered model name
            version: Model version number
            stage: Target stage ("Staging", "Production", "Archived")

        Returns:
            True if transitioned successfully, False otherwise
        """
        try:
            client = MlflowClient()
            client.transition_model_version_stage(
                name=name,
                version=version,
                stage=stage,
            )
            logger.info(f"Transitioned model {name} v{version} to {stage}")
            return True
        except Exception as e:
            logger.error(f"Failed to transition model stage: {e}")
            return False

    # ========================================================================
    # Feature Metadata
    # ========================================================================

    def log_feature_metadata(self, metadata: Dict[str, Any]) -> bool:
        """
        Log feature metadata as a JSON artifact.

        Args:
            metadata: Dictionary containing feature information

        Returns:
            True if logged successfully, False otherwise
        """
        if not mlflow.active_run():
            logger.warning("No active MLflow run. Cannot log feature metadata.")
            return False

        try:
            mlflow.log_dict(metadata, "feature_metadata.json")
            logger.debug("Logged feature metadata")
            return True
        except Exception as e:
            logger.error(f"Failed to log feature metadata: {e}")
            return False

    def log_features(self, features: List[str]) -> bool:
        """
        Log the list of features used.

        Args:
            features: List of feature names

        Returns:
            True if logged successfully, False otherwise
        """
        if not mlflow.active_run():
            logger.warning("No active MLflow run. Cannot log features.")
            return False

        try:
            # Log as a tag for easy searching
            mlflow.set_tag("features", ",".join(features))
            mlflow.set_tag("n_features", len(features))
            logger.debug(f"Logged {len(features)} features")
            return True
        except Exception as e:
            logger.error(f"Failed to log features: {e}")
            return False

    def log_vintage_date(self, vintage_date: date) -> bool:
        """
        Log the vintage date of training data.

        Args:
            vintage_date: Date of the data vintage

        Returns:
            True if logged successfully, False otherwise
        """
        if not mlflow.active_run():
            logger.warning("No active MLflow run. Cannot log vintage date.")
            return False

        try:
            mlflow.set_tag("vintage_date", vintage_date.isoformat())
            logger.debug(f"Logged vintage date: {vintage_date}")
            return True
        except Exception as e:
            logger.error(f"Failed to log vintage date: {e}")
            return False

    # ========================================================================
    # Helper Methods
    # ========================================================================

    @staticmethod
    def _flatten_dict(
        d: Dict[str, Any],
        parent_key: str = "",
        sep: str = ".",
    ) -> Dict[str, Any]:
        """
        Flatten a nested dictionary using dot notation.

        Args:
            d: Dictionary to flatten
            parent_key: Prefix for keys (used in recursion)
            sep: Separator for nested keys

        Returns:
            Flattened dictionary
        """
        items = []
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(MLflowLogger._flatten_dict(v, new_key, sep=sep).items())
            else:
                items.append((new_key, v))
        return dict(items)


# ============================================================================
# Standalone Functions
# ============================================================================


def log_hyperparameters(params: Dict[str, Any]) -> None:
    """
    Standalone function to log hyperparameters to active MLflow run.

    Args:
        params: Dictionary of hyperparameters
    """
    if not MLFLOW_AVAILABLE:
        logger.warning("MLflow not available")
        return

    if not mlflow.active_run():
        logger.warning("No active MLflow run")
        return

    mlflow.log_params(params)


def log_metrics(metrics: Dict[str, float], step: Optional[int] = None) -> None:
    """
    Standalone function to log metrics to active MLflow run.

    Args:
        metrics: Dictionary of metrics
        step: Optional step number
    """
    if not MLFLOW_AVAILABLE:
        logger.warning("MLflow not available")
        return

    if not mlflow.active_run():
        logger.warning("No active MLflow run")
        return

    mlflow.log_metrics(metrics, step=step)


def log_artifact(local_path: Union[str, Path]) -> None:
    """
    Standalone function to log an artifact to active MLflow run.

    Args:
        local_path: Path to the file to log
    """
    if not MLFLOW_AVAILABLE:
        logger.warning("MLflow not available")
        return

    if not mlflow.active_run():
        logger.warning("No active MLflow run")
        return

    mlflow.log_artifact(str(local_path))


def log_model_to_registry(
    model: Any,
    model_name: str,
    artifact_path: str = "model",
) -> None:
    """
    Standalone function to log a model to the registry.

    Args:
        model: The model object to log
        model_name: Name for the registered model
        artifact_path: Path within the run's artifact directory
    """
    if not MLFLOW_AVAILABLE:
        logger.warning("MLflow not available")
        return

    if not mlflow.active_run():
        logger.warning("No active MLflow run")
        return

    try:
        mlflow.sklearn.log_model(
            model,
            artifact_path=artifact_path,
            registered_model_name=model_name,
        )
    except Exception:
        mlflow.pyfunc.log_model(
            artifact_path=artifact_path,
            python_model=model,
            registered_model_name=model_name,
        )
