"""
Ensemble forecasting pipeline for combining multiple models.

This module provides ensemble methods for combining predictions from multiple
forecasting models (DFM, MIDAS, GBM, etc.) to improve accuracy and robustness.

Key Features:
- Simple averaging (equal weights)
- Weighted averaging (user-defined or optimized weights)
- Weight optimization via variance minimization
- Mixed-frequency pipeline compatibility via raw-source bridge outputs
- Reproducibility (deterministic with same seed)
- Integration with BaseForecaster interface

Ensemble Methods:
1. **Simple Average**: Equal-weighted combination (1/N for each model)
   - Pros: Simple, robust, no overfitting
   - Cons: Ignores model quality differences

2. **Weighted Average**: User-specified or optimized weights
   - Pros: Can assign higher weight to better models
   - Cons: Requires validation data for optimization

3. **Stacking**: Meta-learner trained on model predictions (future extension)
   - Pros: Most flexible, can learn complex combinations
   - Cons: More complex, requires more data

Mathematical Properties:
- Variance reduction: Ensemble variance <= average individual variance
- Weight constraints: weights >= 0, sum(weights) = 1.0
- Optimization: Minimizes MSE on validation set

References:
- Granger & Ramanathan (1984): "Improved methods of combining forecasts"
- Timmermann (2006): "Forecast combinations"
- Claeskens et al. (2016): "The forecast combination puzzle"
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from enum import Enum
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from loguru import logger

from models_src.utils.base_model import BaseForecaster


# ============================================================================
# Configuration
# ============================================================================


class EnsembleMethod(str, Enum):
    """Ensemble method types."""
    SIMPLE_AVERAGE = "simple_average"
    WEIGHTED_AVERAGE = "weighted_average"
    STACKING = "stacking"  # Future extension


@dataclass
class EnsembleConfig:
    """
    Configuration for ensemble forecasting.
    
    Attributes:
        method: Ensemble method (SIMPLE_AVERAGE, WEIGHTED_AVERAGE, STACKING)
        model_names: List of model names to ensemble
        weights: Optional dict of model weights (for WEIGHTED_AVERAGE)
        optimize_weights: Whether to optimize weights on validation data
        random_state: Random seed for reproducibility
        
    Example:
        >>> config = EnsembleConfig(
        ...     method=EnsembleMethod.WEIGHTED_AVERAGE,
        ...     model_names=['dfm', 'midas', 'xgboost'],
        ...     weights={'dfm': 0.5, 'midas': 0.3, 'xgboost': 0.2}
        ... )
    """
    
    method: EnsembleMethod
    model_names: List[str]
    weights: Optional[Dict[str, float]] = None
    optimize_weights: bool = False
    random_state: int = 42
    
    def __post_init__(self):
        """Validate configuration after initialization."""
        # Validate model_names
        if not self.model_names:
            raise ValueError("model_names cannot be empty")
        
        # Validate weights if provided
        if self.weights is not None:
            self._validate_weights()
    
    def _validate_weights(self):
        """Validate weight dictionary."""
        # Check keys match model_names
        if set(self.weights.keys()) != set(self.model_names):
            raise ValueError(
                f"Weight keys {set(self.weights.keys())} must match "
                f"model_names {set(self.model_names)}"
            )
        
        # Check all weights are positive
        if any(w < 0 for w in self.weights.values()):
            raise ValueError("All weights must be positive")
        
        # Check weights sum to 1.0
        weight_sum = sum(self.weights.values())
        if abs(weight_sum - 1.0) > 1e-6:
            raise ValueError(
                f"Weights must sum to 1.0, got {weight_sum}"
            )


# ============================================================================
# Utility Functions
# ============================================================================


def validate_predictions_dict(
    predictions: Dict[str, np.ndarray],
    expected_keys: List[str]
) -> None:
    """
    Validate predictions dictionary.
    
    Args:
        predictions: Dict mapping model name to predictions array
        expected_keys: Expected model names
        
    Raises:
        ValueError: If validation fails
    """
    # Check all expected keys present
    missing_keys = set(expected_keys) - set(predictions.keys())
    if missing_keys:
        raise ValueError(f"Missing predictions for models: {missing_keys}")
    
    # Check all predictions have same length
    lengths = [len(pred) for pred in predictions.values()]
    if len(set(lengths)) > 1:
        raise ValueError(
            f"All predictions must have same length, got {dict(zip(predictions.keys(), lengths))}"
        )


def simple_average(predictions: Dict[str, np.ndarray]) -> np.ndarray:
    """
    Compute simple average of predictions.
    
    Args:
        predictions: Dict mapping model name to predictions array
        
    Returns:
        Array of averaged predictions
        
    Example:
        >>> preds = {'model1': np.array([1, 2, 3]), 'model2': np.array([2, 3, 4])}
        >>> simple_average(preds)
        array([1.5, 2.5, 3.5])
    """
    # Stack predictions into matrix (n_samples x n_models)
    pred_matrix = np.column_stack(list(predictions.values()))
    
    # Compute mean across models (axis=1)
    return pred_matrix.mean(axis=1)


def weighted_average(
    predictions: Dict[str, np.ndarray],
    weights: Dict[str, float]
) -> np.ndarray:
    """
    Compute weighted average of predictions.
    
    Args:
        predictions: Dict mapping model name to predictions array
        weights: Dict mapping model name to weight
        
    Returns:
        Array of weighted-averaged predictions
        
    Example:
        >>> preds = {'model1': np.array([1, 2, 3]), 'model2': np.array([2, 3, 4])}
        >>> weights = {'model1': 0.7, 'model2': 0.3}
        >>> weighted_average(preds, weights)
        array([1.3, 2.3, 3.3])
    """
    # Initialize result
    n_samples = len(next(iter(predictions.values())))
    result = np.zeros(n_samples)
    
    # Weighted sum
    for model_name, pred in predictions.items():
        result += weights[model_name] * pred
    
    return result


def optimize_weights(
    predictions: Dict[str, np.ndarray],
    y_true: np.ndarray,
    method: str = 'minimize_mse',
    bounds: Optional[tuple] = None,
) -> Dict[str, float]:
    """
    Optimize ensemble weights to minimize forecast error.
    
    Solves the optimization problem:
        min_w  MSE(weighted_average(predictions, w), y_true)
        s.t.   w >= 0, sum(w) = 1
    
    Args:
        predictions: Dict mapping model name to predictions array
        y_true: True target values
        method: Optimization method ('minimize_mse')
        bounds: Optional bounds for weights (default: (0, 1) for each weight)
        
    Returns:
        Dict mapping model name to optimized weight
        
    Example:
        >>> preds = {'model1': np.array([1, 2, 3]), 'model2': np.array([2, 3, 4])}
        >>> y_true = np.array([1.5, 2.5, 3.5])
        >>> weights = optimize_weights(preds, y_true)
    """
    model_names = list(predictions.keys())
    n_models = len(model_names)
    
    # Stack predictions into matrix
    pred_matrix = np.column_stack([predictions[name] for name in model_names])
    
    def objective(weights):
        """MSE objective function."""
        weighted_pred = pred_matrix @ weights
        mse = np.mean((weighted_pred - y_true) ** 2)
        return mse
    
    # Constraints: weights sum to 1
    constraints = [
        {'type': 'eq', 'fun': lambda w: np.sum(w) - 1.0}
    ]
    
    # Bounds: each weight in [0, 1]
    if bounds is None:
        bounds = [(0.0, 1.0) for _ in range(n_models)]
    
    # Initial guess: equal weights
    w0 = np.ones(n_models) / n_models
    
    # Optimize
    result = minimize(
        objective,
        w0,
        method='SLSQP',
        bounds=bounds,
        constraints=constraints,
        options={'ftol': 1e-9, 'disp': False}
    )
    
    if not result.success:
        logger.warning(
            "Weight optimization did not converge",
            message=result.message
        )
    
    # Convert to dict
    optimized_weights = {
        name: float(weight)
        for name, weight in zip(model_names, result.x)
    }
    
    logger.info(
        "Optimized ensemble weights",
        weights=optimized_weights,
        final_mse=result.fun
    )
    
    return optimized_weights


# ============================================================================
# Ensemble Forecaster
# ============================================================================


class EnsembleForecaster(BaseForecaster):
    """
    Ensemble forecaster that combines multiple models.
    
    Supports multiple ensemble methods:
    - Simple average: Equal-weighted combination
    - Weighted average: User-defined or optimized weights
    - Stacking: Meta-learning (future extension)
    
    The ensemble follows the BaseForecaster interface, so it can be used
    anywhere a single model is expected.
    
    Attributes:
        models: Dict mapping model name to model instance
        config: Ensemble configuration
        optimized_weights: Optimized weights (if optimization enabled)
        
    Example:
        >>> # Create ensemble with pre-trained monthly models
        >>> models = {'dfm': dfm_model, 'midas': midas_model, 'xgboost': xgb_model}
        >>> config = EnsembleConfig(
        ...     method=EnsembleMethod.SIMPLE_AVERAGE,
        ...     model_names=['dfm', 'midas', 'xgboost']
        ... )
        >>> ensemble = EnsembleForecaster(models=models, config=config)
        >>> predictions = ensemble.predict(X_test)
    """
    
    def __init__(
        self,
        models: Dict[str, BaseForecaster],
        config: EnsembleConfig,
    ):
        """
        Initialize ensemble forecaster.
        
        Args:
            models: Dict mapping model name to model instance
            config: Ensemble configuration
            
        Raises:
            ValueError: If model names don't match config
        """
        super().__init__(random_state=config.random_state)
        
        # Validate models match config
        if set(models.keys()) != set(config.model_names):
            raise ValueError(
                f"Model names {set(models.keys())} must match "
                f"config model_names {set(config.model_names)}"
            )
        
        self.models = models
        self.config = config
        self.optimized_weights: Optional[Dict[str, float]] = None
        
        logger.info(
            "Initialized ensemble forecaster",
            method=config.method,
            n_models=len(models),
            model_names=config.model_names,
        )
    
    def fit(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        vintage_date: str
    ) -> 'EnsembleForecaster':
        """
        Fit ensemble (optimize weights if required).
        
        Note: Individual models should already be trained. This method
        only optimizes ensemble weights using validation data.
        
        Args:
            X: Validation features (for weight optimization)
            y: Validation target (for weight optimization)
            vintage_date: Vintage date
            
        Returns:
            self: For method chaining
            
        Raises:
            ValueError: If optimization fails
        """
        self.vintage_date = vintage_date
        
        # If weight optimization is enabled, optimize weights
        if self.config.optimize_weights:
            logger.info(
                "Optimizing ensemble weights",
                n_samples=len(X),
                n_models=len(self.models)
            )
            
            # Get predictions from all models
            predictions = {
                name: model.predict(X)
                for name, model in self.models.items()
            }
            
            # Optimize weights
            self.optimized_weights = optimize_weights(
                predictions=predictions,
                y_true=y.values,
                method='minimize_mse',
            )
            
            logger.info(
                "Ensemble weights optimized",
                weights=self.optimized_weights
            )
        else:
            logger.info("No weight optimization requested")
        
        return self
    
    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """
        Generate ensemble predictions.
        
        Args:
            X: Features
            
        Returns:
            Array of ensemble predictions
            
        Raises:
            ValueError: If weight optimization required but not fitted
        """
        logger.debug(
            "Generating ensemble predictions",
            n_samples=len(X),
            method=self.config.method
        )
        
        # Check if optimization required but not done
        if self.config.optimize_weights and self.optimized_weights is None:
            raise ValueError(
                "Weight optimization enabled but weights not optimized. "
                "Call fit() before predict()."
            )
        
        # Get predictions from all models
        predictions = {
            name: model.predict(X)
            for name, model in self.models.items()
        }
        
        # Validate predictions
        validate_predictions_dict(predictions, self.config.model_names)
        
        # Combine predictions based on method
        if self.config.method == EnsembleMethod.SIMPLE_AVERAGE:
            result = simple_average(predictions)
        
        elif self.config.method == EnsembleMethod.WEIGHTED_AVERAGE:
            # Use optimized weights if available, otherwise use config weights
            if self.optimized_weights is not None:
                weights = self.optimized_weights
            elif self.config.weights is not None:
                weights = self.config.weights
            else:
                raise ValueError(
                    "WEIGHTED_AVERAGE method requires weights. "
                    "Either provide weights in config or enable optimize_weights."
                )
            
            result = weighted_average(predictions, weights)
        
        elif self.config.method == EnsembleMethod.STACKING:
            raise NotImplementedError("Stacking method not yet implemented")
        
        else:
            raise ValueError(f"Unknown ensemble method: {self.config.method}")
        
        logger.debug(
            "Ensemble predictions generated",
            n_predictions=len(result)
        )
        
        return result
    
    def get_params(self) -> Dict[str, Any]:
        """
        Get ensemble parameters.
        
        Returns:
            Dict of parameters
        """
        params = {
            'random_state': self.random_state,
            'method': self.config.method,
            'n_models': len(self.models),
            'model_names': self.config.model_names,
            'optimize_weights': self.config.optimize_weights,
        }
        
        if self.config.weights is not None:
            params['configured_weights'] = self.config.weights
        
        if self.optimized_weights is not None:
            params['optimized_weights'] = self.optimized_weights
        
        return params
    
    def save(self, path: Path) -> None:
        """
        Save ensemble to disk.
        
        Args:
            path: Path to save ensemble
            
        Note:
            This saves the ensemble configuration and optimized weights,
            but not the individual models. Individual models should be
            saved separately.
        """
        import joblib
        
        ensemble_data = {
            'config': self.config,
            'optimized_weights': self.optimized_weights,
            'model_names': list(self.models.keys()),
            'random_state': self.random_state,
            'model_id': self.model_id,
            'created_at': self.created_at,
            'vintage_date': getattr(self, 'vintage_date', None),
        }
        
        joblib.dump(ensemble_data, path)
        
        logger.info(
            "Ensemble saved",
            path=str(path)
        )
    
    @classmethod
    def load(
        cls,
        path: Path,
        models: Dict[str, BaseForecaster]
    ) -> 'EnsembleForecaster':
        """
        Load ensemble from disk.
        
        Args:
            path: Path to saved ensemble
            models: Dict of model instances (must be loaded separately)
            
        Returns:
            Loaded ensemble instance
            
        Note:
            Individual models must be loaded separately and provided
            via the models argument.
        """
        import joblib
        
        ensemble_data = joblib.load(path)
        
        # Recreate ensemble
        ensemble = cls(
            models=models,
            config=ensemble_data['config']
        )
        
        # Restore state
        ensemble.optimized_weights = ensemble_data.get('optimized_weights')
        ensemble.model_id = ensemble_data.get('model_id')
        ensemble.created_at = ensemble_data.get('created_at')
        
        if ensemble_data.get('vintage_date'):
            ensemble.vintage_date = ensemble_data['vintage_date']
        
        logger.info(
            "Ensemble loaded",
            path=str(path),
            n_models=len(models)
        )
        
        return ensemble

