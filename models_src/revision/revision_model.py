"""
Revision Forecasting Model

Predicts how preliminary NFP values will be revised in subsequent releases.
Revisions are systematic and partially predictable based on:
- Preliminary value magnitude
- Leading indicators (claims, surveys)
- Historical revision patterns
- Data quality signals

Key Features:
- Revision magnitude prediction (RMSE-optimized)
- Revision direction classification (up/down)
- Ridge regression with L2 regularization
- Deterministic training (reproducible with same seed)
- Feature registry integration

References:
- Faust et al. (2005): "Revisions of Employment Data"
- Croushore & Stark (2001): "A Real-Time Data Set for Macroeconomists"
- Aruoba (2008): "Data Revisions Are Not Well Behaved"
"""

from typing import Dict, Any, Optional
from pathlib import Path
import re

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from loguru import logger
import joblib

from models_src.utils.base_model import BaseForecaster


class RevisionForecaster(BaseForecaster):
    """
    Forecast preliminary NFP revisions using Ridge regression.
    
    Predicts the revision (final - preliminary) based on:
    1. Preliminary value features (magnitude, recent growth)
    2. Leading indicators (UI claims, surveys, Treasury withholdings)
    3. Historical revision patterns (mean reversion)
    4. Data quality signals (seasonal adjustment flags, sample sizes)
    
    Model:
        revision = β₀ + β₁*prelim + β₂*indicators + β₃*history + ε
    
    Where revision = final_value - preliminary_value
    
    Parameters:
        alpha: L2 regularization strength (higher = more regularization)
        fit_intercept: Whether to include intercept term
        random_state: Random seed for reproducibility
        
    Attributes:
        model_: Fitted Ridge regression model (after fit)
        scaler_: StandardScaler for features (after fit)
        feature_names_: Names of features used in training (after fit)
        n_features_: Number of features in training data (after fit)
        vintage_date_: Vintage date of training data (after fit)
        
    Example:
        ```python
        # Create and fit model
        model = RevisionForecaster(alpha=1.0, random_state=42)
        model.fit(X_train, y_train, vintage_date='2024-11-15')
        
        # Predict revisions
        revision_forecasts = model.predict(X_test)
        
        # Interpret: negative = downward revision, positive = upward revision
        ```
    """
    
    def __init__(
        self,
        alpha: float = 1.0,
        fit_intercept: bool = True,
        random_state: int = 42
    ):
        """
        Initialize revision forecaster.
        
        Args:
            alpha: L2 regularization strength (higher = more regularization, 
                   reduces overfitting to noisy historical revision patterns)
            fit_intercept: Whether to include intercept (True recommended)
            random_state: Random seed for reproducibility
            
        Raises:
            ValueError: If alpha is negative
        """
        super().__init__(random_state=random_state)
        
        # Validate parameters
        if alpha < 0:
            raise ValueError(f"alpha must be non-negative, got {alpha}")
        
        self.alpha = alpha
        self.fit_intercept = fit_intercept
        
        # Fitted attributes (set during fit)
        self.model_: Optional[Ridge] = None
        self.scaler_: Optional[StandardScaler] = None
        self.feature_names_: Optional[list] = None
        self.n_features_: Optional[int] = None
        self.vintage_date_: Optional[str] = None
        self.training_rmse_: Optional[float] = None
        
        logger.info(
            "Initialized RevisionForecaster",
            alpha=alpha,
            fit_intercept=fit_intercept,
            random_state=random_state
        )
    
    def fit(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        vintage_date: str
    ) -> 'RevisionForecaster':
        """
        Train revision forecasting model.
        
        Fits Ridge regression to predict revisions from features. Automatically
        standardizes features (zero mean, unit variance) for stable training.
        
        Args:
            X: Feature matrix (N_samples x N_features)
               Expected features: preliminary values, leading indicators,
               historical revision statistics
            y: Target revisions (N_samples)
               Computed as: revision = final_value - preliminary_value
            vintage_date: Training data vintage (YYYY-MM-DD format)
            
        Returns:
            self: For method chaining
            
        Raises:
            ValueError: If inputs invalid or vintage_date malformed
            
        Example:
            ```python
            # Prepare revision data
            X = pd.DataFrame({
                'preliminary_value': [200, 150, 180],
                'claims_4wk_avg': [220, 230, 215],
                'prev_revision_avg': [10, -5, 8]
            })
            y = pd.Series([15, -10, 12])  # Actual revisions
            
            # Fit model
            model = RevisionForecaster(alpha=1.0, random_state=42)
            model.fit(X, y, vintage_date='2024-11-15')
            ```
        """
        # Validate inputs
        self._validate_fit_inputs(X, y, vintage_date)
        
        # Store metadata
        self.vintage_date_ = vintage_date
        self.n_features_ = X.shape[1]
        self.feature_names_ = list(X.columns)
        
        # Store feature metadata for registry integration
        self.feature_metadata_ = {
            'feature_names': self.feature_names_,
            'vintage_date': vintage_date,
            'n_features': self.n_features_
        }
        
        logger.info(
            "Starting revision model training",
            n_samples=len(X),
            n_features=self.n_features_,
            vintage_date=vintage_date,
            alpha=self.alpha
        )
        
        # Set random seed for reproducibility
        np.random.seed(self.random_state)
        
        # Standardize features (critical for Ridge regression)
        self.scaler_ = StandardScaler()
        X_scaled = self.scaler_.fit_transform(X)
        
        # Fit Ridge regression
        self.model_ = Ridge(
            alpha=self.alpha,
            fit_intercept=self.fit_intercept,
            random_state=self.random_state
        )
        self.model_.fit(X_scaled, y.values)
        
        # Compute training RMSE for diagnostics
        y_pred_train = self.model_.predict(X_scaled)
        self.training_rmse_ = np.sqrt(np.mean((y.values - y_pred_train) ** 2))
        
        # Log training completion
        logger.info(
            "Revision model training complete",
            training_rmse=self.training_rmse_,
            n_coefficients=len(self.model_.coef_),
            intercept=self.model_.intercept_ if self.fit_intercept else 0.0
        )
        
        return self
    
    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """
        Predict revisions for new preliminary values.
        
        Args:
            X: Feature matrix (N_samples x N_features)
               Must have same features as training data
            
        Returns:
            predictions: Array of predicted revisions (N_samples)
                        Positive = upward revision expected
                        Negative = downward revision expected
                        
        Raises:
            ValueError: If model not fitted or feature mismatch
            
        Example:
            ```python
            # New preliminary releases
            X_new = pd.DataFrame({
                'preliminary_value': [190],
                'claims_4wk_avg': [225],
                'prev_revision_avg': [5]
            })
            
            # Predict revision
            revision_forecast = model.predict(X_new)
            print(f"Expected revision: {revision_forecast[0]:.1f}K")
            ```
        """
        # Check if fitted
        if self.model_ is None:
            raise ValueError(
                "Model must be fitted before prediction. Call fit() first."
            )
        
        # Validate feature count matches
        if X.shape[1] != self.n_features_:
            raise ValueError(
                f"Feature mismatch: Expected {self.n_features_} features, "
                f"got {X.shape[1]}"
            )
        
        # Standardize features using fitted scaler
        X_scaled = self.scaler_.transform(X)
        
        # Generate predictions
        predictions = self.model_.predict(X_scaled)
        
        logger.debug(
            "Generated revision predictions",
            n_predictions=len(predictions),
            mean_revision=np.mean(predictions),
            std_revision=np.std(predictions)
        )
        
        return predictions
    
    def get_params(self) -> Dict[str, Any]:
        """
        Get model parameters and metadata.
        
        Returns:
            Dictionary containing:
            - Model hyperparameters (alpha, fit_intercept, random_state)
            - Fitted state (is_fitted, vintage_date, n_features)
            - Training diagnostics (training_rmse)
            - Feature information (feature_names)
            - Model metadata (model_id, created_at)
        """
        params = {
            # Hyperparameters
            'alpha': self.alpha,
            'fit_intercept': self.fit_intercept,
            'random_state': self.random_state,
            
            # Model metadata
            'model_id': str(self.model_id),
            'created_at': self.created_at,  # Already a string from BaseForecaster
            
            # Fitted state
            'is_fitted': self.model_ is not None,
            'vintage_date': self.vintage_date_,
            'n_features': self.n_features_,
            'feature_names': self.feature_names_,
            
            # Training diagnostics
            'training_rmse': self.training_rmse_,
        }
        
        # Add coefficients if fitted
        if self.model_ is not None:
            params['coefficients'] = self.model_.coef_.tolist()
            params['intercept'] = float(self.model_.intercept_)
        
        return params
    
    def get_feature_importance(self) -> pd.DataFrame:
        """
        Get feature importance based on absolute coefficient magnitudes.
        
        Returns:
            DataFrame with columns:
            - feature: Feature name
            - coefficient: Ridge coefficient (raw)
            - abs_coefficient: Absolute coefficient magnitude
            - direction: Impact direction ('positive' or 'negative')
            
        Raises:
            ValueError: If model not fitted
            
        Note:
            Coefficients are for standardized features, so magnitudes
            are directly comparable for feature importance ranking.
            
        Example:
            ```python
            importance = model.get_feature_importance()
            print(importance.head())
            
            # Top 3 most important features
            top_3 = importance.head(3)['feature'].tolist()
            ```
        """
        if self.model_ is None:
            raise ValueError(
                "Model must be fitted before computing feature importance. "
                "Call fit() first."
            )
        
        # Create DataFrame with feature coefficients
        importance_df = pd.DataFrame({
            'feature': self.feature_names_,
            'coefficient': self.model_.coef_,
            'abs_coefficient': np.abs(self.model_.coef_)
        })
        
        # Add direction indicator
        importance_df['direction'] = importance_df['coefficient'].apply(
            lambda x: 'positive' if x > 0 else 'negative'
        )
        
        # Sort by absolute magnitude (descending)
        importance_df = importance_df.sort_values(
            'abs_coefficient', 
            ascending=False
        ).reset_index(drop=True)
        
        return importance_df
    
    def save(self, path: Path) -> None:
        """
        Save fitted model to disk.
        
        Args:
            path: Path to save model (will create .pkl file)
            
        Raises:
            ValueError: If model not fitted
            IOError: If save fails
        """
        if self.model_ is None:
            raise ValueError("Cannot save unfitted model. Call fit() first.")
        
        try:
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            
            # Save entire model state
            model_state = {
                'model': self.model_,
                'scaler': self.scaler_,
                'feature_names': self.feature_names_,
                'n_features': self.n_features_,
                'vintage_date': self.vintage_date_,
                'training_rmse': self.training_rmse_,
                'alpha': self.alpha,
                'fit_intercept': self.fit_intercept,
                'random_state': self.random_state,
                'model_id': str(self.model_id),
                'created_at': self.created_at,  # Already a string from BaseForecaster
            }
            
            joblib.dump(model_state, path)
            
            logger.info(
                "Saved revision model",
                path=str(path),
                model_id=str(self.model_id)
            )
        except Exception as e:
            logger.error(
                "Failed to save revision model",
                path=str(path),
                error=str(e),
                exc_info=True
            )
            raise IOError(f"Failed to save model to {path}: {e}") from e
    
    @classmethod
    def load(cls, path: Path) -> 'RevisionForecaster':
        """
        Load fitted model from disk.
        
        Args:
            path: Path to saved model (.pkl file)
            
        Returns:
            Loaded RevisionForecaster instance
            
        Raises:
            FileNotFoundError: If model file doesn't exist
            IOError: If load fails
        """
        path = Path(path)
        
        if not path.exists():
            raise FileNotFoundError(
                f"Model file not found: {path}"
            )
        
        try:
            # Load model state
            model_state = joblib.load(path)
            
            # Create new instance
            instance = cls(
                alpha=model_state['alpha'],
                fit_intercept=model_state['fit_intercept'],
                random_state=model_state['random_state']
            )
            
            # Restore fitted state
            instance.model_ = model_state['model']
            instance.scaler_ = model_state['scaler']
            instance.feature_names_ = model_state['feature_names']
            instance.n_features_ = model_state['n_features']
            instance.vintage_date_ = model_state['vintage_date']
            instance.training_rmse_ = model_state['training_rmse']
            instance.model_id = model_state['model_id']
            instance.created_at = model_state['created_at']  # Already a string
            
            logger.info(
                "Loaded revision model",
                path=str(path),
                model_id=model_state['model_id'],
                vintage_date=model_state['vintage_date']
            )
            
            return instance
            
        except Exception as e:
            logger.error(
                "Failed to load revision model",
                path=str(path),
                error=str(e),
                exc_info=True
            )
            raise IOError(f"Failed to load model from {path}: {e}") from e
    
    def _validate_fit_inputs(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        vintage_date: str
    ) -> None:
        """
        Validate inputs for fit method.
        
        Args:
            X: Feature matrix
            y: Target values
            vintage_date: Vintage date string
            
        Raises:
            ValueError: If inputs are invalid
        """
        # Check for empty data
        if len(X) == 0 or len(y) == 0:
            raise ValueError("X and y cannot be empty")
        
        # Check for length mismatch
        if len(X) != len(y):
            raise ValueError(
                f"X and y must have same length. Got X: {len(X)}, y: {len(y)}"
            )
        
        # Check for NaN values
        if X.isna().any().any():
            raise ValueError("X contains NaN values. Remove missing data first.")
        
        if y.isna().any():
            raise ValueError("y contains NaN values. Remove missing data first.")
        
        # Validate vintage date format (YYYY-MM-DD)
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', vintage_date):
            raise ValueError(
                f"vintage_date must be in YYYY-MM-DD format, got {vintage_date}"
            )

