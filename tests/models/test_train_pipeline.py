"""
Tests for model training pipeline.

This module tests the orchestrated training workflow including:
- Feature loading from feature registry
- Vintage-aware train/val/test splits
- Model training and evaluation
- MLflow experiment tracking
- Data leakage prevention
"""

import pytest
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import date, datetime, timezone
from unittest.mock import Mock, patch, MagicMock, call
import tempfile

from models_src.pipelines.train_pipeline import (
    TrainingConfig,
    TrainingSplit,
    create_time_series_splits,
    train_model,
    evaluate_model,
    train_pipeline,
)
from models_src.utils.base_model import BaseForecaster
from models_src.utils.io import ModelMetadata


# ============================================================================
# Test Helpers
# ============================================================================


class MockForecaster(BaseForecaster):
    """
    Mock forecaster for testing training pipelines.
    
    Must be at module level to be pickleable.
    """
    
    def __init__(self, random_state=42, should_fail=False):
        super().__init__(random_state=random_state)
        self.should_fail = should_fail
        self._is_fitted = False
        self.fit_called_with = None
        self.predict_called_with = None
    
    def fit(self, X, y, vintage_date):
        """Fit mock model."""
        if self.should_fail:
            raise ValueError("Intentional training failure for testing")
        
        self.fit_called_with = {
            "X_shape": X.shape,
            "y_shape": y.shape,
            "vintage_date": vintage_date,
        }
        self._is_fitted = True
        self.vintage_date = vintage_date
        self.feature_names = X.columns.tolist()
        self.n_features = X.shape[1]
        
        return self
    
    def predict(self, X):
        """Generate mock predictions."""
        if not self._is_fitted:
            raise ValueError("Model must be fitted before prediction")
        
        self.predict_called_with = {"X_shape": X.shape}
        
        # Return simple predictions based on first feature
        predictions = X.iloc[:, 0].values + np.random.RandomState(self.random_state).randn(len(X)) * 0.1
        return predictions
    
    def get_params(self):
        """Return mock parameters."""
        return {
            "random_state": self.random_state,
            "is_fitted": self._is_fitted,
            "n_features": getattr(self, "n_features", None),
            "vintage_date": getattr(self, "vintage_date", None),
        }


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sample_time_series_data():
    """
    Create sample time series data with proper temporal structure.
    
    Returns DataFrame with:
    - date index (2020-01-01 to 2024-12-31)
    - 5 features
    - target variable
    """
    dates = pd.date_range(start="2020-01-01", end="2024-12-31", freq="MS")
    n_samples = len(dates)
    
    np.random.seed(42)
    
    data = pd.DataFrame({
        "date": dates,
        "feature_1": np.random.randn(n_samples).cumsum(),
        "feature_2": np.random.randn(n_samples).cumsum(),
        "feature_3": np.random.randn(n_samples) * 10,
        "feature_4": np.random.randn(n_samples) * 5,
        "feature_5": np.random.randn(n_samples) * 2,
        "target": np.random.randn(n_samples).cumsum() * 100,
    })
    
    data.set_index("date", inplace=True)
    
    return data


@pytest.fixture
def sample_features():
    """Sample feature names list."""
    return ["feature_1", "feature_2", "feature_3", "feature_4", "feature_5"]


@pytest.fixture
def sample_training_config(tmp_path):
    """Sample training configuration."""
    return TrainingConfig(
        model_name="test_model",
        experiment_name="test_experiment",
        target_column="target",
        feature_columns=["feature_1", "feature_2", "feature_3", "feature_4", "feature_5"],
        vintage_date="2024-12-31",
        train_start_date="2020-01-01",
        train_end_date="2023-12-31",
        val_start_date="2024-01-01",
        val_end_date="2024-06-30",
        test_start_date="2024-07-01",
        test_end_date="2024-12-31",
        output_dir=str(tmp_path / "models"),
        random_state=42,
        save_model=True,
        log_to_mlflow=False,  # Disable MLflow for most tests
    )


@pytest.fixture
def mock_model():
    """Create mock model instance."""
    return MockForecaster(random_state=42)


@pytest.fixture
def mock_feature_registry():
    """Create mock feature registry."""
    registry = Mock()
    registry.search.return_value = [
        {
            "feature_id": "feat-1",
            "name": "feature_1",
            "source": "ces",
            "frequency": "monthly",
            "version": "1.0.0",
            "vintage_date": "2024-12-31",
        },
        {
            "feature_id": "feat-2",
            "name": "feature_2",
            "source": "laus",
            "frequency": "monthly",
            "version": "1.0.0",
            "vintage_date": "2024-12-31",
        },
    ]
    return registry


# ============================================================================
# Test TrainingConfig
# ============================================================================


class TestTrainingConfig:
    """Test training configuration validation."""
    
    def test_valid_config(self, sample_training_config):
        """Test that valid configuration is accepted."""
        assert sample_training_config.model_name == "test_model"
        assert sample_training_config.random_state == 42
        assert sample_training_config.save_model is True
    
    def test_date_validation(self, tmp_path):
        """Test that date order is validated."""
        with pytest.raises(ValueError, match="train_start_date must be before train_end_date"):
            TrainingConfig(
                model_name="test_model",
                experiment_name="test_experiment",
                target_column="target",
                feature_columns=["feature_1"],
                vintage_date="2024-12-31",
                train_start_date="2023-12-31",
                train_end_date="2020-01-01",  # Invalid: before train_start
                val_start_date="2024-01-01",
                val_end_date="2024-06-30",
                test_start_date="2024-07-01",
                test_end_date="2024-12-31",
                output_dir=str(tmp_path / "models"),
            )
    
    def test_feature_columns_required(self, tmp_path):
        """Test that feature_columns is required."""
        with pytest.raises(ValueError, match="feature_columns cannot be empty"):
            TrainingConfig(
                model_name="test_model",
                experiment_name="test_experiment",
                target_column="target",
                feature_columns=[],  # Empty
                vintage_date="2024-12-31",
                train_start_date="2020-01-01",
                train_end_date="2023-12-31",
                val_start_date="2024-01-01",
                val_end_date="2024-06-30",
                test_start_date="2024-07-01",
                test_end_date="2024-12-31",
                output_dir=str(tmp_path / "models"),
            )


# ============================================================================
# Test Time Series Splits
# ============================================================================


class TestTimeSeriesSplits:
    """Test vintage-aware time series splitting."""
    
    def test_create_splits_basic(self, sample_time_series_data, sample_training_config):
        """Test basic train/val/test split creation."""
        splits = create_time_series_splits(sample_time_series_data, sample_training_config)
        
        assert isinstance(splits, TrainingSplit)
        assert splits.X_train.shape[0] > 0
        assert splits.X_val.shape[0] > 0
        assert splits.X_test.shape[0] > 0
        assert len(splits.y_train) == len(splits.X_train)
        assert len(splits.y_val) == len(splits.X_val)
        assert len(splits.y_test) == len(splits.X_test)
    
    def test_no_data_leakage(self, sample_time_series_data, sample_training_config):
        """
        Test that no future data leaks into training set.
        
        Critical for vintage-aware forecasting: training data must not
        include any observations after train_end_date.
        """
        splits = create_time_series_splits(sample_time_series_data, sample_training_config)
        
        # Check train data is before validation data
        train_max_date = splits.X_train.index.max()
        val_min_date = splits.X_val.index.min()
        test_min_date = splits.X_test.index.min()
        
        assert train_max_date <= pd.Timestamp(sample_training_config.train_end_date), \
            "Training data includes dates after train_end_date (data leakage)"
        
        assert val_min_date >= pd.Timestamp(sample_training_config.val_start_date), \
            "Validation data includes dates before val_start_date (data leakage)"
        
        # Validation should not overlap with test
        val_max_date = splits.X_val.index.max()
        assert val_max_date <= pd.Timestamp(sample_training_config.val_end_date)
        assert test_min_date >= pd.Timestamp(sample_training_config.test_start_date)
    
    def test_chronological_order(self, sample_time_series_data, sample_training_config):
        """Test that splits maintain chronological order (train < val < test)."""
        splits = create_time_series_splits(sample_time_series_data, sample_training_config)
        
        train_max_date = splits.X_train.index.max()
        val_min_date = splits.X_val.index.min()
        val_max_date = splits.X_val.index.max()
        test_min_date = splits.X_test.index.min()
        
        # Train must be entirely before validation
        assert train_max_date < val_min_date, \
            "Training and validation data overlap"
        
        # Validation must be entirely before test
        assert val_max_date < test_min_date, \
            "Validation and test data overlap"
    
    def test_feature_columns_extracted(self, sample_time_series_data, sample_training_config):
        """Test that only specified feature columns are extracted."""
        splits = create_time_series_splits(sample_time_series_data, sample_training_config)
        
        expected_features = set(sample_training_config.feature_columns)
        
        assert set(splits.X_train.columns) == expected_features
        assert set(splits.X_val.columns) == expected_features
        assert set(splits.X_test.columns) == expected_features
    
    def test_target_column_extracted(self, sample_time_series_data, sample_training_config):
        """Test that target column is correctly extracted."""
        splits = create_time_series_splits(sample_time_series_data, sample_training_config)
        
        assert splits.y_train.name == sample_training_config.target_column
        assert splits.y_val.name == sample_training_config.target_column
        assert splits.y_test.name == sample_training_config.target_column
    
    def test_vintage_date_awareness(self, sample_time_series_data, sample_training_config):
        """
        Test that split respects vintage date (no data after vintage date).
        
        In real backtesting, we must not use data that wasn't available
        at the vintage date.
        """
        splits = create_time_series_splits(sample_time_series_data, sample_training_config)
        
        vintage_date = pd.Timestamp(sample_training_config.vintage_date)
        
        # All data must be on or before vintage date
        assert splits.X_train.index.max() <= vintage_date, \
            "Training data includes dates after vintage_date"
        assert splits.X_val.index.max() <= vintage_date, \
            "Validation data includes dates after vintage_date"
        assert splits.X_test.index.max() <= vintage_date, \
            "Test data includes dates after vintage_date"


# ============================================================================
# Test Model Training
# ============================================================================


class TestModelTraining:
    """Test model training function."""
    
    def test_train_model_basic(self, sample_time_series_data, sample_training_config, mock_model):
        """Test basic model training."""
        splits = create_time_series_splits(sample_time_series_data, sample_training_config)
        
        trained_model = train_model(
            model=mock_model,
            X_train=splits.X_train,
            y_train=splits.y_train,
            vintage_date=sample_training_config.vintage_date,
        )
        
        assert trained_model._is_fitted is True
        assert trained_model.fit_called_with is not None
        assert trained_model.vintage_date == sample_training_config.vintage_date
    
    def test_train_model_vintage_tracking(self, sample_time_series_data, sample_training_config, mock_model):
        """Test that vintage date is tracked in trained model."""
        splits = create_time_series_splits(sample_time_series_data, sample_training_config)
        
        vintage_date = "2024-12-31"
        trained_model = train_model(
            model=mock_model,
            X_train=splits.X_train,
            y_train=splits.y_train,
            vintage_date=vintage_date,
        )
        
        assert hasattr(trained_model, "vintage_date")
        assert trained_model.vintage_date == vintage_date
    
    def test_train_model_feature_names(self, sample_time_series_data, sample_training_config, mock_model):
        """Test that feature names are tracked."""
        splits = create_time_series_splits(sample_time_series_data, sample_training_config)
        
        trained_model = train_model(
            model=mock_model,
            X_train=splits.X_train,
            y_train=splits.y_train,
            vintage_date=sample_training_config.vintage_date,
        )
        
        assert hasattr(trained_model, "feature_names")
        assert trained_model.feature_names == sample_training_config.feature_columns
    
    def test_train_model_handles_failure(self, sample_time_series_data, sample_training_config):
        """Test that training failures are handled gracefully."""
        splits = create_time_series_splits(sample_time_series_data, sample_training_config)
        
        failing_model = MockForecaster(should_fail=True)
        
        with pytest.raises(ValueError, match="Intentional training failure"):
            train_model(
                model=failing_model,
                X_train=splits.X_train,
                y_train=splits.y_train,
                vintage_date=sample_training_config.vintage_date,
            )


# ============================================================================
# Test Model Evaluation
# ============================================================================


class TestModelEvaluation:
    """Test model evaluation function."""
    
    def test_evaluate_model_basic(self, sample_time_series_data, sample_training_config, mock_model):
        """Test basic model evaluation."""
        splits = create_time_series_splits(sample_time_series_data, sample_training_config)
        
        # Train model first
        trained_model = train_model(
            model=mock_model,
            X_train=splits.X_train,
            y_train=splits.y_train,
            vintage_date=sample_training_config.vintage_date,
        )
        
        # Evaluate on validation set
        metrics = evaluate_model(
            model=trained_model,
            X=splits.X_val,
            y=splits.y_val,
            split_name="validation",
        )
        
        # Check that common metrics are computed
        assert "rmse" in metrics
        assert "mae" in metrics
        assert "mape" in metrics
        assert "smape" in metrics
        assert isinstance(metrics["rmse"], (int, float))
        assert isinstance(metrics["mae"], (int, float))
    
    def test_evaluate_multiple_splits(self, sample_time_series_data, sample_training_config, mock_model):
        """Test evaluation on multiple data splits."""
        splits = create_time_series_splits(sample_time_series_data, sample_training_config)
        
        trained_model = train_model(
            model=mock_model,
            X_train=splits.X_train,
            y_train=splits.y_train,
            vintage_date=sample_training_config.vintage_date,
        )
        
        # Evaluate on all splits
        train_metrics = evaluate_model(trained_model, splits.X_train, splits.y_train, "train")
        val_metrics = evaluate_model(trained_model, splits.X_val, splits.y_val, "validation")
        test_metrics = evaluate_model(trained_model, splits.X_test, splits.y_test, "test")
        
        # All should have same metrics computed
        for metrics in [train_metrics, val_metrics, test_metrics]:
            assert "rmse" in metrics
            assert "mae" in metrics
        
        # Training error should typically be lower than validation/test
        # (though this is not guaranteed with our simple mock model)
        assert train_metrics["rmse"] >= 0
        assert val_metrics["rmse"] >= 0
        assert test_metrics["rmse"] >= 0
    
    def test_evaluate_model_not_fitted(self, sample_time_series_data, sample_training_config):
        """Test that evaluation fails if model not fitted."""
        splits = create_time_series_splits(sample_time_series_data, sample_training_config)
        
        unfitted_model = MockForecaster(random_state=42)
        
        with pytest.raises(ValueError, match="Model must be fitted before prediction"):
            evaluate_model(
                model=unfitted_model,
                X=splits.X_val,
                y=splits.y_val,
                split_name="validation",
            )


# ============================================================================
# Test Training Pipeline (End-to-End)
# ============================================================================


class TestTrainingPipeline:
    """Test end-to-end training pipeline."""
    
    def test_pipeline_end_to_end(self, sample_time_series_data, sample_training_config, mock_model):
        """Test complete training pipeline execution."""
        result = train_pipeline(
            data=sample_time_series_data,
            model=mock_model,
            config=sample_training_config,
        )
        
        # Check that result contains all expected keys
        assert "model" in result
        assert "metrics" in result
        assert "splits" in result
        assert "metadata" in result
        
        # Check model is fitted
        assert result["model"]._is_fitted is True
        
        # Check metrics contain all splits
        assert "train" in result["metrics"]
        assert "validation" in result["metrics"]
        assert "test" in result["metrics"]
        
        # Check metadata
        metadata = result["metadata"]
        assert metadata["model_name"] == sample_training_config.model_name
        assert metadata["vintage_date"] == sample_training_config.vintage_date
        assert metadata["random_state"] == sample_training_config.random_state
    
    @patch("models_src.pipelines.train_pipeline.MLflowLogger")
    def test_pipeline_mlflow_logging(self, mock_mlflow_class, sample_time_series_data, sample_training_config, mock_model):
        """Test that MLflow logging is called when enabled."""
        # Enable MLflow
        sample_training_config.log_to_mlflow = True
        
        # Create mock MLflow logger
        mock_logger = MagicMock()
        mock_mlflow_class.return_value = mock_logger
        mock_logger.start_run.return_value.__enter__.return_value = MagicMock()
        mock_logger.start_run.return_value.__exit__.return_value = None
        
        result = train_pipeline(
            data=sample_time_series_data,
            model=mock_model,
            config=sample_training_config,
        )
        
        # Check MLflow methods were called
        assert mock_logger.start_run.called
        assert mock_logger.log_hyperparameters.called
        assert mock_logger.log_metrics.called or mock_logger.log_metrics_by_split.called
    
    @patch("models_src.pipelines.train_pipeline.get_global_registry")
    def test_pipeline_feature_registry_integration(self, mock_get_registry, sample_time_series_data, sample_training_config, mock_model, mock_feature_registry):
        """Test feature registry integration."""
        # Setup mock registry
        mock_get_registry.return_value = mock_feature_registry
        
        # Enable feature registry query
        sample_training_config.query_feature_registry = True
        
        result = train_pipeline(
            data=sample_time_series_data,
            model=mock_model,
            config=sample_training_config,
        )
        
        # Check that feature registry was queried
        assert mock_get_registry.called
        
        # Check that feature metadata is in result
        assert "feature_metadata" in result["metadata"]
    
    def test_pipeline_model_saving(self, sample_time_series_data, sample_training_config, mock_model):
        """Test that model is saved when save_model=True."""
        sample_training_config.save_model = True
        
        result = train_pipeline(
            data=sample_time_series_data,
            model=mock_model,
            config=sample_training_config,
        )
        
        # Check that model_path is returned
        assert "model_path" in result
        
        # Check that model file exists
        model_path = Path(result["model_path"])
        assert model_path.exists()
        
        # Check that metadata file exists
        metadata_path = model_path.parent / f"{model_path.stem}_metadata.json"
        assert metadata_path.exists()
    
    def test_pipeline_no_model_saving(self, sample_time_series_data, sample_training_config, mock_model):
        """Test that model is not saved when save_model=False."""
        sample_training_config.save_model = False
        
        result = train_pipeline(
            data=sample_time_series_data,
            model=mock_model,
            config=sample_training_config,
        )
        
        # Check that model_path is not returned
        assert "model_path" not in result or result["model_path"] is None
    
    def test_pipeline_data_leakage_prevention(self, sample_time_series_data, sample_training_config, mock_model):
        """
        Test that pipeline prevents data leakage.
        
        This is a critical test: the pipeline must ensure that no future data
        is used during training. This is validated by checking date ranges.
        """
        result = train_pipeline(
            data=sample_time_series_data,
            model=mock_model,
            config=sample_training_config,
        )
        
        splits = result["splits"]
        
        # Verify no future data in training set
        train_max_date = splits.X_train.index.max()
        val_min_date = splits.X_val.index.min()
        test_min_date = splits.X_test.index.min()
        
        assert train_max_date < val_min_date, \
            "CRITICAL: Training data overlaps with validation (data leakage)"
        
        assert val_min_date < test_min_date, \
            "CRITICAL: Validation data overlaps with test (data leakage)"
        
        # Verify vintage date constraint
        vintage_date = pd.Timestamp(sample_training_config.vintage_date)
        assert splits.X_test.index.max() <= vintage_date, \
            "CRITICAL: Test data includes dates after vintage date (data leakage)"
    
    def test_pipeline_reproducibility(self, sample_time_series_data, sample_training_config):
        """
        Test that pipeline produces deterministic results.
        
        Same data + same config + same seed = identical results.
        """
        # Run pipeline twice with same seed
        model1 = MockForecaster(random_state=42)
        result1 = train_pipeline(
            data=sample_time_series_data.copy(),
            model=model1,
            config=sample_training_config,
        )
        
        model2 = MockForecaster(random_state=42)
        result2 = train_pipeline(
            data=sample_time_series_data.copy(),
            model=model2,
            config=sample_training_config,
        )
        
        # Metrics should be identical (or very close due to floating point)
        for split in ["train", "validation", "test"]:
            for metric in ["rmse", "mae"]:
                assert abs(result1["metrics"][split][metric] - result2["metrics"][split][metric]) < 1e-6, \
                    f"Reproducibility failed for {split} {metric}"


# ============================================================================
# Test Prefect Integration (Mocked)
# ============================================================================


class TestPrefectIntegration:
    """Test Prefect workflow orchestration (mocked)."""
    
    @patch("models_src.pipelines.train_pipeline.task")
    @patch("models_src.pipelines.train_pipeline.flow")
    def test_prefect_flow_structure(self, mock_flow, mock_task, sample_time_series_data, sample_training_config, mock_model):
        """Test that pipeline can be wrapped in Prefect flow."""
        # Mock Prefect decorators
        mock_task.return_value = lambda func: func
        mock_flow.return_value = lambda func: func
        
        # This test just verifies that the pipeline can be decorated
        # Real Prefect testing would require running a Prefect server
        
        result = train_pipeline(
            data=sample_time_series_data,
            model=mock_model,
            config=sample_training_config,
        )
        
        assert result is not None
        assert "model" in result
    
    def test_pipeline_idempotency(self, sample_time_series_data, sample_training_config, mock_model):
        """
        Test that pipeline is idempotent (can be re-run safely).
        
        Important for Prefect: if a flow fails and is retried, it should
        produce the same result.
        """
        # Run pipeline twice
        result1 = train_pipeline(
            data=sample_time_series_data.copy(),
            model=MockForecaster(random_state=42),
            config=sample_training_config,
        )
        
        result2 = train_pipeline(
            data=sample_time_series_data.copy(),
            model=MockForecaster(random_state=42),
            config=sample_training_config,
        )
        
        # Results should be identical
        assert result1["metadata"]["model_name"] == result2["metadata"]["model_name"]
        assert result1["metadata"]["vintage_date"] == result2["metadata"]["vintage_date"]


# ============================================================================
# Test Error Handling
# ============================================================================


class TestErrorHandling:
    """Test error handling in training pipeline."""
    
    def test_missing_features_error(self, sample_time_series_data, sample_training_config, mock_model):
        """Test that missing features raise appropriate error."""
        # Request features that don't exist
        sample_training_config.feature_columns = ["nonexistent_feature"]
        
        with pytest.raises((KeyError, ValueError)):
            train_pipeline(
                data=sample_time_series_data,
                model=mock_model,
                config=sample_training_config,
            )
    
    def test_missing_target_error(self, sample_time_series_data, sample_training_config, mock_model):
        """Test that missing target column raises appropriate error."""
        sample_training_config.target_column = "nonexistent_target"
        
        with pytest.raises((KeyError, ValueError)):
            train_pipeline(
                data=sample_time_series_data,
                model=mock_model,
                config=sample_training_config,
            )
    
    def test_empty_split_error(self, sample_time_series_data, sample_training_config, mock_model):
        """Test that empty data split raises appropriate error."""
        # Set date range that results in empty training set
        sample_training_config.train_start_date = "2030-01-01"
        sample_training_config.train_end_date = "2030-12-31"
        
        with pytest.raises(ValueError, match="empty|no data|insufficient"):
            train_pipeline(
                data=sample_time_series_data,
                model=mock_model,
                config=sample_training_config,
            )

