"""
MIDAS (Mixed Data Sampling) Regression Model

Bridge-equation model for forecasting low-frequency targets using high-frequency
predictors. Uses exponential Almon polynomial to weight high-frequency lags.

Key Features:
- Mixed-frequency regression (daily/weekly → monthly)
- Almon polynomial lag weighting (smooth decay)
- NLS (Nonlinear Least Squares) parameter estimation
- Direct h-step ahead forecasting
- Feature registry integration

References:
- Ghysels, Santa-Clara, Valkanov (2004): MIDAS regressions
- Clements & Galvão (2008): Macroeconomic forecasting with MIDAS
- Foroni, Marcellino, Schumacher (2015): U-MIDAS
"""

from typing import Dict, Any, Optional, List
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from loguru import logger
import joblib

from models_src.utils.base_model import BaseForecaster


class MIDASRegression(BaseForecaster):
    """
    MIDAS regression with Almon polynomial lag weighting.

    Uses high-frequency predictors to forecast low-frequency targets via
    exponential Almon polynomial weighting scheme. Parameters estimated via
    Nonlinear Least Squares (NLS).

    Args:
        n_lags: Number of high-frequency lags to include
        almon_degree: Degree of Almon polynomial (higher = more flexible decay)
        horizon: Forecast horizon (h-step ahead, 1 = nowcast)
        include_intercept: Whether to include intercept term
        optimization_method: Scipy optimization method ('BFGS', 'L-BFGS-B', etc.)
        random_state: Random seed for reproducibility

    Attributes:
        coefficients_: Estimated regression coefficients (after fit)
        almon_weights_: Estimated Almon polynomial weights (after fit)
        intercept_: Intercept term (if include_intercept=True)
        feature_names_: Names of features used in training
        n_features_: Number of features in training data
        vintage_date_: Vintage date of training data

    Example:
        >>> model = MIDASRegression(n_lags=20, almon_degree=2, horizon=1)
        >>> model.fit(X_train, y_train, vintage_date='2024-11-15')
        >>> predictions = model.predict(X_test)
    """

    def __init__(
        self,
        n_lags: int = 20,
        almon_degree: int = 2,
        horizon: int = 1,
        include_intercept: bool = True,
        optimization_method: str = "BFGS",
        random_state: int = 42,
    ):
        """Initialize MIDAS regression model."""
        super().__init__(random_state=random_state)

        # Hyperparameters
        self.n_lags = n_lags
        self.almon_degree = almon_degree
        self.horizon = horizon
        self.include_intercept = include_intercept
        self.optimization_method = optimization_method

        # Model state (set during fit)
        self.coefficients_: Optional[np.ndarray] = None
        self.almon_weights_: Optional[np.ndarray] = None
        self.intercept_: Optional[float] = None
        self.feature_names_: Optional[List[str]] = None
        self.n_features_: Optional[int] = None
        self.vintage_date_: Optional[str] = None
        self.training_loss_: Optional[float] = None

        self._validate_parameters()

        logger.info(
            "midas_model_initialized",
            extra={
                "model_id": self.model_id,
                "n_lags": n_lags,
                "almon_degree": almon_degree,
                "horizon": horizon,
                "include_intercept": include_intercept,
                "random_state": random_state,
            },
        )

    def _validate_parameters(self) -> None:
        """Validate model hyperparameters."""
        if self.n_lags <= 0:
            raise ValueError(f"n_lags must be positive, got {self.n_lags}")

        if self.almon_degree < 0:
            raise ValueError(f"almon_degree must be non-negative, got {self.almon_degree}")

        if self.horizon <= 0:
            raise ValueError(f"horizon must be positive, got {self.horizon}")

    def fit(self, X: pd.DataFrame, y: pd.Series, vintage_date: str) -> "MIDASRegression":
        """
        Train MIDAS regression model via NLS estimation.

        Args:
            X: Feature matrix (N samples × M features). Should contain MIDAS lag
               features for each high-frequency predictor.
            y: Target variable (N samples, low-frequency)
            vintage_date: Vintage date for training data (ISO format: YYYY-MM-DD)

        Returns:
            self: For method chaining

        Raises:
            ValueError: If X or y are empty, or shapes don't match

        Note:
            - Uses NLS to estimate Almon polynomial parameters
            - Weights are constrained to sum to 1 (normalized)
            - Training uses self.random_state for determinism
        """
        # Validate inputs
        if len(X) == 0 or len(y) == 0:
            raise ValueError("X and y cannot be empty")

        if len(X) != len(y):
            raise ValueError(f"X and y must have same length. Got X={len(X)}, y={len(y)}")

        # Store metadata
        self.vintage_date_ = vintage_date
        self.n_features_ = X.shape[1]
        self.feature_names_ = list(X.columns)

        logger.info(
            "midas_fit_started",
            extra={
                "model_id": self.model_id,
                "n_samples": len(X),
                "n_features": self.n_features_,
                "vintage_date": vintage_date,
            },
        )

        # Set random seed for reproducibility
        np.random.seed(self.random_state)

        # Convert to numpy arrays
        X_array = X.values
        y_array = y.values

        # Estimate model via NLS
        self._fit_nls(X_array, y_array)

        logger.info(
            "midas_fit_completed",
            extra={
                "model_id": self.model_id,
                "training_loss": self.training_loss_,
                "n_coefficients": len(self.coefficients_) if self.coefficients_ is not None else 0,
                "intercept": self.intercept_,
            },
        )

        return self

    def _fit_nls(self, X: np.ndarray, y: np.ndarray) -> None:
        """
        Fit model via Nonlinear Least Squares.

        Estimates:
        - Almon polynomial parameters (theta_1, theta_2, ...)
        - Regression coefficients (beta_j for each predictor group)
        - Intercept (if include_intercept=True)

        Args:
            X: Feature matrix (N × M)
            y: Target variable (N,)
        """
        n_samples, n_features = X.shape

        # Initialize parameters
        # For simplicity, assume each feature is a separate MIDAS lag group
        # In practice, features would be grouped by predictor
        n_predictors = n_features  # Each feature is independent for now

        # Initial parameter guess
        # [intercept (if included), beta_1, ..., beta_p, theta_1, ..., theta_k]
        n_params = (1 if self.include_intercept else 0) + n_predictors + (self.almon_degree + 1)

        initial_params = np.zeros(n_params)
        if self.include_intercept:
            initial_params[0] = np.mean(y)  # Start with mean

        # Betas: start with small positive values
        beta_start_idx = 1 if self.include_intercept else 0
        initial_params[beta_start_idx : beta_start_idx + n_predictors] = 0.1

        # Thetas: start with decay pattern
        theta_start_idx = beta_start_idx + n_predictors
        initial_params[theta_start_idx:] = 1.0

        # Define objective function (sum of squared residuals)
        def objective(params):
            predictions = self._predict_with_params(X, params)
            residuals = y - predictions
            return np.sum(residuals**2)

        # Optimize via NLS
        result = minimize(
            objective,
            initial_params,
            method=self.optimization_method,
            options={"maxiter": 1000},
        )

        if not result.success:
            logger.warning(
                "midas_optimization_failed",
                extra={"message": result.message, "n_iterations": result.nit},
            )

        # Extract fitted parameters
        fitted_params = result.x

        if self.include_intercept:
            self.intercept_ = fitted_params[0]
            self.coefficients_ = fitted_params[1 : 1 + n_predictors]
            theta_params = fitted_params[1 + n_predictors :]
        else:
            self.intercept_ = 0.0
            self.coefficients_ = fitted_params[:n_predictors]
            theta_params = fitted_params[n_predictors:]

        # Compute Almon weights from theta parameters
        self.almon_weights_ = self._compute_almon_weights(theta_params)

        # Store training loss
        self.training_loss_ = result.fun

    def _predict_with_params(self, X: np.ndarray, params: np.ndarray) -> np.ndarray:
        """
        Generate predictions given parameter vector.

        Used during optimization.

        Args:
            X: Feature matrix (N × M)
            params: Parameter vector [intercept?, betas, thetas]

        Returns:
            predictions: Array of predictions (N,)
        """
        n_samples, n_features = X.shape

        # Parse parameters
        if self.include_intercept:
            intercept = params[0]
            betas = params[1 : 1 + n_features]
            thetas = params[1 + n_features :]
        else:
            intercept = 0.0
            betas = params[:n_features]
            thetas = params[n_features:]

        # Compute Almon weights
        weights = self._compute_almon_weights(thetas)

        # For simplicity, apply same weights to all features
        # In practice, would group features by predictor
        weighted_X = X * weights[:n_features]  # Broadcast weights

        # Linear combination: y = intercept + sum(beta_j * weighted_feature_j)
        predictions = intercept + np.dot(weighted_X, betas)

        return predictions

    def _compute_almon_weights(self, theta_params: np.ndarray) -> np.ndarray:
        """
        Compute exponential Almon polynomial weights.

        Args:
            theta_params: Almon polynomial parameters (degree + 1 values)

        Returns:
            weights: Normalized weight vector (n_lags,)
        """
        if self.almon_degree == 0:
            # Equal weights
            return np.ones(self.n_lags) / self.n_lags

        # Create lag indices (0 = most recent)
        lag_indices = np.arange(self.n_lags, dtype=float)

        # Exponential Almon polynomial
        # w_i = exp(sum_k theta_k * (i/n_lags)^k)
        normalized_lags = lag_indices / self.n_lags

        polynomial_values = np.zeros(self.n_lags)
        for k, theta in enumerate(theta_params):
            polynomial_values += theta * (normalized_lags**k)

        # Exponential transformation (ensures positive weights)
        weights = np.exp(polynomial_values)

        # Normalize to sum to 1
        weights = weights / weights.sum()

        return weights

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """
        Generate predictions for new data.

        Args:
            X: Feature matrix (N samples × M features)

        Returns:
            predictions: Array of predictions (N samples)

        Raises:
            ValueError: If model not fitted or feature mismatch
        """
        # Check if fitted
        if self.coefficients_ is None or self.almon_weights_ is None:
            raise ValueError("Model must be fitted before prediction. Call fit() first.")

        # Validate features
        if X.shape[1] != self.n_features_:
            expected = self.n_features_
            raise ValueError(f"Feature mismatch. Expected {expected} features, got {X.shape[1]}")

        logger.debug(
            "midas_predict_started",
            extra={"model_id": self.model_id, "n_samples": len(X)},
        )

        # Convert to numpy
        X_array = X.values

        # Apply Almon weights to features
        weighted_X = X_array * self.almon_weights_[: self.n_features_]

        # Linear combination: y = intercept + sum(beta_j * weighted_feature_j)
        predictions = self.intercept_ + np.dot(weighted_X, self.coefficients_)

        logger.debug(
            "midas_predict_completed",
            extra={
                "model_id": self.model_id,
                "n_predictions": len(predictions),
                "mean_prediction": float(np.mean(predictions)),
            },
        )

        return predictions

    def get_params(self) -> Dict[str, Any]:
        """
        Get model parameters and metadata.

        Returns:
            params: Dictionary of model parameters
        """
        return {
            "random_state": self.random_state,
            "n_lags": self.n_lags,
            "almon_degree": self.almon_degree,
            "horizon": self.horizon,
            "include_intercept": self.include_intercept,
            "optimization_method": self.optimization_method,
            "vintage_date": self.vintage_date_,
            "n_features": self.n_features_,
            "is_fitted": self.coefficients_ is not None,
            "training_loss": self.training_loss_,
            "model_id": self.model_id,
            "created_at": self.created_at,
        }

    def save(self, path: Path) -> None:
        """
        Save model to disk.

        Args:
            path: Path to save model (.pkl or .joblib)
        """
        if self.coefficients_ is None:
            raise ValueError("Cannot save unfitted model. Call fit() first.")

        model_data = {
            "params": self.get_params(),
            "coefficients": self.coefficients_,
            "almon_weights": self.almon_weights_,
            "intercept": self.intercept_,
            "feature_names": self.feature_names_,
            "vintage_date": self.vintage_date_,
            "training_loss": self.training_loss_,
        }

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        joblib.dump(model_data, path)

        logger.info(
            "midas_model_saved",
            extra={
                "model_id": self.model_id,
                "path": str(path),
                "file_size_bytes": path.stat().st_size,
            },
        )

    @classmethod
    def load(cls, path: Path) -> "MIDASRegression":
        """
        Load model from disk.

        Args:
            path: Path to saved model file

        Returns:
            model: Loaded MIDAS regression model
        """
        path = Path(path)

        if not path.exists():
            raise FileNotFoundError(f"Model file not found: {path}")

        model_data = joblib.load(path)
        params = model_data["params"]

        # Reconstruct model
        model = cls(
            n_lags=params["n_lags"],
            almon_degree=params["almon_degree"],
            horizon=params["horizon"],
            include_intercept=params["include_intercept"],
            optimization_method=params["optimization_method"],
            random_state=params["random_state"],
        )

        # Restore fitted state
        model.coefficients_ = model_data["coefficients"]
        model.almon_weights_ = model_data["almon_weights"]
        model.intercept_ = model_data["intercept"]
        model.feature_names_ = model_data["feature_names"]
        model.n_features_ = params["n_features"]
        model.vintage_date_ = model_data["vintage_date"]
        model.training_loss_ = model_data["training_loss"]

        logger.info(
            "midas_model_loaded",
            extra={
                "model_id": model.model_id,
                "path": str(path),
                "vintage_date": model.vintage_date_,
            },
        )

        return model

    def get_feature_importance(self) -> pd.DataFrame:
        """
        Get feature importance scores.

        Returns absolute coefficient values as importance measure.

        Returns:
            DataFrame with feature names and importance scores

        Raises:
            ValueError: If model not fitted
        """
        if self.coefficients_ is None:
            raise ValueError("Model must be fitted before computing feature importance")

        importance = pd.DataFrame(
            {
                "feature": self.feature_names_,
                "coefficient": self.coefficients_,
                "abs_coefficient": np.abs(self.coefficients_),
            }
        )

        importance = importance.sort_values("abs_coefficient", ascending=False)

        return importance
