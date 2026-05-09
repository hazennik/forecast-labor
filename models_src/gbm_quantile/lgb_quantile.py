"""
LightGBM Quantile Regression for probabilistic forecasting.

Multi-quantile predictions using LightGBM with quantile loss objective.
Enables prediction intervals and full predictive distributions.

Key Features:
- Multi-quantile training (5%, 10%, 25%, 50%, 75%, 90%, 95%)
- Native LightGBM quantile support (faster than iterative reweighting)
- Quantile crossing prevention via post-processing
- Feature importance tracking
- Hyperparameter tuning support
- Deterministic training via random_state

References:
- Ke et al. (2017): LightGBM: A Highly Efficient Gradient Boosting Decision Tree
- Meinshausen (2006): Quantile Regression Forests
"""

from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
import numpy as np
import pandas as pd
import lightgbm as lgb
from loguru import logger
import joblib

from models_src.utils.base_model import BaseForecaster


class LightGBMQuantile(BaseForecaster):
    """
    LightGBM model for quantile regression.

    Trains separate LightGBM models for each quantile using native quantile loss.
    Returns full predictive distribution for uncertainty quantification.

    Args:
        quantiles: List of quantiles to predict (default: [0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95])
        n_estimators: Number of boosting rounds
        max_depth: Maximum tree depth (-1 for no limit)
        learning_rate: Boosting learning rate
        num_leaves: Maximum number of leaves per tree
        subsample: Subsample ratio of training instances
        colsample_bytree: Subsample ratio of columns when constructing each tree
        prevent_crossing: Whether to enforce monotonic quantile ordering
        random_state: Random seed for reproducibility

    Attributes:
        models_: Dictionary of trained LightGBM models (one per quantile)
        feature_names_: Names of features used in training
        feature_importance_: Feature importance scores
        n_features_: Number of features in training data
        vintage_date_: Vintage date of training data

    Example:
        >>> model = LightGBMQuantile(
        ...     quantiles=[0.1, 0.5, 0.9],
        ...     n_estimators=100,
        ...     max_depth=5
        ... )
        >>> model.fit(X_train, y_train, vintage_date='2024-11-15')
        >>> predictions = model.predict(X_test)  # Returns dict of quantile predictions
    """

    DEFAULT_QUANTILES = [0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95]

    def __init__(
        self,
        quantiles: Optional[List[float]] = None,
        n_estimators: int = 100,
        max_depth: int = 5,
        learning_rate: float = 0.1,
        num_leaves: int = 31,
        subsample: float = 0.8,
        colsample_bytree: float = 0.8,
        prevent_crossing: bool = True,
        random_state: int = 42,
    ):
        """Initialize LightGBM quantile model."""
        super().__init__(random_state=random_state)

        # Hyperparameters
        self.quantiles = quantiles if quantiles is not None else self.DEFAULT_QUANTILES
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.learning_rate = learning_rate
        self.num_leaves = num_leaves
        self.subsample = subsample
        self.colsample_bytree = colsample_bytree
        self.prevent_crossing = prevent_crossing

        # Model state (set during fit)
        self.models_: Optional[Dict[float, lgb.Booster]] = None
        self.feature_names_: Optional[List[str]] = None
        self.feature_importance_: Optional[pd.DataFrame] = None
        self.n_features_: Optional[int] = None
        self.vintage_date_: Optional[str] = None

        self._validate_parameters()

        logger.info(
            "lightgbm_quantile_initialized",
            extra={
                "model_id": self.model_id,
                "quantiles": self.quantiles,
                "n_estimators": n_estimators,
                "max_depth": max_depth,
                "num_leaves": num_leaves,
                "prevent_crossing": prevent_crossing,
                "random_state": random_state,
            },
        )

    def _validate_parameters(self) -> None:
        """Validate model hyperparameters."""
        # Validate quantiles
        if len(self.quantiles) == 0:
            raise ValueError("quantiles list cannot be empty")

        for q in self.quantiles:
            if not 0 < q < 1:
                raise ValueError(f"All quantiles must be in (0, 1), got {q}")

        # Check for duplicates
        if len(self.quantiles) != len(set(self.quantiles)):
            raise ValueError("quantiles must be unique")

        # Validate other hyperparameters
        if self.n_estimators <= 0:
            raise ValueError(f"n_estimators must be positive, got {self.n_estimators}")

        if self.max_depth < -1:
            raise ValueError(f"max_depth must be >= -1, got {self.max_depth}")

        if not 0 < self.learning_rate <= 1:
            raise ValueError(f"learning_rate must be in (0, 1], got {self.learning_rate}")

        if self.num_leaves <= 1:
            raise ValueError(f"num_leaves must be > 1, got {self.num_leaves}")

        if not 0 < self.subsample <= 1:
            raise ValueError(f"subsample must be in (0, 1], got {self.subsample}")

        if not 0 < self.colsample_bytree <= 1:
            raise ValueError(f"colsample_bytree must be in (0, 1], got {self.colsample_bytree}")

    def fit(self, X: pd.DataFrame, y: pd.Series, vintage_date: str) -> "LightGBMQuantile":
        """
        Train LightGBM quantile models.

        Trains one LightGBM model per quantile using native quantile loss objective.

        Args:
            X: Feature matrix (N samples × M features)
            y: Target variable (N samples)
            vintage_date: Vintage date for training data (ISO format: YYYY-MM-DD)

        Returns:
            self: For method chaining

        Raises:
            ValueError: If X or y are empty, or shapes don't match
        """
        # Validate inputs
        if len(X) == 0 or len(y) == 0:
            raise ValueError("X and y cannot be empty")

        if len(X) != len(y):
            raise ValueError(f"X and y must have same length. Got X={len(X)}, y={len(y)}")

        # Store metadata
        self.vintage_date_ = vintage_date
        self.n_features_ = X.shape[1]

        # Ensure feature names are strings (LightGBM requirement)
        if X.columns.dtype == "object":
            self.feature_names_ = [str(name) for name in X.columns]
        else:
            # Integer column names - convert to strings
            self.feature_names_ = [f"f_{i}" for i in range(X.shape[1])]

        logger.info(
            "lightgbm_quantile_fit_started",
            extra={
                "model_id": self.model_id,
                "n_samples": len(X),
                "n_features": self.n_features_,
                "n_quantiles": len(self.quantiles),
                "vintage_date": vintage_date,
            },
        )

        # Convert to numpy arrays
        X_array = X.values
        y_array = y.values

        # Train one model per quantile
        self.models_ = {}

        for quantile in self.quantiles:
            logger.debug(
                "training_quantile_model", extra={"quantile": quantile, "model_id": self.model_id}
            )

            # LightGBM parameters for quantile regression
            params = {
                "objective": "quantile",
                "alpha": quantile,  # Quantile level
                "metric": "quantile",
                "max_depth": self.max_depth,
                "learning_rate": self.learning_rate,
                "num_leaves": self.num_leaves,
                "subsample": self.subsample,
                "colsample_bytree": self.colsample_bytree,
                "random_state": self.random_state,
                "verbosity": -1,  # Suppress output
            }

            # Create LightGBM dataset
            train_data = lgb.Dataset(
                X_array, label=y_array, feature_name=self.feature_names_, free_raw_data=False
            )

            # Train model
            model = lgb.train(params, train_data, num_boost_round=self.n_estimators)

            self.models_[quantile] = model

        # Compute feature importance (using median model)
        self._compute_feature_importance()

        logger.info(
            "lightgbm_quantile_fit_completed",
            extra={"model_id": self.model_id, "n_models_trained": len(self.models_)},
        )

        return self

    def _compute_feature_importance(self) -> None:
        """Compute feature importance scores."""
        if self.models_ is None or len(self.models_) == 0:
            return

        # Use median model for feature importance
        median_quantile = 0.5
        if median_quantile not in self.models_:
            # Use first available quantile if median not available
            median_quantile = list(self.models_.keys())[0]

        model = self.models_[median_quantile]

        # Get feature importance from LightGBM
        importance_scores = model.feature_importance(importance_type="gain")

        # Convert to DataFrame
        importance_data = []
        for i, (feature_name, score) in enumerate(zip(self.feature_names_, importance_scores)):
            importance_data.append({"feature": feature_name, "importance": float(score)})

        self.feature_importance_ = pd.DataFrame(importance_data)
        self.feature_importance_ = self.feature_importance_.sort_values(
            "importance", ascending=False
        ).reset_index(drop=True)

    def predict(self, X: pd.DataFrame) -> Dict[float, np.ndarray]:
        """
        Generate quantile predictions for new data.

        Args:
            X: Feature matrix (N samples × M features)

        Returns:
            predictions: Dictionary mapping quantile → predictions array
                Example: {0.1: array([...]), 0.5: array([...]), 0.9: array([...])}

        Raises:
            ValueError: If model not fitted or feature mismatch
        """
        # Check if fitted
        if self.models_ is None:
            raise ValueError("Model must be fitted before prediction. Call fit() first.")

        # Validate features
        if X.shape[1] != self.n_features_:
            raise ValueError(
                f"Feature mismatch. Expected {self.n_features_} features, got {X.shape[1]}"
            )

        logger.debug(
            "lightgbm_quantile_predict_started",
            extra={
                "model_id": self.model_id,
                "n_samples": len(X),
                "n_quantiles": len(self.quantiles),
            },
        )

        # Convert to numpy array
        X_array = X.values

        # Generate predictions for each quantile
        predictions = {}
        for quantile, model in self.models_.items():
            predictions[quantile] = model.predict(X_array)

        # Prevent quantile crossing if requested
        if self.prevent_crossing:
            predictions = self._prevent_quantile_crossing(predictions)

        logger.debug(
            "lightgbm_quantile_predict_completed",
            extra={"model_id": self.model_id, "n_predictions": len(X)},
        )

        return predictions

    def _prevent_quantile_crossing(
        self, predictions: Dict[float, np.ndarray]
    ) -> Dict[float, np.ndarray]:
        """
        Ensure quantile predictions are monotonically increasing.

        Uses isotonic regression to enforce q1 < q2 < ... < qn ordering.

        Args:
            predictions: Dictionary of quantile predictions

        Returns:
            corrected_predictions: Predictions with crossing prevented
        """
        from sklearn.isotonic import IsotonicRegression

        # Sort quantiles
        sorted_quantiles = sorted(predictions.keys())
        n_samples = len(predictions[sorted_quantiles[0]])

        # For each sample, enforce monotonicity
        corrected = {q: np.zeros(n_samples) for q in sorted_quantiles}

        for i in range(n_samples):
            # Extract predictions for this sample across quantiles
            sample_preds = [predictions[q][i] for q in sorted_quantiles]

            # Apply isotonic regression to enforce monotonicity
            iso = IsotonicRegression(increasing=True)
            corrected_preds = iso.fit_transform(sorted_quantiles, sample_preds)

            # Store corrected predictions
            for j, q in enumerate(sorted_quantiles):
                corrected[q][i] = corrected_preds[j]

        return corrected

    def get_params(self) -> Dict[str, Any]:
        """
        Get model parameters and metadata.

        Returns:
            params: Dictionary of model parameters
        """
        return {
            "random_state": self.random_state,
            "quantiles": self.quantiles,
            "n_estimators": self.n_estimators,
            "max_depth": self.max_depth,
            "learning_rate": self.learning_rate,
            "num_leaves": self.num_leaves,
            "subsample": self.subsample,
            "colsample_bytree": self.colsample_bytree,
            "prevent_crossing": self.prevent_crossing,
            "vintage_date": self.vintage_date_,
            "n_features": self.n_features_,
            "is_fitted": self.models_ is not None,
            "model_id": self.model_id,
            "created_at": self.created_at,
        }

    def save(self, path: Path) -> None:
        """
        Save model to disk.

        Args:
            path: Path to save model (.pkl or .joblib)
        """
        if self.models_ is None:
            raise ValueError("Cannot save unfitted model. Call fit() first.")

        model_data = {
            "params": self.get_params(),
            "models": self.models_,
            "feature_names": self.feature_names_,
            "feature_importance": self.feature_importance_,
            "vintage_date": self.vintage_date_,
        }

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        joblib.dump(model_data, path)

        logger.info(
            "lightgbm_quantile_saved",
            extra={
                "model_id": self.model_id,
                "path": str(path),
                "file_size_bytes": path.stat().st_size,
            },
        )

    @classmethod
    def load(cls, path: Path) -> "LightGBMQuantile":
        """
        Load model from disk.

        Args:
            path: Path to saved model file

        Returns:
            model: Loaded LightGBM quantile model
        """
        path = Path(path)

        if not path.exists():
            raise FileNotFoundError(f"Model file not found: {path}")

        model_data = joblib.load(path)
        params = model_data["params"]

        # Reconstruct model
        model = cls(
            quantiles=params["quantiles"],
            n_estimators=params["n_estimators"],
            max_depth=params["max_depth"],
            learning_rate=params["learning_rate"],
            num_leaves=params["num_leaves"],
            subsample=params["subsample"],
            colsample_bytree=params["colsample_bytree"],
            prevent_crossing=params["prevent_crossing"],
            random_state=params["random_state"],
        )

        # Restore fitted state
        model.models_ = model_data["models"]
        model.feature_names_ = model_data["feature_names"]
        model.feature_importance_ = model_data["feature_importance"]
        model.n_features_ = params["n_features"]
        model.vintage_date_ = model_data["vintage_date"]

        logger.info(
            "lightgbm_quantile_loaded",
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

        Returns:
            DataFrame with feature names and importance scores

        Raises:
            ValueError: If model not fitted
        """
        if self.feature_importance_ is None:
            raise ValueError("Model must be fitted before computing feature importance")

        return self.feature_importance_.copy()

    def get_prediction_intervals(
        self, predictions: Dict[float, np.ndarray], confidence_level: float = 0.9
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Extract prediction intervals from quantile predictions.

        Args:
            predictions: Dictionary of quantile predictions
            confidence_level: Confidence level (e.g., 0.9 for 90% interval)

        Returns:
            lower: Lower bounds of prediction interval
            upper: Upper bounds of prediction interval

        Example:
            >>> predictions = model.predict(X_test)
            >>> lower, upper = model.get_prediction_intervals(predictions, confidence_level=0.9)
        """
        alpha = (1 - confidence_level) / 2
        lower_quantile = alpha
        upper_quantile = 1 - alpha

        # Find closest quantiles (handle floating point precision)
        available_quantiles = list(predictions.keys())

        def find_closest_quantile(target_q):
            """Find closest available quantile to target."""
            closest = min(available_quantiles, key=lambda x: abs(x - target_q))
            if abs(closest - target_q) > 0.01:  # Tolerance of 1%
                raise ValueError(
                    f"No quantile close to {target_q:.3f} found. "
                    f"Available quantiles: {sorted(available_quantiles)}"
                )
            return closest

        lower_q = find_closest_quantile(lower_quantile)
        upper_q = find_closest_quantile(upper_quantile)

        return predictions[lower_q], predictions[upper_q]
