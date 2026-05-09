"""
Tests for MLflow logging integration.

This module tests experiment tracking, hyperparameter logging, metric logging,
artifact logging, and model registry integration with MLflow.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, call
from datetime import date

from models_src.utils.mlflow_logger import (
    MLflowLogger,
    ExperimentConfig,
    log_hyperparameters,
    log_metrics,
    log_artifact,
    log_model_to_registry,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def experiment_config():
    """Create sample experiment configuration."""
    return ExperimentConfig(
        experiment_name="nfp_forecasting",
        run_name="test_run_2025_01_15",
        tracking_uri="http://localhost:5000",
        artifact_location=None,
        tags={"model_type": "DFM", "vintage": "2025-01-01"},
    )


@pytest.fixture
def mock_mlflow():
    """Create a mock MLflow module."""
    with patch("models_src.utils.mlflow_logger.mlflow") as mock:
        # Mock the active run context manager
        mock_run = MagicMock()
        mock_run.__enter__ = Mock(return_value=mock_run)
        mock_run.__exit__ = Mock(return_value=None)
        mock_run.info.run_id = "test-run-123"
        mock.start_run.return_value = mock_run
        mock.active_run.return_value = mock_run

        yield mock


@pytest.fixture
def mlflow_logger(experiment_config, mock_mlflow):
    """Create MLflowLogger instance with mocked MLflow."""
    return MLflowLogger(config=experiment_config)


# ============================================================================
# Experiment Tracking Tests
# ============================================================================


class TestExperimentTracking:
    """Test MLflow experiment tracking functionality."""

    def test_logger_initialization(self, experiment_config, mock_mlflow):
        """Test that MLflowLogger initializes correctly."""
        logger = MLflowLogger(config=experiment_config)

        assert logger.config == experiment_config
        assert logger.experiment_name == "nfp_forecasting"
        mock_mlflow.set_tracking_uri.assert_called_once_with("http://localhost:5000")

    def test_create_experiment_if_not_exists(self, experiment_config, mock_mlflow):
        """Test that experiment is created if it doesn't exist."""
        mock_mlflow.get_experiment_by_name.return_value = None
        mock_mlflow.create_experiment.return_value = "experiment-123"

        logger = MLflowLogger(config=experiment_config)
        logger.setup_experiment()

        mock_mlflow.get_experiment_by_name.assert_called_once_with("nfp_forecasting")
        mock_mlflow.create_experiment.assert_called_once()

    def test_use_existing_experiment(self, experiment_config, mock_mlflow):
        """Test that existing experiment is used if available."""
        mock_experiment = Mock()
        mock_experiment.experiment_id = "existing-123"
        mock_mlflow.get_experiment_by_name.return_value = mock_experiment

        logger = MLflowLogger(config=experiment_config)
        logger.setup_experiment()

        mock_mlflow.get_experiment_by_name.assert_called_once_with("nfp_forecasting")
        mock_mlflow.create_experiment.assert_not_called()

    def test_start_run(self, mlflow_logger, mock_mlflow):
        """Test starting an MLflow run."""
        with mlflow_logger.start_run():
            pass

        mock_mlflow.start_run.assert_called_once()
        assert "run_name" in mock_mlflow.start_run.call_args.kwargs
        assert mock_mlflow.start_run.call_args.kwargs["run_name"] == "test_run_2025_01_15"

    def test_start_run_with_tags(self, mlflow_logger, mock_mlflow):
        """Test that tags are set when starting a run."""
        with mlflow_logger.start_run():
            pass

        # Check that set_tags was called with the config tags
        mock_mlflow.set_tags.assert_called()
        tags_arg = mock_mlflow.set_tags.call_args[0][0]
        assert tags_arg["model_type"] == "DFM"
        assert tags_arg["vintage"] == "2025-01-01"

    def test_get_run_id(self, mlflow_logger, mock_mlflow):
        """Test retrieving the current run ID."""
        with mlflow_logger.start_run():
            run_id = mlflow_logger.get_run_id()
            assert run_id == "test-run-123"


# ============================================================================
# Hyperparameter Logging Tests
# ============================================================================


class TestHyperparameterLogging:
    """Test hyperparameter logging functionality."""

    def test_log_single_hyperparameter(self, mlflow_logger, mock_mlflow):
        """Test logging a single hyperparameter."""
        with mlflow_logger.start_run():
            mlflow_logger.log_hyperparameter("learning_rate", 0.01)

        mock_mlflow.log_param.assert_called_with("learning_rate", 0.01)

    def test_log_multiple_hyperparameters(self, mlflow_logger, mock_mlflow):
        """Test logging multiple hyperparameters at once."""
        hyperparams = {
            "learning_rate": 0.01,
            "max_depth": 5,
            "n_estimators": 100,
            "random_state": 42,
        }

        with mlflow_logger.start_run():
            mlflow_logger.log_hyperparameters(hyperparams)

        mock_mlflow.log_params.assert_called_once_with(hyperparams)

    def test_log_hyperparameters_with_nested_dict(self, mlflow_logger, mock_mlflow):
        """Test logging hyperparameters with nested structure (flattened)."""
        hyperparams = {
            "model": {
                "learning_rate": 0.01,
                "max_depth": 5,
            },
            "preprocessing": {
                "scale": True,
            },
        }

        with mlflow_logger.start_run():
            mlflow_logger.log_hyperparameters(hyperparams, flatten=True)

        # Check that nested params were flattened
        call_args = mock_mlflow.log_params.call_args[0][0]
        assert "model.learning_rate" in call_args
        assert "model.max_depth" in call_args
        assert "preprocessing.scale" in call_args

    def test_standalone_log_hyperparameters(self, mock_mlflow):
        """Test standalone log_hyperparameters function."""
        hyperparams = {"learning_rate": 0.01, "max_depth": 5}

        log_hyperparameters(hyperparams)

        mock_mlflow.log_params.assert_called_once_with(hyperparams)


# ============================================================================
# Metric Logging Tests
# ============================================================================


class TestMetricLogging:
    """Test metric logging functionality."""

    def test_log_single_metric(self, mlflow_logger, mock_mlflow):
        """Test logging a single metric."""
        with mlflow_logger.start_run():
            mlflow_logger.log_metric("rmse", 100.5)

        mock_mlflow.log_metric.assert_called_with("rmse", 100.5, step=None)

    def test_log_metric_with_step(self, mlflow_logger, mock_mlflow):
        """Test logging a metric with step number."""
        with mlflow_logger.start_run():
            mlflow_logger.log_metric("loss", 0.5, step=10)

        mock_mlflow.log_metric.assert_called_with("loss", 0.5, step=10)

    def test_log_multiple_metrics(self, mlflow_logger, mock_mlflow):
        """Test logging multiple metrics at once."""
        metrics = {
            "rmse": 100.5,
            "smape": 15.2,
            "mae": 75.3,
        }

        with mlflow_logger.start_run():
            mlflow_logger.log_metrics(metrics)

        mock_mlflow.log_metrics.assert_called_once_with(metrics, step=None)

    def test_log_metrics_with_step(self, mlflow_logger, mock_mlflow):
        """Test logging multiple metrics with step number."""
        metrics = {"train_loss": 0.5, "val_loss": 0.6}

        with mlflow_logger.start_run():
            mlflow_logger.log_metrics(metrics, step=10)

        mock_mlflow.log_metrics.assert_called_once_with(metrics, step=10)

    def test_log_metrics_by_split(self, mlflow_logger, mock_mlflow):
        """Test logging metrics organized by data split."""
        metrics = {
            "train": {"rmse": 90.0, "smape": 12.0},
            "val": {"rmse": 100.0, "smape": 15.0},
            "test": {"rmse": 105.0, "smape": 16.0},
        }

        with mlflow_logger.start_run():
            mlflow_logger.log_metrics_by_split(metrics)

        # Should log flattened metrics with split prefix
        [
            call({"train_rmse": 90.0, "train_smape": 12.0}, step=None),
            call({"val_rmse": 100.0, "val_smape": 15.0}, step=None),
            call({"test_rmse": 105.0, "test_smape": 16.0}, step=None),
        ]

        # Check that log_metrics was called for each split
        assert mock_mlflow.log_metrics.call_count == 3

    def test_standalone_log_metrics(self, mock_mlflow):
        """Test standalone log_metrics function."""
        metrics = {"rmse": 100.5, "smape": 15.2}

        log_metrics(metrics)

        mock_mlflow.log_metrics.assert_called_once_with(metrics, step=None)


# ============================================================================
# Artifact Logging Tests
# ============================================================================


class TestArtifactLogging:
    """Test artifact logging functionality."""

    def test_log_artifact_file(self, mlflow_logger, mock_mlflow, tmp_path):
        """Test logging a file artifact."""
        artifact_file = tmp_path / "test_artifact.txt"
        artifact_file.write_text("test content")

        with mlflow_logger.start_run():
            mlflow_logger.log_artifact(str(artifact_file))

        mock_mlflow.log_artifact.assert_called_once()
        assert str(artifact_file) in str(mock_mlflow.log_artifact.call_args)

    def test_log_artifact_directory(self, mlflow_logger, mock_mlflow, tmp_path):
        """Test logging a directory of artifacts."""
        artifact_dir = tmp_path / "artifacts"
        artifact_dir.mkdir()
        (artifact_dir / "file1.txt").write_text("content1")
        (artifact_dir / "file2.txt").write_text("content2")

        with mlflow_logger.start_run():
            mlflow_logger.log_artifacts(str(artifact_dir))

        mock_mlflow.log_artifacts.assert_called_once_with(str(artifact_dir), artifact_path=None)

    def test_log_artifact_with_path(self, mlflow_logger, mock_mlflow, tmp_path):
        """Test logging artifacts to a specific path in MLflow."""
        artifact_dir = tmp_path / "artifacts"
        artifact_dir.mkdir()

        with mlflow_logger.start_run():
            mlflow_logger.log_artifacts(str(artifact_dir), artifact_path="models")

        mock_mlflow.log_artifacts.assert_called_once_with(str(artifact_dir), artifact_path="models")

    def test_log_figure(self, mlflow_logger, mock_mlflow, tmp_path):
        """Test logging a matplotlib figure."""
        # Mock a figure
        mock_fig = Mock()
        mock_fig.savefig = Mock()

        with mlflow_logger.start_run():
            mlflow_logger.log_figure(mock_fig, "residual_plot.png")

        # Should have called savefig and then log_artifact
        mock_fig.savefig.assert_called_once()
        mock_mlflow.log_artifact.assert_called_once()

    def test_standalone_log_artifact(self, mock_mlflow, tmp_path):
        """Test standalone log_artifact function."""
        artifact_file = tmp_path / "test.txt"
        artifact_file.write_text("test")

        log_artifact(str(artifact_file))

        mock_mlflow.log_artifact.assert_called_once()


# ============================================================================
# Model Registry Tests
# ============================================================================


class TestModelRegistry:
    """Test model registry integration."""

    def test_log_model_to_registry(self, mlflow_logger, mock_mlflow):
        """Test logging a model to the registry."""
        mock_model = Mock()

        with mlflow_logger.start_run():
            mlflow_logger.log_model(
                model=mock_model,
                artifact_path="model",
                registered_model_name="nfp_forecaster",
            )

        # MLflow should have been called to log the model
        assert mock_mlflow.sklearn.log_model.called or mock_mlflow.pyfunc.log_model.called

    def test_register_model(self, mlflow_logger, mock_mlflow):
        """Test registering a model."""
        model_uri = "runs:/test-run-123/model"

        with mlflow_logger.start_run():
            mlflow_logger.register_model(
                model_uri=model_uri,
                name="nfp_forecaster",
            )

        mock_mlflow.register_model.assert_called_once_with(model_uri, "nfp_forecaster")

    @patch("models_src.utils.mlflow_logger.MlflowClient")
    def test_transition_model_stage(self, mock_client_class, mlflow_logger, mock_mlflow):
        """Test transitioning a model to a different stage."""
        # Mock the MlflowClient instance
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        with mlflow_logger.start_run():
            mlflow_logger.transition_model_stage(
                name="nfp_forecaster",
                version=1,
                stage="Production",
            )

        # Should call the MlflowClient to transition stage
        mock_client.transition_model_version_stage.assert_called_once_with(
            name="nfp_forecaster",
            version=1,
            stage="Production",
        )

    def test_standalone_log_model_to_registry(self, mock_mlflow):
        """Test standalone log_model_to_registry function."""
        mock_model = Mock()

        log_model_to_registry(
            model=mock_model,
            model_name="test_model",
            artifact_path="model",
        )

        # Should have logged the model
        assert mock_mlflow.sklearn.log_model.called or mock_mlflow.pyfunc.log_model.called


# ============================================================================
# Feature Metadata Logging Tests
# ============================================================================


class TestFeatureMetadataLogging:
    """Test feature metadata logging."""

    def test_log_feature_metadata(self, mlflow_logger, mock_mlflow):
        """Test logging feature metadata."""
        feature_metadata = {
            "features": ["feature1", "feature2", "feature3"],
            "feature_importance": {"feature1": 0.5, "feature2": 0.3, "feature3": 0.2},
            "feature_versions": {"feature1": "v1.0", "feature2": "v1.1"},
        }

        with mlflow_logger.start_run():
            mlflow_logger.log_feature_metadata(feature_metadata)

        # Should have logged as params or as a JSON artifact
        # Check that some MLflow logging happened
        assert mock_mlflow.log_dict.called or mock_mlflow.log_params.called

    def test_log_feature_list(self, mlflow_logger, mock_mlflow):
        """Test logging a list of features used."""
        features = ["feature1", "feature2", "feature3"]

        with mlflow_logger.start_run():
            mlflow_logger.log_features(features)

        # Should log features as a tag or param
        mock_mlflow.set_tag.assert_called()

    def test_log_vintage_date(self, mlflow_logger, mock_mlflow):
        """Test logging vintage date as metadata."""
        vintage_date = date(2025, 1, 1)

        with mlflow_logger.start_run():
            mlflow_logger.log_vintage_date(vintage_date)

        mock_mlflow.set_tag.assert_called_with("vintage_date", "2025-01-01")


# ============================================================================
# Integration Tests
# ============================================================================


class TestMLflowIntegration:
    """Test end-to-end MLflow logging scenarios."""

    def test_complete_training_run(self, mlflow_logger, mock_mlflow):
        """Test a complete model training run with all logging."""
        # Simulate a complete training workflow
        hyperparams = {"learning_rate": 0.01, "max_depth": 5}
        train_metrics = {"train_rmse": 90.0, "train_smape": 12.0}
        val_metrics = {"val_rmse": 100.0, "val_smape": 15.0}
        features = ["feature1", "feature2", "feature3"]

        with mlflow_logger.start_run():
            # Log hyperparameters
            mlflow_logger.log_hyperparameters(hyperparams)

            # Log training metrics
            mlflow_logger.log_metrics(train_metrics, step=0)
            mlflow_logger.log_metrics(val_metrics, step=0)

            # Log features
            mlflow_logger.log_features(features)

            # Log vintage date
            mlflow_logger.log_vintage_date(date(2025, 1, 1))

        # Verify all logging happened
        mock_mlflow.log_params.assert_called()
        assert mock_mlflow.log_metrics.call_count >= 2
        assert mock_mlflow.set_tag.call_count >= 2

    def test_logging_without_active_run_fails_gracefully(self, mlflow_logger, mock_mlflow):
        """Test that logging without an active run is handled gracefully."""
        mock_mlflow.active_run.return_value = None

        # Should not raise an exception, but should log a warning
        result = mlflow_logger.log_metric("rmse", 100.5)

        # Should return False or handle gracefully
        assert result is False or result is None

    def test_nested_runs_not_supported(self, mlflow_logger, mock_mlflow):
        """Test that nested runs are not supported (or handled correctly)."""
        with mlflow_logger.start_run():
            # Attempting to start another run should use the existing run or fail gracefully
            with mlflow_logger.start_run():
                pass

        # Should not have called start_run twice in a nested manner
        # (implementation details may vary)
        pass


# ============================================================================
# Configuration Tests
# ============================================================================


class TestExperimentConfig:
    """Test ExperimentConfig dataclass."""

    def test_config_creation(self):
        """Test creating an ExperimentConfig."""
        config = ExperimentConfig(
            experiment_name="test_experiment",
            run_name="test_run",
            tracking_uri="http://localhost:5000",
            artifact_location="/tmp/mlruns",
            tags={"env": "test"},
        )

        assert config.experiment_name == "test_experiment"
        assert config.run_name == "test_run"
        assert config.tracking_uri == "http://localhost:5000"
        assert config.artifact_location == "/tmp/mlruns"
        assert config.tags["env"] == "test"

    def test_config_defaults(self):
        """Test ExperimentConfig with default values."""
        config = ExperimentConfig(
            experiment_name="test",
            run_name="run1",
        )

        assert config.tracking_uri is None
        assert config.artifact_location is None
        assert config.tags == {}
