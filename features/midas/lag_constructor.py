"""
MIDAS lag constructor for mixed-frequency feature engineering.

MIDAS (Mixed Data Sampling) enables regression with predictors sampled at different
frequencies (e.g., daily Treasury data predicting monthly NFP).

Key Features:
- Frequency alignment (daily → weekly, daily → monthly, weekly → monthly)
- Exponential Almon lag polynomial weighting
- Ragged-edge handling (missing recent high-frequency data)
- Deterministic output (reproducibility)

References:
- Ghysels, Santa-Clara, Valkanov (2004): MIDAS regressions
- Clements & Galvão (2008): Macroeconomic forecasting with MIDAS
"""

from typing import Literal
import numpy as np
import pandas as pd
from loguru import logger


class MIDASLagConstructor:
    """
    Construct MIDAS lag features from high-frequency to low-frequency.

    Aligns high-frequency series (e.g., daily, weekly) to low-frequency target dates
    (e.g., monthly) and creates lag features with optional Almon polynomial weighting.

    Args:
        source_freq: Source series frequency ('D' for daily, 'W' for weekly)
        target_freq: Target frequency ('W' for weekly, 'M' for monthly)
        n_lags: Number of lags to construct
        almon_poly_degree: Degree of exponential Almon polynomial (0 = equal weights)
        apply_weights: Whether to apply Almon weights to lags (False = raw lags)
        column_prefix: Prefix for lag column names (default: 'lag')

    Example:
        >>> constructor = MIDASLagConstructor(
        ...     source_freq='D',
        ...     target_freq='M',
        ...     n_lags=20,
        ...     almon_poly_degree=2
        ... )
        >>> lags = constructor.construct_lags(daily_series, monthly_dates)
    """

    VALID_FREQUENCIES = {"D": 1, "W": 7, "M": 30}  # Approximate days per period
    FREQ_HIERARCHY = ["D", "W", "M"]  # Low to high aggregation

    def __init__(
        self,
        source_freq: Literal["D", "W"],
        target_freq: Literal["W", "M"],
        n_lags: int,
        almon_poly_degree: int = 2,
        apply_weights: bool = False,
        column_prefix: str = "lag",
    ):
        """Initialize MIDAS lag constructor."""
        self.source_freq = source_freq
        self.target_freq = target_freq
        self.n_lags = n_lags
        self.almon_poly_degree = almon_poly_degree
        self.apply_weights = apply_weights
        self.column_prefix = column_prefix

        self._validate_parameters()

        logger.info(
            "midas_constructor_initialized",
            source_freq=source_freq,
            target_freq=target_freq,
            n_lags=n_lags,
            almon_degree=almon_poly_degree,
        )

    def _validate_parameters(self) -> None:
        """Validate constructor parameters."""
        if self.source_freq not in ["D", "W"]:
            raise ValueError(f"source_freq must be 'D' or 'W', got {self.source_freq}")

        if self.target_freq not in ["W", "M"]:
            raise ValueError(f"target_freq must be 'W' or 'M', got {self.target_freq}")

        # Source must be higher frequency than target
        source_idx = self.FREQ_HIERARCHY.index(self.source_freq)
        target_idx = self.FREQ_HIERARCHY.index(self.target_freq)

        if source_idx >= target_idx:
            raise ValueError(
                f"source_freq must be higher frequency than target_freq. "
                f"Got source={self.source_freq}, target={self.target_freq}"
            )

        if self.n_lags <= 0:
            raise ValueError(f"n_lags must be positive, got {self.n_lags}")

        if self.almon_poly_degree < 0:
            raise ValueError(
                f"almon_poly_degree must be non-negative, got {self.almon_poly_degree}"
            )

    def construct_lags(self, series: pd.Series, target_dates: pd.DatetimeIndex) -> pd.DataFrame:
        """
        Construct MIDAS lag features.

        Args:
            series: High-frequency time series with datetime index
            target_dates: Target dates for low-frequency predictions

        Returns:
            DataFrame with lag features (rows = target_dates, cols = lags)

        Raises:
            ValueError: If series is empty or frequency mismatched
        """
        if len(series) == 0:
            raise ValueError("Series cannot be empty")

        # Infer and validate series frequency
        inferred_freq = infer_series_frequency(series)
        if inferred_freq != self.source_freq:
            raise ValueError(
                f"Series frequency does not match source_freq. "
                f"Expected {self.source_freq}, inferred {inferred_freq}"
            )

        logger.info(
            "constructing_midas_lags",
            series_name=series.name or "unnamed",
            series_length=len(series),
            target_dates_count=len(target_dates),
            n_lags=self.n_lags,
        )

        # Build lag matrix
        lag_matrix = self._build_lag_matrix(series, target_dates)

        # Apply Almon weights if requested
        if self.apply_weights:
            weights = self._compute_almon_weights(self.n_lags, self.almon_poly_degree)
            lag_matrix = lag_matrix * weights

        # Create DataFrame with proper column names
        column_names = [f"{self.column_prefix}_lag_{i}" for i in range(self.n_lags)]
        result = pd.DataFrame(lag_matrix, index=target_dates, columns=column_names)

        logger.info(
            "midas_lags_constructed",
            output_shape=result.shape,
            missing_values=result.isna().sum().sum(),
        )

        return result

    def _build_lag_matrix(self, series: pd.Series, target_dates: pd.DatetimeIndex) -> np.ndarray:
        """
        Build raw lag matrix (before weighting).

        For each target date, extract the n_lags most recent values from the
        high-frequency series.

        Args:
            series: High-frequency time series
            target_dates: Target prediction dates

        Returns:
            Lag matrix (n_target_dates, n_lags)
        """
        lag_matrix = np.full((len(target_dates), self.n_lags), np.nan)

        for i, target_date in enumerate(target_dates):
            # Get all data available up to (and including) target date
            available_data = series[series.index <= target_date]

            if len(available_data) == 0:
                logger.warning(
                    "no_data_before_target_date",
                    target_date=target_date,
                    series_start=series.index[0] if len(series) > 0 else None,
                )
                continue

            # Extract lags (most recent first)
            # lag_0 = most recent value, lag_1 = previous value, etc.
            for lag_idx in range(self.n_lags):
                data_idx = len(available_data) - 1 - lag_idx

                if data_idx >= 0:
                    lag_matrix[i, lag_idx] = available_data.iloc[data_idx]
                else:
                    # Insufficient data for this lag
                    # Keep as NaN or could use forward-fill strategy
                    pass

        return lag_matrix

    def _compute_almon_weights(self, n_lags: int, degree: int) -> np.ndarray:
        """
        Compute exponential Almon polynomial weights.

        Almon (1965) polynomial provides smooth decay of lag weights.
        Higher degree = more flexible decay pattern.

        Args:
            n_lags: Number of lags
            degree: Polynomial degree (0 = equal weights)

        Returns:
            Normalized weight vector (sums to 1)
        """
        if degree == 0:
            # Equal weights
            return np.ones(n_lags) / n_lags

        # Create lag indices (0 = most recent)
        lag_indices = np.arange(n_lags, dtype=float)

        # Exponential Almon: w_i = exp(-θ * i^p) where p is degree
        # Recent lags (small i) get higher weight
        theta = 1.0  # Decay rate parameter
        weights = np.exp(-theta * (lag_indices / n_lags) ** degree)

        # Normalize to sum to 1
        weights = weights / weights.sum()

        return weights


# Utility functions


def get_frequency_ratio(source_freq: str, target_freq: str) -> int:
    """
    Calculate approximate frequency ratio.

    Args:
        source_freq: High-frequency identifier ('D', 'W')
        target_freq: Low-frequency identifier ('W', 'M')

    Returns:
        Approximate ratio (e.g., ~30 for daily-to-monthly)

    Example:
        >>> get_frequency_ratio('D', 'M')
        30
        >>> get_frequency_ratio('W', 'M')
        4
    """
    ratios = {
        ("D", "W"): 7,
        ("D", "M"): 30,
        ("W", "M"): 4,
    }

    key = (source_freq, target_freq)
    if key not in ratios:
        raise ValueError(f"Unsupported frequency combination: {source_freq} → {target_freq}")

    return ratios[key]


def infer_series_frequency(series: pd.Series) -> str:
    """
    Infer frequency from pandas Series index.

    Args:
        series: Time series with datetime index

    Returns:
        Frequency string ('D', 'W', 'M', 'MS')

    Raises:
        ValueError: If frequency cannot be inferred
    """
    if not isinstance(series.index, pd.DatetimeIndex):
        raise ValueError("Series must have DatetimeIndex")

    if len(series) < 2:
        raise ValueError("Series must have at least 2 observations to infer frequency")

    # Try to infer frequency
    freq = pd.infer_freq(series.index)

    if freq is None:
        # Try manual inference from median difference
        diffs = series.index.to_series().diff().median()
        if diffs <= pd.Timedelta(days=1.5):
            return "D"
        elif diffs <= pd.Timedelta(days=8):
            return "W"
        elif diffs <= pd.Timedelta(days=32):
            return "M"
        else:
            raise ValueError("Could not infer frequency from series index")

    # Normalize pandas frequency strings
    if freq.startswith("D"):
        return "D"
    elif freq.startswith("W"):
        return "W"
    elif freq in ["M", "MS", "ME"]:
        return "M"
    else:
        raise ValueError(f"Unsupported frequency: {freq}")


def align_series_to_dates(
    series: pd.Series,
    target_dates: pd.DatetimeIndex,
    method: Literal["last", "mean", "sum"] = "last",
) -> pd.Series:
    """
    Align high-frequency series to target dates.

    Args:
        series: High-frequency time series
        target_dates: Target dates for alignment
        method: Aggregation method ('last', 'mean', 'sum')

    Returns:
        Series aligned to target dates

    Example:
        >>> daily_idx = pd.date_range("2024-01-01", periods=90, freq="D")
        >>> daily = pd.Series(range(90), index=daily_idx)
        >>> monthly = pd.date_range("2024-01-01", periods=3, freq="MS")
        >>> align_series_to_dates(daily, monthly, method="last")
    """
    if method not in ["last", "mean", "sum"]:
        raise ValueError(f"method must be 'last', 'mean', or 'sum', got {method}")

    aligned_values = []

    for target_date in target_dates:
        # Get data up to target date
        available = series[series.index <= target_date]

        if len(available) == 0:
            aligned_values.append(np.nan)
            continue

        if method == "last":
            aligned_values.append(available.iloc[-1])
        elif method == "mean":
            aligned_values.append(available.mean())
        elif method == "sum":
            aligned_values.append(available.sum())

    return pd.Series(aligned_values, index=target_dates, name=series.name)
