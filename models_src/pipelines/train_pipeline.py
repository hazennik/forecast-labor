"""
Training pipeline for forecasting models.

This module provides orchestrated training workflows including:
- Feature loading from feature registry
- Vintage-aware train/val/test splits
- Model training and evaluation
- MLflow experiment tracking
- Model persistence with metadata

The pipeline ensures:
- No data leakage (vintage-aware splits)
- Deterministic training (via random_state)
- Comprehensive metric tracking
- Production-ready artifact generation
"""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
from datetime import date, datetime
import sys

import pandas as pd
import numpy as np
from loguru import logger

from models_src.utils.base_model import BaseForecaster
from models_src.utils.io import save_model_with_metadata, ModelMetadata
from models_src.utils.mlflow_logger import MLflowLogger, ExperimentConfig
from models_src.utils.metrics import compute_metrics


# ============================================================================
# Configuration
# ============================================================================


@dataclass
class TrainingConfig:
    """
    Configuration for model training pipeline.
    
    This configuration defines all parameters needed for vintage-aware
    model training, including data splits, output settings, and tracking.
    
    Attributes:
        model_name: Name for the trained model
        experiment_name: MLflow experiment name
        target_column: Name of the target variable column
        feature_columns: List of feature column names
        vintage_date: Vintage date for the training data (YYYY-MM-DD)
        train_start_date: Start date for training period (YYYY-MM-DD)
        train_end_date: End date for training period (YYYY-MM-DD)
        val_start_date: Start date for validation period (YYYY-MM-DD)
        val_end_date: End date for validation period (YYYY-MM-DD)
        test_start_date: Start date for test period (YYYY-MM-DD)
        test_end_date: End date for test period (YYYY-MM-DD)
        output_dir: Directory for saving model artifacts
        random_state: Random seed for reproducibility
        save_model: Whether to save model to disk
        log_to_mlflow: Whether to log to MLflow
        query_feature_registry: Whether to query feature registry for metadata
        mlflow_tracking_uri: Optional MLflow tracking URI
    """
    
    model_name: str
    experiment_name: str
    target_column: str
    feature_columns: List[str]
    vintage_date: str
    train_start_date: str
    train_end_date: str
    val_start_date: str
    val_end_date: str
    test_start_date: str
    test_end_date: str
    output_dir: str
    random_state: int = 42
    save_model: bool = True
    log_to_mlflow: bool = True
    query_feature_registry: bool = True
    mlflow_tracking_uri: Optional[str] = None
    
    def __post_init__(self):
        """Validate configuration after initialization."""
        # Validate feature columns
        if not self.feature_columns:
            raise ValueError("feature_columns cannot be empty")
        
        # Validate date order
        dates = [
            ("train_start_date", self.train_start_date),
            ("train_end_date", self.train_end_date),
            ("val_start_date", self.val_start_date),
            ("val_end_date", self.val_end_date),
            ("test_start_date", self.test_start_date),
            ("test_end_date", self.test_end_date),
        ]
        
        # Convert to timestamps for comparison
        date_dict = {name: pd.Timestamp(date_str) for name, date_str in dates}
        
        # Validate train period
        if date_dict["train_start_date"] >= date_dict["train_end_date"]:
            raise ValueError("train_start_date must be before train_end_date")
        
        # Validate val period
        if date_dict["val_start_date"] >= date_dict["val_end_date"]:
            raise ValueError("val_start_date must be before val_end_date")
        
        # Validate test period
        if date_dict["test_start_date"] >= date_dict["test_end_date"]:
            raise ValueError("test_start_date must be before test_end_date")
        
        # Validate chronological order (train < val < test)
        if date_dict["train_end_date"] >= date_dict["val_start_date"]:
            raise ValueError("train_end_date must be before val_start_date (no overlap)")
        
        if date_dict["val_end_date"] >= date_dict["test_start_date"]:
            raise ValueError("val_end_date must be before test_start_date (no overlap)")
        
        # Create output directory
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        
        logger.info(
            "Training configuration validated",
            model_name=self.model_name,
            vintage_date=self.vintage_date,
            n_features=len(self.feature_columns),
        )


@dataclass
class TrainingSplit:
    """
    Container for train/validation/test data splits.
    
    All splits are vintage-aware and maintain chronological order to
    prevent data leakage.
    
    Attributes:
        X_train: Training features
        y_train: Training target
        X_val: Validation features
        y_val: Validation target
        X_test: Test features
        y_test: Test target
    """
    
    X_train: pd.DataFrame
    y_train: pd.Series
    X_val: pd.DataFrame
    y_val: pd.Series
    X_test: pd.DataFrame
    y_test: pd.Series


# ============================================================================
# Data Splitting
# ============================================================================


def create_time_series_splits(
    data: pd.DataFrame,
    config: TrainingConfig,
) -> TrainingSplit:
    """
    Create vintage-aware train/validation/test splits.
    
    This function ensures:
    - No data leakage (strict chronological order)
    - Vintage date constraint (no data after vintage_date)
    - Proper feature/target separation
    
    Args:
        data: DataFrame with date index and features/target columns
        config: Training configuration with date ranges
    
    Returns:
        TrainingSplit with X/y for train/val/test
    
    Raises:
        ValueError: If data is insufficient or splits are empty
        KeyError: If feature/target columns don't exist
    
    Example:
        >>> data = pd.DataFrame(...)  # Time series data
        >>> config = TrainingConfig(...)
        >>> splits = create_time_series_splits(data, config)
        >>> model.fit(splits.X_train, splits.y_train)
    """
    logger.info("Creating vintage-aware data splits")
    
    # Validate input
    if not isinstance(data.index, pd.DatetimeIndex):
        raise ValueError("Data must have DatetimeIndex")
    
    # Check that all required columns exist
    required_columns = config.feature_columns + [config.target_column]
    missing_columns = set(required_columns) - set(data.columns)
    if missing_columns:
        raise KeyError(f"Missing columns in data: {missing_columns}")
    
    # Enforce vintage date constraint
    vintage_date = pd.Timestamp(config.vintage_date)
    data = data[data.index <= vintage_date]
    
    if data.empty:
        raise ValueError(
            f"No data available on or before vintage date {config.vintage_date}"
        )
    
    # Create splits based on date ranges
    train_start = pd.Timestamp(config.train_start_date)
    train_end = pd.Timestamp(config.train_end_date)
    val_start = pd.Timestamp(config.val_start_date)
    val_end = pd.Timestamp(config.val_end_date)
    test_start = pd.Timestamp(config.test_start_date)
    test_end = pd.Timestamp(config.test_end_date)
    
    # Extract train split
    train_data = data[(data.index >= train_start) & (data.index <= train_end)]
    if train_data.empty:
        raise ValueError(
            f"Training data is empty for date range "
            f"{config.train_start_date} to {config.train_end_date}"
        )
    
    X_train = train_data[config.feature_columns]
    y_train = train_data[config.target_column]
    
    # Extract validation split
    val_data = data[(data.index >= val_start) & (data.index <= val_end)]
    if val_data.empty:
        raise ValueError(
            f"Validation data is empty for date range "
            f"{config.val_start_date} to {config.val_end_date}"
        )
    
    X_val = val_data[config.feature_columns]
    y_val = val_data[config.target_column]
    
    # Extract test split
    test_data = data[(data.index >= test_start) & (data.index <= test_end)]
    if test_data.empty:
        raise ValueError(
            f"Test data is empty for date range "
            f"{config.test_start_date} to {config.test_end_date}"
        )
    
    X_test = test_data[config.feature_columns]
    y_test = test_data[config.target_column]
    
    # Log split information
    logger.info(
        "Data splits created",
        train_samples=len(X_train),
        val_samples=len(X_val),
        test_samples=len(X_test),
        train_date_range=f"{X_train.index.min()} to {X_train.index.max()}",
        val_date_range=f"{X_val.index.min()} to {X_val.index.max()}",
        test_date_range=f"{X_test.index.min()} to {X_test.index.max()}",
    )
    
    # Validate chronological order (data leakage prevention)
    if X_train.index.max() >= X_val.index.min():
        raise ValueError(
            "CRITICAL: Training and validation data overlap (data leakage)"
        )
    
    if X_val.index.max() >= X_test.index.min():
        raise ValueError(
            "CRITICAL: Validation and test data overlap (data leakage)"
        )
    
    return TrainingSplit(
        X_train=X_train,
        y_train=y_train,
        X_val=X_val,
        y_val=y_val,
        X_test=X_test,
        y_test=y_test,
    )


# ============================================================================
# Model Training
# ============================================================================


def train_model(
    model: BaseForecaster,
    X_train: pd.DataFrame,
    y_train: pd.Series,
    vintage_date: str,
) -> BaseForecaster:
    """
    Train a forecasting model on provided data.
    
    This function wraps the model's fit() method with logging and
    error handling.
    
    Args:
        model: Forecasting model (must inherit from BaseForecaster)
        X_train: Training features
        y_train: Training target
        vintage_date: Vintage date for reproducibility tracking
    
    Returns:
        Trained model instance
    
    Raises:
        Exception: If training fails
    
    Example:
        >>> model = DFMModel(random_state=42)
        >>> trained_model = train_model(model, X_train, y_train, "2024-12-31")
    """
    logger.info(
        "Training model",
        model_type=type(model).__name__,
        n_samples=len(X_train),
        n_features=X_train.shape[1],
        vintage_date=vintage_date,
    )
    
    try:
        # Train model
        model.fit(X_train, y_train, vintage_date=vintage_date)
        
        logger.info(
            "Model training completed successfully",
            model_type=type(model).__name__,
        )
        
        return model
    
    except Exception as e:
        logger.error(
            "Model training failed",
            model_type=type(model).__name__,
            error=str(e),
            exc_info=True,
        )
        raise


# ============================================================================
# Model Evaluation
# ============================================================================


def evaluate_model(
    model: BaseForecaster,
    X: pd.DataFrame,
    y: pd.Series,
    split_name: str,
) -> Dict[str, float]:
    """
    Evaluate model performance on a data split.
    
    Computes standard forecasting metrics: RMSE, MAE, MAPE, sMAPE.
    
    Args:
        model: Trained forecasting model
        X: Features
        y: True target values
        split_name: Name of the split (for logging)
    
    Returns:
        Dictionary of computed metrics
    
    Example:
        >>> metrics = evaluate_model(model, X_val, y_val, "validation")
        >>> print(metrics["rmse"])
    """
    logger.info(
        "Evaluating model",
        split_name=split_name,
        n_samples=len(X),
    )
    
    try:
        # Generate predictions
        y_pred = model.predict(X)
        
        # Compute metrics using utility function
        metrics = compute_metrics(y_true=y.values, y_pred=y_pred)
        
        logger.info(
            "Model evaluation completed",
            split_name=split_name,
            rmse=metrics.get("rmse"),
            mae=metrics.get("mae"),
            smape=metrics.get("smape"),
        )
        
        return metrics
    
    except Exception as e:
        logger.error(
            "Model evaluation failed",
            split_name=split_name,
            error=str(e),
            exc_info=True,
        )
        raise


# ============================================================================
# Main Training Pipeline
# ============================================================================


def train_pipeline(
    data: pd.DataFrame,
    model: BaseForecaster,
    config: TrainingConfig,
) -> Dict[str, Any]:
    """
    Orchestrated training pipeline with full tracking and persistence.
    
    This pipeline:
    1. Creates vintage-aware data splits (no leakage)
    2. Trains the model on training data
    3. Evaluates on train/val/test splits
    4. Logs to MLflow (if enabled)
    5. Saves model artifacts (if enabled)
    6. Queries feature registry for metadata (if enabled)
    
    Args:
        data: Time series data with DatetimeIndex
        model: Forecasting model instance
        config: Training configuration
    
    Returns:
        Dictionary containing:
        - model: Trained model instance
        - metrics: Dict of metrics by split (train/val/test)
        - splits: TrainingSplit instance with data splits
        - metadata: Training metadata
        - model_path: Path to saved model (if save_model=True)
    
    Raises:
        ValueError: If configuration invalid or data insufficient
        Exception: If training or evaluation fails
    
    Example:
        >>> data = load_vintage_data("2024-12-31")
        >>> model = DFMModel(random_state=42)
        >>> config = TrainingConfig(...)
        >>> result = train_pipeline(data, model, config)
        >>> print(result["metrics"]["validation"]["rmse"])
    """
    logger.info(
        "Starting training pipeline",
        model_name=config.model_name,
        experiment_name=config.experiment_name,
        vintage_date=config.vintage_date,
    )
    
    try:
        # Step 1: Create data splits (vintage-aware, no leakage)
        splits = create_time_series_splits(data, config)
        
        # Step 2: Train model
        trained_model = train_model(
            model=model,
            X_train=splits.X_train,
            y_train=splits.y_train,
            vintage_date=config.vintage_date,
        )
        
        # Step 3: Evaluate model on all splits
        train_metrics = evaluate_model(trained_model, splits.X_train, splits.y_train, "train")
        val_metrics = evaluate_model(trained_model, splits.X_val, splits.y_val, "validation")
        test_metrics = evaluate_model(trained_model, splits.X_test, splits.y_test, "test")
        
        metrics_by_split = {
            "train": train_metrics,
            "validation": val_metrics,
            "test": test_metrics,
        }
        
        # Step 4: Query feature registry (if enabled)
        feature_metadata = None
        if config.query_feature_registry:
            try:
                from features.registry import get_global_registry
                
                registry = get_global_registry()
                
                feature_info = []
                for feature_name in config.feature_columns:
                    try:
                        matches = registry.search(name=feature_name)
                        if matches:
                            feature_info.append(matches[0])
                    except Exception as e:
                        logger.warning(
                            "Could not retrieve feature metadata",
                            feature_name=feature_name,
                            error=str(e),
                        )
                
                feature_metadata = {
                    "features": feature_info,
                    "feature_count": len(feature_info),
                }
                
                logger.info(
                    "Feature metadata retrieved from registry",
                    feature_count=len(feature_info),
                )
            
            except ImportError:
                logger.warning("Feature registry not available")
            except Exception as e:
                logger.warning(
                    "Failed to query feature registry",
                    error=str(e),
                )
        
        # Step 5: MLflow logging (if enabled)
        mlflow_run_id = None
        if config.log_to_mlflow:
            try:
                # Create MLflow logger
                mlflow_config = ExperimentConfig(
                    experiment_name=config.experiment_name,
                    run_name=f"{config.model_name}_{config.vintage_date}",
                    tracking_uri=config.mlflow_tracking_uri,
                    tags={
                        "model_name": config.model_name,
                        "vintage_date": config.vintage_date,
                        "model_type": type(model).__name__,
                    },
                )
                
                mlflow_logger = MLflowLogger(mlflow_config)
                
                with mlflow_logger.start_run() as run:
                    mlflow_run_id = run.info.run_id
                    
                    # Log hyperparameters
                    hyperparams = model.get_params()
                    hyperparams["random_state"] = config.random_state
                    mlflow_logger.log_hyperparameters(hyperparams)
                    
                    # Log metrics by split
                    mlflow_logger.log_metrics_by_split(metrics_by_split)
                    
                    # Log features
                    mlflow_logger.log_features(config.feature_columns)
                    
                    # Log vintage date
                    mlflow_logger.log_vintage_date(date.fromisoformat(config.vintage_date))
                    
                    # Log feature metadata
                    if feature_metadata:
                        mlflow_logger.log_feature_metadata(feature_metadata)
                    
                    # Log model to MLflow
                    mlflow_logger.log_model(
                        model=trained_model,
                        artifact_path="model",
                        registered_model_name=config.model_name,
                    )
                
                logger.info(
                    "Logged to MLflow successfully",
                    experiment_name=config.experiment_name,
                    run_id=mlflow_run_id,
                )
            
            except Exception as e:
                logger.warning(
                    "Failed to log to MLflow",
                    error=str(e),
                    exc_info=True,
                )
        
        # Step 6: Save model artifacts (if enabled)
        model_path = None
        if config.save_model:
            try:
                # Create metadata
                metadata = ModelMetadata(
                    model_id=model.model_id,
                    model_type=type(model).__name__,
                    training_date=datetime.now(),
                    vintage_date=date.fromisoformat(config.vintage_date),
                    features=config.feature_columns,
                    hyperparameters=model.get_params(),
                    metrics=val_metrics,  # Use validation metrics
                    python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
                    dependencies={
                        "pandas": pd.__version__,
                        "numpy": np.__version__,
                    },
                )
                
                # Save model with metadata
                artifact = save_model_with_metadata(
                    model=trained_model,
                    metadata=metadata,
                    output_dir=config.output_dir,
                    model_name=config.model_name,
                    format="joblib",
                    include_feature_info=config.query_feature_registry,
                )
                
                model_path = str(artifact.model_path)
                
                logger.info(
                    "Model saved successfully",
                    model_path=model_path,
                    hash=artifact.hash_value,
                )
            
            except Exception as e:
                logger.error(
                    "Failed to save model",
                    error=str(e),
                    exc_info=True,
                )
                raise
        
        # Step 7: Prepare result
        result = {
            "model": trained_model,
            "metrics": metrics_by_split,
            "splits": splits,
            "metadata": {
                "model_name": config.model_name,
                "experiment_name": config.experiment_name,
                "vintage_date": config.vintage_date,
                "random_state": config.random_state,
                "training_date": datetime.now().isoformat(),
                "n_train_samples": len(splits.X_train),
                "n_val_samples": len(splits.X_val),
                "n_test_samples": len(splits.X_test),
                "n_features": len(config.feature_columns),
            },
        }
        
        if feature_metadata:
            result["metadata"]["feature_metadata"] = feature_metadata
        
        if model_path:
            result["model_path"] = model_path
        
        if mlflow_run_id:
            result["metadata"]["mlflow_run_id"] = mlflow_run_id
        
        logger.info(
            "Training pipeline completed successfully",
            model_name=config.model_name,
            val_rmse=val_metrics.get("rmse"),
            test_rmse=test_metrics.get("rmse"),
        )
        
        return result
    
    except Exception as e:
        logger.error(
            "Training pipeline failed",
            model_name=config.model_name,
            error=str(e),
            exc_info=True,
        )
        raise

