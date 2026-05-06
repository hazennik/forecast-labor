"""
Training pipelines for forecasting models.

This module provides orchestrated workflows for model training, including:
- Vintage-aware data splitting
- Model training and evaluation
- Time-series cross-validation
- MLflow experiment tracking
- Model persistence with metadata
- Feature registry integration
"""

from models_src.pipelines.train_pipeline import (
    TrainingConfig,
    TrainingSplit,
    create_time_series_splits,
    train_model,
    evaluate_model,
    train_pipeline,
)

from models_src.pipelines.cross_validation import (
    CrossValidationConfig,
    CVFold,
    generate_expanding_window_folds,
    cross_validate_model,
    aggregate_cv_metrics,
)

from models_src.pipelines.mixed_frequency_pipeline import (
    MixedFrequencyPipeline,
    MixedFrequencyPipelineConfig,
)

__all__ = [
    # Training pipeline
    "TrainingConfig",
    "TrainingSplit",
    "create_time_series_splits",
    "train_model",
    "evaluate_model",
    "train_pipeline",
    # Cross-validation
    "CrossValidationConfig",
    "CVFold",
    "generate_expanding_window_folds",
    "cross_validate_model",
    "aggregate_cv_metrics",
    # Mixed-frequency pipeline
    "MixedFrequencyPipeline",
    "MixedFrequencyPipelineConfig",
]

