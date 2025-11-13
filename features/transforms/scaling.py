"""
Scaling and winsorization transformations.

Features:
- StandardScaler: Z-score standardization (mean=0, std=1)
- MinMaxScaler: Min-max normalization to [0, 1]
- RobustScaler: Median and IQR-based scaling (robust to outliers)
- Winsorizer: Outlier capping at percentiles

All transformations are deterministic and support fit/transform/inverse_transform.
"""

from typing import Optional, Tuple
import pandas as pd
import numpy as np
import structlog

logger = structlog.get_logger(__name__)


class StandardScaler:
    """
    Standardize features by removing mean and scaling to unit variance.

    Z-score normalization: z = (x - μ) / σ

    Attributes:
        mean_: Fitted mean
        std_: Fitted standard deviation
    """

    def __init__(self):
        """Initialize standard scaler."""
        self.mean_: Optional[float] = None
        self.std_: Optional[float] = None
        self._fitted = False

    def fit(self, series: pd.Series) -> "StandardScaler":
        """
        Compute mean and std for later scaling.

        Args:
            series: Training data

        Returns:
            self
        """
        if len(series) == 0:
            raise ValueError("Series cannot be empty")

        self.mean_ = float(series.mean())
        self.std_ = float(series.std())

        if self.std_ == 0:
            logger.warning("zero_std_detected", series_name=series.name)
            self.std_ = 1.0  # Avoid division by zero

        self._fitted = True

        logger.info(
            "standard_scaler_fitted",
            mean=self.mean_,
            std=self.std_,
            series_length=len(series),
        )

        return self

    def transform(self, series: pd.Series) -> pd.Series:
        """
        Apply standardization.

        Args:
            series: Data to transform

        Returns:
            Standardized series
        """
        if not self._fitted:
            raise ValueError("Scaler must be fitted before transform")

        scaled = (series - self.mean_) / self.std_

        return pd.Series(scaled, index=series.index, name=series.name)

    def fit_transform(self, series: pd.Series) -> pd.Series:
        """Fit and transform in one step."""
        return self.fit(series).transform(series)

    def inverse_transform(self, series: pd.Series) -> pd.Series:
        """
        Reverse the standardization.

        Args:
            series: Standardized data

        Returns:
            Original scale data
        """
        if not self._fitted:
            raise ValueError("Scaler must be fitted before inverse_transform")

        original = (series * self.std_) + self.mean_

        return pd.Series(original, index=series.index, name=series.name)


class MinMaxScaler:
    """
    Scale features to [0, 1] range.

    Formula: x_scaled = (x - min) / (max - min)

    Attributes:
        min_: Fitted minimum value
        max_: Fitted maximum value
    """

    def __init__(self):
        """Initialize min-max scaler."""
        self.min_: Optional[float] = None
        self.max_: Optional[float] = None
        self._fitted = False

    def fit(self, series: pd.Series) -> "MinMaxScaler":
        """
        Compute min and max for later scaling.

        Args:
            series: Training data

        Returns:
            self
        """
        if len(series) == 0:
            raise ValueError("Series cannot be empty")

        self.min_ = float(series.min())
        self.max_ = float(series.max())

        if self.min_ == self.max_:
            logger.warning("constant_series_detected", value=self.min_)
            self.max_ = self.min_ + 1.0  # Avoid division by zero

        self._fitted = True

        logger.info(
            "minmax_scaler_fitted",
            min=self.min_,
            max=self.max_,
            series_length=len(series),
        )

        return self

    def transform(self, series: pd.Series) -> pd.Series:
        """
        Scale to [0, 1] range.

        Args:
            series: Data to transform

        Returns:
            Scaled series
        """
        if not self._fitted:
            raise ValueError("Scaler must be fitted before transform")

        scaled = (series - self.min_) / (self.max_ - self.min_)

        # Clip to [0, 1] in case of out-of-sample extremes
        scaled = scaled.clip(0.0, 1.0)

        return pd.Series(scaled, index=series.index, name=series.name)

    def fit_transform(self, series: pd.Series) -> pd.Series:
        """Fit and transform in one step."""
        return self.fit(series).transform(series)

    def inverse_transform(self, series: pd.Series) -> pd.Series:
        """
        Reverse the scaling.

        Args:
            series: Scaled data in [0, 1]

        Returns:
            Original scale data
        """
        if not self._fitted:
            raise ValueError("Scaler must be fitted before inverse_transform")

        original = (series * (self.max_ - self.min_)) + self.min_

        return pd.Series(original, index=series.index, name=series.name)


class RobustScaler:
    """
    Scale features using robust statistics (median and IQR).

    More robust to outliers than StandardScaler.
    Formula: x_scaled = (x - median) / IQR

    Attributes:
        median_: Fitted median
        iqr_: Fitted interquartile range (Q3 - Q1)
    """

    def __init__(self):
        """Initialize robust scaler."""
        self.median_: Optional[float] = None
        self.iqr_: Optional[float] = None
        self._fitted = False

    def fit(self, series: pd.Series) -> "RobustScaler":
        """
        Compute median and IQR for later scaling.

        Args:
            series: Training data

        Returns:
            self
        """
        if len(series) == 0:
            raise ValueError("Series cannot be empty")

        self.median_ = float(series.median())
        q1 = series.quantile(0.25)
        q3 = series.quantile(0.75)
        self.iqr_ = float(q3 - q1)

        if self.iqr_ == 0:
            logger.warning("zero_iqr_detected", series_name=series.name)
            self.iqr_ = 1.0  # Avoid division by zero

        self._fitted = True

        logger.info(
            "robust_scaler_fitted",
            median=self.median_,
            iqr=self.iqr_,
            series_length=len(series),
        )

        return self

    def transform(self, series: pd.Series) -> pd.Series:
        """
        Apply robust scaling.

        Args:
            series: Data to transform

        Returns:
            Scaled series
        """
        if not self._fitted:
            raise ValueError("Scaler must be fitted before transform")

        scaled = (series - self.median_) / self.iqr_

        return pd.Series(scaled, index=series.index, name=series.name)

    def fit_transform(self, series: pd.Series) -> pd.Series:
        """Fit and transform in one step."""
        return self.fit(series).transform(series)

    def inverse_transform(self, series: pd.Series) -> pd.Series:
        """
        Reverse the scaling.

        Args:
            series: Scaled data

        Returns:
            Original scale data
        """
        if not self._fitted:
            raise ValueError("Scaler must be fitted before inverse_transform")

        original = (series * self.iqr_) + self.median_

        return pd.Series(original, index=series.index, name=series.name)


class Winsorizer:
    """
    Cap extreme values at specified percentiles.

    Replaces outliers with the value at the specified percentile.
    More conservative than dropping outliers (preserves sample size).

    Args:
        lower: Lower percentile (0-1), e.g., 0.05 for 5th percentile
        upper: Upper percentile (0-1), e.g., 0.95 for 95th percentile

    Attributes:
        lower_bound_: Fitted lower bound
        upper_bound_: Fitted upper bound
    """

    def __init__(self, lower: float = 0.05, upper: float = 0.95):
        """Initialize winsorizer."""
        if not 0 <= lower < upper <= 1:
            raise ValueError(
                f"Must have 0 <= lower < upper <= 1, got lower={lower}, upper={upper}"
            )

        self.lower = lower
        self.upper = upper
        self.lower_bound_: Optional[float] = None
        self.upper_bound_: Optional[float] = None
        self._fitted = False

    def fit(self, series: pd.Series) -> "Winsorizer":
        """
        Compute percentile bounds.

        Args:
            series: Training data

        Returns:
            self
        """
        if len(series) == 0:
            raise ValueError("Series cannot be empty")

        self.lower_bound_ = float(series.quantile(self.lower))
        self.upper_bound_ = float(series.quantile(self.upper))

        self._fitted = True

        logger.info(
            "winsorizer_fitted",
            lower_percentile=self.lower,
            upper_percentile=self.upper,
            lower_bound=self.lower_bound_,
            upper_bound=self.upper_bound_,
        )

        return self

    def transform(self, series: pd.Series) -> pd.Series:
        """
        Winsorize (cap) extreme values.

        Args:
            series: Data to transform

        Returns:
            Winsorized series
        """
        if not self._fitted:
            raise ValueError("Winsorizer must be fitted before transform")

        # Clip values to bounds
        winsorized = series.clip(lower=self.lower_bound_, upper=self.upper_bound_)

        return pd.Series(winsorized, index=series.index, name=series.name)

    def fit_transform(self, series: pd.Series) -> pd.Series:
        """Fit and transform in one step."""
        return self.fit(series).transform(series)

