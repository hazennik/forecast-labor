"""
Base classes for forecasting models

Defines abstract interface that all forecasting models must implement.
Ensures consistency across DFM, MIDAS, GBM, and other model types.

Key Features:
- Deterministic training via random_state
- Vintage-aware interface (reproducibility)
- Abstract method enforcement
- Consistent model lifecycle (fit/predict/save/load)
- Model metadata tracking
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from pathlib import Path
from datetime import datetime
import uuid

import pandas as pd
import numpy as np
from loguru import logger


class BaseForecaster(ABC):
    """
    Abstract base class for all forecasting models.
    
    All forecasting models (DFM, MIDAS, GBM, etc.) must inherit from this class
    and implement the abstract methods. This ensures:
    - Consistent interface across all models
    - Deterministic training (via random_state)
    - Vintage-aware training (reproducibility)
    - Model metadata tracking
    
    Attributes:
        random_state: Random seed for reproducibility
        model_id: Unique identifier for this model instance
        created_at: Timestamp when model was created
        
    Example:
        ```python
        class MyModel(BaseForecaster):
            def fit(self, X, y, vintage_date):
                # Training logic
                return self
            
            def predict(self, X):
                # Prediction logic
                return predictions
            
            def get_params(self):
                return {'random_state': self.random_state}
        
        model = MyModel(random_state=42)
        model.fit(X_train, y_train, vintage_date='2024-11-15')
        predictions = model.predict(X_test)
        ```
    """
    
    def __init__(self, random_state: int = 42):
        """
        Initialize base forecaster.
        
        Args:
            random_state: Random seed for reproducibility. Same seed guarantees
                identical results across runs (determinism).
                
        Note:
            All subclasses should call super().__init__(random_state) in their
            __init__ method to ensure proper initialization.
        """
        self.random_state = random_state
        self.model_id = str(uuid.uuid4())
        self.created_at = datetime.now().isoformat()
        
        logger.debug(
            f"Initialized {self.__class__.__name__}",
            extra={
                'model_id': self.model_id,
                'random_state': random_state,
                'created_at': self.created_at
            }
        )
    
    @abstractmethod
    def fit(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        vintage_date: str
    ) -> 'BaseForecaster':
        """
        Train the model on provided data.
        
        This method MUST be implemented by all subclasses.
        
        Args:
            X: Feature matrix (N samples × M features)
            y: Target variable (N samples)
            vintage_date: Vintage date for the training data (ISO format: YYYY-MM-DD).
                Critical for reproducibility - same vintage + same seed = same model.
                
        Returns:
            self: For method chaining (model.fit().predict())
            
        Raises:
            NotImplementedError: If subclass doesn't implement this method
            
        Note:
            - Must store vintage_date for reproducibility tracking
            - Must use self.random_state for any randomness
            - Should validate inputs (X shape, y length, vintage format)
            - Should log training progress
            
        Example:
            ```python
            def fit(self, X, y, vintage_date):
                self.vintage_date = vintage_date
                self.n_features = X.shape[1]
                
                # Use random_state for determinism
                np.random.seed(self.random_state)
                self.model = train_model(X, y)
                
                return self
            ```
        """
        pass
    
    @abstractmethod
    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """
        Generate predictions for new data.
        
        This method MUST be implemented by all subclasses.
        
        Args:
            X: Feature matrix (N samples × M features)
            
        Returns:
            predictions: Array of predictions (N samples)
            
        Raises:
            NotImplementedError: If subclass doesn't implement this method
            ValueError: If model not fitted (call fit() first)
            
        Note:
            - Must check if model is fitted before predicting
            - Must validate input features match training features
            - Should use self.random_state for any randomness
            - Should log prediction metadata
            
        Example:
            ```python
            def predict(self, X):
                if not hasattr(self, 'model'):
                    raise ValueError("Model must be fitted before prediction")
                
                predictions = self.model.predict(X)
                return predictions
            ```
        """
        pass
    
    @abstractmethod
    def get_params(self) -> Dict[str, Any]:
        """
        Get model parameters and metadata.
        
        This method MUST be implemented by all subclasses.
        
        Returns:
            params: Dictionary of model parameters and metadata
            
        Note:
            - Must include 'random_state'
            - Should include 'vintage_date' if fitted
            - Should include hyperparameters
            - Should include model state (is_fitted, etc.)
            
        Example:
            ```python
            def get_params(self):
                return {
                    'random_state': self.random_state,
                    'vintage_date': getattr(self, 'vintage_date', None),
                    'n_features': getattr(self, 'n_features', None),
                    'is_fitted': hasattr(self, 'model'),
                    'hyperparameter_1': self.hyperparam_1,
                }
            ```
        """
        pass
    
    def save(self, path: Path) -> None:
        """
        Save model to disk.
        
        Default implementation raises NotImplementedError.
        Subclasses should override to implement model-specific serialization.
        
        Args:
            path: Path to save model (should be .pkl or .joblib)
            
        Raises:
            NotImplementedError: If subclass doesn't implement this method
            
        Note:
            - Should save model state + metadata
            - Should use joblib or pickle for serialization
            - Should include vintage_date in saved metadata
            - Should log save operation
            
        Example:
            ```python
            def save(self, path):
                import joblib
                
                model_data = {
                    'model': self.model,
                    'params': self.get_params(),
                    'vintage_date': self.vintage_date,
                    'feature_names': self.feature_names,
                }
                
                joblib.dump(model_data, path)
                logger.info(f"Model saved to {path}")
            ```
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement save() method"
        )
    
    @classmethod
    def load(cls, path: Path) -> 'BaseForecaster':
        """
        Load model from disk.
        
        Default implementation raises NotImplementedError.
        Subclasses should override to implement model-specific deserialization.
        
        Args:
            path: Path to saved model file
            
        Returns:
            model: Loaded model instance
            
        Raises:
            NotImplementedError: If subclass doesn't implement this method
            
        Note:
            - Should restore full model state
            - Should restore metadata (vintage_date, params, etc.)
            - Should validate loaded model integrity
            - Should log load operation
            
        Example:
            ```python
            @classmethod
            def load(cls, path):
                import joblib
                
                model_data = joblib.load(path)
                
                # Reconstruct model
                model = cls(random_state=model_data['params']['random_state'])
                model.model = model_data['model']
                model.vintage_date = model_data['vintage_date']
                model.feature_names = model_data['feature_names']
                
                logger.info(f"Model loaded from {path}")
                return model
            ```
        """
        raise NotImplementedError(
            f"{cls.__name__} must implement load() class method"
        )
    
    def __repr__(self) -> str:
        """String representation of model"""
        return (
            f"{self.__class__.__name__}("
            f"random_state={self.random_state}, "
            f"model_id={self.model_id[:8]}...)"
        )
    
    def __str__(self) -> str:
        """Human-readable string representation"""
        params = self.get_params() if hasattr(self, 'get_params') else {}
        is_fitted = params.get('is_fitted', False)
        vintage = params.get('vintage_date', 'N/A')
        
        return (
            f"{self.__class__.__name__}\n"
            f"  Random State: {self.random_state}\n"
            f"  Model ID: {self.model_id[:8]}...\n"
            f"  Fitted: {is_fitted}\n"
            f"  Vintage Date: {vintage}\n"
            f"  Created: {self.created_at}"
        )

