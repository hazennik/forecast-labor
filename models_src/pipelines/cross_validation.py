"""
Time-series cross-validation for forecasting models.

This module provides expanding window cross-validation for vintage-aware
model evaluation. Key features:
- Expanding window (training data grows with each fold)
- No data leakage (strict chronological order)
- Vintage date constraint enforcement
- Comprehensive metric aggregation
- Timeout enforcement (Phase 6.2.2)

The expanding window approach is appropriate for time series because:
1. More recent data is typically more relevant
2. We want to evaluate performance as data accumulates
3. Real-world forecasting scenarios use all available historical data
"""

import time
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from pathlib import Path

import pandas as pd
import numpy as np
from loguru import logger

from models_src.utils.base_model import BaseForecaster
from models_src.utils.metrics import compute_metrics


# ============================================================================
# Exceptions
# ============================================================================


class CVTimeoutError(Exception):
    """Raised when cross-validation exceeds timeout limits."""
    pass


class FoldTimeoutError(Exception):
    """Raised when a single fold exceeds its timeout limit."""
    pass


# ============================================================================
# Configuration
# ============================================================================


@dataclass
class CrossValidationConfig:
    """
    Configuration for time-series cross-validation.
    
    This configuration defines the expanding window cross-validation scheme
    for vintage-aware forecasting model evaluation.
    
    Attributes:
        n_folds: Number of cross-validation folds
        initial_train_size: Number of periods in initial training set
        forecast_horizon: Number of periods to forecast (test set size)
        step_size: Number of periods to step forward between folds
        target_column: Name of the target variable column
        feature_columns: List of feature column names
        vintage_date: Vintage date constraint (YYYY-MM-DD)
        gap_size: Number of periods to skip between train and test (default: 0)
        max_time_per_fold_seconds: Maximum time allowed per fold in seconds (default: None = no limit)
        total_max_time_seconds: Maximum total time for all folds in seconds (default: None = no limit)
    
    Example:
        >>> config = CrossValidationConfig(
        ...     n_folds=5,
        ...     initial_train_size=24,  # 24 months initial training
        ...     forecast_horizon=6,      # 6 months test period
        ...     step_size=6,             # 6 months between folds
        ...     target_column="target",
        ...     feature_columns=["feature_1", "feature_2"],
        ...     vintage_date="2024-12-31",
        ...     max_time_per_fold_seconds=300,  # 5 minutes per fold
        ...     total_max_time_seconds=1800,    # 30 minutes total
        ... )
    """
    
    n_folds: int
    initial_train_size: int
    forecast_horizon: int
    step_size: int
    target_column: str
    feature_columns: List[str]
    vintage_date: str
    gap_size: int = 0
    max_time_per_fold_seconds: Optional[int] = None
    total_max_time_seconds: Optional[int] = None
    
    def __post_init__(self):
        """Validate configuration after initialization."""
        # Validate n_folds
        if self.n_folds < 1:
            raise ValueError("n_folds must be at least 1")
        
        # Validate initial_train_size
        if self.initial_train_size < 1:
            raise ValueError("initial_train_size must be at least 1")
        
        # Validate forecast_horizon
        if self.forecast_horizon < 1:
            raise ValueError("forecast_horizon must be at least 1")
        
        # Validate step_size
        if self.step_size < 1:
            raise ValueError("step_size must be at least 1")
        
        # Validate feature_columns
        if not self.feature_columns:
            raise ValueError("feature_columns cannot be empty")
        
        # Validate gap_size
        if self.gap_size < 0:
            raise ValueError("gap_size must be non-negative")
        
        # Validate timeout parameters (Phase 5.9.2 Quality Gap Resolution)
        if self.max_time_per_fold_seconds is not None:
            if self.max_time_per_fold_seconds <= 0:
                raise ValueError("max_time_per_fold_seconds must be positive")
        
        if self.total_max_time_seconds is not None:
            if self.total_max_time_seconds <= 0:
                raise ValueError("total_max_time_seconds must be positive")
        
        logger.info(
            "Cross-validation configuration validated",
            n_folds=self.n_folds,
            initial_train_size=self.initial_train_size,
            forecast_horizon=self.forecast_horizon,
            step_size=self.step_size,
            n_features=len(self.feature_columns),
        )


@dataclass
class CVFold:
    """
    Container for a single cross-validation fold.
    
    Each fold contains train and test data splits with strict
    chronological ordering to prevent data leakage.
    
    Attributes:
        fold_index: Index of this fold (0-based)
        X_train: Training features
        y_train: Training target
        X_test: Test features
        y_test: Test target
    """
    
    fold_index: int
    X_train: pd.DataFrame
    y_train: pd.Series
    X_test: pd.DataFrame
    y_test: pd.Series


# ============================================================================
# Fold Generation
# ============================================================================


def generate_expanding_window_folds(
    data: pd.DataFrame,
    config: CrossValidationConfig,
) -> List[CVFold]:
    """
    Generate expanding window cross-validation folds.
    
    This function creates folds where the training window expands with each
    fold, while the test window slides forward. This approach:
    - Uses all available historical data (expanding window)
    - Maintains chronological order (no data leakage)
    - Respects vintage date constraint
    
    Args:
        data: DataFrame with DatetimeIndex and features/target columns
        config: Cross-validation configuration
    
    Returns:
        List of CVFold instances, one per fold
    
    Raises:
        ValueError: If data insufficient, wrong index type, or config invalid
        KeyError: If feature/target columns don't exist
    
    Example:
        >>> data = pd.DataFrame(...)  # Time series data
        >>> config = CrossValidationConfig(...)
        >>> folds = generate_expanding_window_folds(data, config)
        >>> for fold in folds:
        ...     model.fit(fold.X_train, fold.y_train)
        ...     predictions = model.predict(fold.X_test)
    """
    logger.info(
        "Generating expanding window folds",
        n_folds=config.n_folds,
        initial_train_size=config.initial_train_size,
    )
    
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
    data = data[data.index <= vintage_date].copy()
    
    if data.empty:
        raise ValueError(
            f"No data available on or before vintage date {config.vintage_date}"
        )
    
    # Calculate minimum data required
    min_data_size = (
        config.initial_train_size +
        config.gap_size +
        config.forecast_horizon +
        (config.n_folds - 1) * config.step_size
    )
    
    if len(data) < min_data_size:
        raise ValueError(
            f"Insufficient data for {config.n_folds} folds. "
            f"Need at least {min_data_size} samples, got {len(data)}"
        )
    
    # Generate folds
    folds = []
    
    for fold_idx in range(config.n_folds):
        # Calculate indices for this fold
        # Training window: from start to (initial + fold_idx * step)
        train_end_idx = config.initial_train_size + fold_idx * config.step_size
        
        # Test window: after gap, for forecast_horizon periods
        test_start_idx = train_end_idx + config.gap_size
        test_end_idx = test_start_idx + config.forecast_horizon
        
        # Check if we have enough data for this fold
        if test_end_idx > len(data):
            logger.warning(
                f"Insufficient data for fold {fold_idx}, stopping at {fold_idx} folds"
            )
            break
        
        # Extract training data (from start to train_end_idx)
        train_data = data.iloc[:train_end_idx]
        X_train = train_data[config.feature_columns]
        y_train = train_data[config.target_column]
        
        # Extract test data (from test_start_idx to test_end_idx)
        test_data = data.iloc[test_start_idx:test_end_idx]
        X_test = test_data[config.feature_columns]
        y_test = test_data[config.target_column]
        
        # Validate split
        if X_train.empty or X_test.empty:
            raise ValueError(
                f"Empty split in fold {fold_idx}: "
                f"train={len(X_train)}, test={len(X_test)}"
            )
        
        # Validate chronological order (data leakage prevention)
        if X_train.index.max() >= X_test.index.min():
            raise ValueError(
                f"CRITICAL: Fold {fold_idx} has data leakage - "
                f"training overlaps with test"
            )
        
        # Create fold
        fold = CVFold(
            fold_index=fold_idx,
            X_train=X_train,
            y_train=y_train,
            X_test=X_test,
            y_test=y_test,
        )
        
        folds.append(fold)
        
        logger.debug(
            "Generated fold",
            fold_index=fold_idx,
            train_size=len(X_train),
            test_size=len(X_test),
            train_date_range=f"{X_train.index.min()} to {X_train.index.max()}",
            test_date_range=f"{X_test.index.min()} to {X_test.index.max()}",
        )
    
    if len(folds) < config.n_folds:
        logger.warning(
            f"Generated {len(folds)} folds instead of requested {config.n_folds} "
            f"due to insufficient data"
        )
    
    logger.info(
        "Fold generation complete",
        n_folds_generated=len(folds),
        train_sizes=[len(f.X_train) for f in folds],
        test_sizes=[len(f.X_test) for f in folds],
    )
    
    return folds


# ============================================================================
# Cross-Validation Execution
# ============================================================================


def cross_validate_model(
    data: pd.DataFrame,
    model: BaseForecaster,
    config: CrossValidationConfig,
) -> List[Dict[str, Any]]:
    """
    Perform cross-validation on a forecasting model with timeout enforcement.
    
    This function:
    1. Generates expanding window folds
    2. Trains model on each fold's training data
    3. Evaluates on both training and test data
    4. Returns comprehensive results per fold
    5. Enforces per-fold and total timeout limits (Phase 6.2.2)
    
    Timeout Behavior:
    - If a fold exceeds max_time_per_fold_seconds, it is skipped with a warning
    - If total CV time exceeds total_max_time_seconds, CV stops and returns partial results
    - When timeouts are None (default), no limits are enforced (backward compatible)
    
    Args:
        data: Time series data with DatetimeIndex
        model: Forecasting model instance
        config: Cross-validation configuration with optional timeout settings
    
    Returns:
        List of dictionaries, one per completed fold, containing:
        - fold_index: Fold number
        - train_metrics: Dictionary of training metrics
        - test_metrics: Dictionary of test metrics
        - train_size: Number of training samples
        - test_size: Number of test samples
        - train_date_range: Training date range
        - test_date_range: Test date range
        - elapsed_seconds: Time taken for this fold (if timing enabled)
        
        May return partial results if timeouts occur.
    
    Raises:
        Exception: If training or evaluation fails (non-timeout errors)
    
    Example:
        >>> config = CrossValidationConfig(
        ...     n_folds=5,
        ...     max_time_per_fold_seconds=300,  # 5 minutes per fold
        ...     total_max_time_seconds=1800,    # 30 minutes total
        ...     ...
        ... )
        >>> results = cross_validate_model(data, model, config)
        >>> for result in results:
        ...     print(f"Fold {result['fold_index']}: "
        ...           f"Test RMSE = {result['test_metrics']['rmse']:.2f}")
    """
    logger.info(
        "Starting cross-validation",
        model_type=type(model).__name__,
        n_folds=config.n_folds,
        max_time_per_fold_seconds=config.max_time_per_fold_seconds,
        total_max_time_seconds=config.total_max_time_seconds,
    )
    
    # Generate folds
    folds = generate_expanding_window_folds(data, config)
    
    # Track timing for timeout enforcement
    cv_start_time = time.time()
    
    # Train and evaluate on each fold
    results = []
    folds_skipped = 0
    folds_timed_out = 0
    
    for fold in folds:
        # Check total timeout before starting fold
        if config.total_max_time_seconds is not None:
            total_elapsed = time.time() - cv_start_time
            if total_elapsed >= config.total_max_time_seconds:
                logger.warning(
                    "Total CV timeout reached, stopping early",
                    total_elapsed_seconds=round(total_elapsed, 2),
                    total_max_time_seconds=config.total_max_time_seconds,
                    folds_completed=len(results),
                    folds_remaining=len(folds) - len(results) - folds_skipped,
                )
                break
        
        logger.info(
            "Processing fold",
            fold_index=fold.fold_index,
            train_size=len(fold.X_train),
            test_size=len(fold.X_test),
        )
        
        fold_start_time = time.time()
        
        try:
            # Train model on this fold
            model.fit(
                X=fold.X_train,
                y=fold.y_train,
                vintage_date=config.vintage_date,
            )
            
            # Check per-fold timeout after training
            if config.max_time_per_fold_seconds is not None:
                fold_elapsed = time.time() - fold_start_time
                if fold_elapsed >= config.max_time_per_fold_seconds:
                    logger.warning(
                        "Per-fold timeout exceeded during training, skipping fold",
                        fold_index=fold.fold_index,
                        fold_elapsed_seconds=round(fold_elapsed, 2),
                        max_time_per_fold_seconds=config.max_time_per_fold_seconds,
                    )
                    folds_timed_out += 1
                    folds_skipped += 1
                    continue
            
            # Evaluate on training set
            train_predictions = model.predict(fold.X_train)
            train_metrics = compute_metrics(
                y_true=fold.y_train.values,
                y_pred=train_predictions,
            )
            
            # Evaluate on test set
            test_predictions = model.predict(fold.X_test)
            test_metrics = compute_metrics(
                y_true=fold.y_test.values,
                y_pred=test_predictions,
            )
            
            fold_elapsed = time.time() - fold_start_time
            
            # Final per-fold timeout check (including evaluation time)
            if config.max_time_per_fold_seconds is not None:
                if fold_elapsed >= config.max_time_per_fold_seconds:
                    logger.warning(
                        "Per-fold timeout exceeded after evaluation, results may be partial",
                        fold_index=fold.fold_index,
                        fold_elapsed_seconds=round(fold_elapsed, 2),
                        max_time_per_fold_seconds=config.max_time_per_fold_seconds,
                    )
                    folds_timed_out += 1
                    # Still save results since evaluation completed
            
            # Store results
            fold_result = {
                "fold_index": fold.fold_index,
                "train_metrics": train_metrics,
                "test_metrics": test_metrics,
                "train_size": len(fold.X_train),
                "test_size": len(fold.X_test),
                "train_date_range": (
                    fold.X_train.index.min().isoformat(),
                    fold.X_train.index.max().isoformat(),
                ),
                "test_date_range": (
                    fold.X_test.index.min().isoformat(),
                    fold.X_test.index.max().isoformat(),
                ),
                "elapsed_seconds": round(fold_elapsed, 3),
            }
            
            results.append(fold_result)
            
            logger.info(
                "Fold completed",
                fold_index=fold.fold_index,
                train_rmse=train_metrics["rmse"],
                test_rmse=test_metrics["rmse"],
                elapsed_seconds=round(fold_elapsed, 2),
            )
        
        except Exception as e:
            logger.error(
                "Fold processing failed",
                fold_index=fold.fold_index,
                error=str(e),
                exc_info=True,
            )
            raise
    
    total_elapsed = time.time() - cv_start_time
    
    logger.info(
        "Cross-validation completed",
        n_folds_completed=len(results),
        n_folds_skipped=folds_skipped,
        n_folds_timed_out=folds_timed_out,
        total_elapsed_seconds=round(total_elapsed, 2),
    )
    
    return results


# ============================================================================
# Metric Aggregation
# ============================================================================


def aggregate_cv_metrics(
    cv_results: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """
    Aggregate metrics across cross-validation folds.
    
    Computes summary statistics (mean, std, min, max) for each metric
    across all folds. This provides a comprehensive view of model
    performance variability.
    
    Args:
        cv_results: List of fold results from cross_validate_model()
    
    Returns:
        Dictionary with 'train' and 'test' keys, each containing:
        - {metric}_mean: Mean across folds
        - {metric}_std: Standard deviation across folds
        - {metric}_min: Minimum across folds
        - {metric}_max: Maximum across folds
        - {metric}_per_fold: List of values per fold
    
    Example:
        >>> results = cross_validate_model(data, model, config)
        >>> aggregated = aggregate_cv_metrics(results)
        >>> print(f"Mean test RMSE: {aggregated['test']['rmse_mean']:.2f} "
        ...       f"± {aggregated['test']['rmse_std']:.2f}")
    """
    logger.info(
        "Aggregating cross-validation metrics",
        n_folds=len(cv_results),
    )
    
    if not cv_results:
        raise ValueError("Cannot aggregate metrics: cv_results is empty")
    
    # Extract metric names from first fold
    metric_names = list(cv_results[0]["train_metrics"].keys())
    
    # Initialize aggregated results
    aggregated = {
        "train": {},
        "test": {},
    }
    
    # Aggregate for each split (train/test)
    for split in ["train", "test"]:
        metrics_key = f"{split}_metrics"
        
        # For each metric
        for metric_name in metric_names:
            # Collect values across all folds
            values = [
                fold_result[metrics_key][metric_name]
                for fold_result in cv_results
            ]
            
            # Compute statistics
            aggregated[split][f"{metric_name}_mean"] = float(np.mean(values))
            aggregated[split][f"{metric_name}_std"] = float(np.std(values))
            aggregated[split][f"{metric_name}_min"] = float(np.min(values))
            aggregated[split][f"{metric_name}_max"] = float(np.max(values))
            aggregated[split][f"{metric_name}_per_fold"] = [float(v) for v in values]
    
    logger.info(
        "Metric aggregation complete",
        train_rmse_mean=aggregated["train"]["rmse_mean"],
        test_rmse_mean=aggregated["test"]["rmse_mean"],
        train_rmse_std=aggregated["train"]["rmse_std"],
        test_rmse_std=aggregated["test"]["rmse_std"],
    )
    
    return aggregated

