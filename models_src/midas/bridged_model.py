"""
MIDAS regression wrapper that accepts raw mixed-frequency sources.

MIDASBridgedRegression keeps the existing MIDASRegression estimator intact and
adds the missing bridge step: raw ETL outputs -> monthly MIDAS features -> model.
"""

from pathlib import Path
from typing import Any, Dict, Mapping, Optional

import joblib
import numpy as np
import pandas as pd
from loguru import logger

from features.midas.bridge import MIDASBridge, RawSource
from features.midas.source_config import SourceConfig
from models_src.midas.midas_model import MIDASRegression
from models_src.utils.base_model import BaseForecaster


class MIDASBridgedRegression(BaseForecaster):
    """
    MIDAS forecaster that builds features from raw mixed-frequency data.

    Args:
        source_configs: Source extraction configs for the bridge.
        almon_degree: Exponential Almon polynomial degree.
        horizon: Forecast horizon for the underlying MIDAS model.
        include_intercept: Whether the underlying regression includes an intercept.
        optimization_method: Scipy optimization method used by MIDASRegression.
        random_state: Random seed for reproducibility.
    """

    def __init__(
        self,
        source_configs: Optional[Mapping[str, SourceConfig]] = None,
        almon_degree: int = 2,
        horizon: int = 1,
        include_intercept: bool = True,
        optimization_method: str = "BFGS",
        random_state: int = 42,
    ) -> None:
        """Initialize the bridged MIDAS forecaster."""
        super().__init__(random_state=random_state)
        self.source_configs = (
            dict(source_configs) if source_configs is not None else None
        )
        self.almon_degree = almon_degree
        self.horizon = horizon
        self.include_intercept = include_intercept
        self.optimization_method = optimization_method

        self.bridge_: Optional[MIDASBridge] = None
        self.model_: Optional[MIDASRegression] = None
        self.feature_names_: Optional[list[str]] = None
        self.vintage_date_: Optional[str] = None

    def fit(
        self,
        X: Mapping[str, RawSource],
        y: pd.Series,
        vintage_date: str,
    ) -> "MIDASBridgedRegression":
        """
        Fit the model from raw source data and monthly targets.

        Args:
            X: Raw mixed-frequency source mapping.
            y: Monthly target series with a DatetimeIndex.
            vintage_date: Vintage date for reproducibility.

        Returns:
            self for method chaining.
        """
        if not isinstance(y.index, pd.DatetimeIndex):
            raise ValueError("y must use a DatetimeIndex so target dates are explicit")
        if y.empty:
            raise ValueError("y cannot be empty")

        self.bridge_ = MIDASBridge(
            source_configs=self.source_configs,
            almon_poly_degree=self.almon_degree,
            apply_almon_weights=True,
        )
        features = self.bridge_.build_features(
            X, pd.DatetimeIndex(y.index), vintage_date
        )
        y_aligned = y.reindex(features.index)

        if y_aligned.isna().any():
            raise ValueError(
                "y contains missing values after alignment to target dates"
            )

        self.model_ = MIDASRegression(
            n_lags=features.shape[1],
            almon_degree=self.almon_degree,
            horizon=self.horizon,
            include_intercept=self.include_intercept,
            optimization_method=self.optimization_method,
            random_state=self.random_state,
        )
        self.model_.fit(features, y_aligned, vintage_date=vintage_date)

        self.feature_names_ = list(features.columns)
        self.vintage_date_ = vintage_date

        logger.info(
            "midas_bridged_fit_completed",
            model_id=self.model_id,
            n_features=len(self.feature_names_),
            vintage_date=vintage_date,
        )

        return self

    def predict(
        self,
        X: Mapping[str, RawSource],
        target_dates: Optional[pd.DatetimeIndex] = None,
    ) -> np.ndarray:
        """
        Generate predictions from raw source data.

        Args:
            X: Raw mixed-frequency source mapping.
            target_dates: Monthly target dates for prediction. Required because raw
                sources may extend beyond the desired forecast window.

        Returns:
            Prediction array with one value per target date.
        """
        if self.model_ is None or self.bridge_ is None:
            raise ValueError(
                "Model must be fitted before prediction. Call fit() first."
            )
        if target_dates is None:
            raise ValueError("target_dates must be provided for raw-source prediction")

        features = self.bridge_.build_features(X, target_dates, self.vintage_date_)
        features = features.reindex(columns=self.feature_names_)
        return self.model_.predict(features)

    def get_params(self) -> Dict[str, Any]:
        """Get model parameters and fitted metadata."""
        return {
            "random_state": self.random_state,
            "almon_degree": self.almon_degree,
            "horizon": self.horizon,
            "include_intercept": self.include_intercept,
            "optimization_method": self.optimization_method,
            "vintage_date": self.vintage_date_,
            "n_features": len(self.feature_names_) if self.feature_names_ else None,
            "is_fitted": self.model_ is not None,
            "model_id": self.model_id,
            "created_at": self.created_at,
        }

    def save(self, path: Path) -> None:
        """
        Save the bridged model state.

        Args:
            path: Destination path for joblib model data.
        """
        if self.model_ is None:
            raise ValueError("Cannot save unfitted model. Call fit() first.")

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "params": self.get_params(),
                "source_configs": self.source_configs,
                "bridge": self.bridge_,
                "model": self.model_,
                "feature_names": self.feature_names_,
            },
            path,
        )

    @classmethod
    def load(cls, path: Path) -> "MIDASBridgedRegression":
        """
        Load a saved bridged model.

        Args:
            path: Path created by save().

        Returns:
            Loaded MIDASBridgedRegression.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Model file not found: {path}")

        model_data = joblib.load(path)
        params = model_data["params"]
        instance = cls(
            source_configs=model_data["source_configs"],
            almon_degree=params["almon_degree"],
            horizon=params["horizon"],
            include_intercept=params["include_intercept"],
            optimization_method=params["optimization_method"],
            random_state=params["random_state"],
        )
        instance.bridge_ = model_data["bridge"]
        instance.model_ = model_data["model"]
        instance.feature_names_ = model_data["feature_names"]
        instance.vintage_date_ = params["vintage_date"]
        return instance
