"""
Frequency conversion for mixed-frequency forecasting.

Converts time series between frequencies:
- Daily → Weekly
- Daily → Monthly
- Weekly → Monthly
- Business days → Monthly

Aggregation methods: mean, sum, last, first
"""

from typing import Literal
import pandas as pd
import numpy as np
import structlog

logger = structlog.get_logger(__name__)


class FrequencyConverter:
    """
    Convert time series between frequencies.

    Supports aggregation from high to low frequency with various methods.
    All conversions are deterministic and vintage-aware.

    Args:
        source_freq: Source frequency ('D', 'B', 'W')
        target_freq: Target frequency ('W', 'M')
        agg_method: Aggregation method ('mean', 'sum', 'last', 'first')

    Example:
        >>> converter = FrequencyConverter(source_freq='D', target_freq='M', agg_method='mean')
        >>> monthly_data = converter.convert(daily_series)
    """

    FREQ_HIERARCHY = {"D": 1, "B": 1, "W": 7, "M": 30}  # Approximate days

    def __init__(
        self,
        source_freq: Literal["D", "B", "W"],
        target_freq: Literal["W", "M"],
        agg_method: Literal["mean", "sum", "last", "first"] = "mean",
    ):
        """Initialize frequency converter."""
        self.source_freq = source_freq
        self.target_freq = target_freq
        self.agg_method = agg_method

        self._validate_parameters()

        logger.info(
            "frequency_converter_initialized",
            source_freq=source_freq,
            target_freq=target_freq,
            agg_method=agg_method,
        )

    def _validate_parameters(self) -> None:
        """Validate converter parameters."""
        valid_source = ["D", "B", "W"]
        valid_target = ["W", "M"]

        if self.source_freq not in valid_source:
            raise ValueError(f"source_freq must be one of {valid_source}")

        if self.target_freq not in valid_target:
            raise ValueError(f"target_freq must be one of {valid_target}")

        # Cannot go from lower to higher frequency
        if self.FREQ_HIERARCHY[self.source_freq] >= self.FREQ_HIERARCHY[self.target_freq]:
            if not (self.source_freq in ["D", "B"] and self.target_freq == "W"):
                # Allow daily/business to weekly
                if self.source_freq != "D" or self.target_freq != "W":
                    raise ValueError(
                        f"Cannot convert from lower to higher frequency: "
                        f"{self.source_freq} → {self.target_freq}"
                    )

        if self.agg_method not in ["mean", "sum", "last", "first"]:
            raise ValueError(
                f"agg_method must be 'mean', 'sum', 'last', or 'first', "
                f"got {self.agg_method}"
            )

    def convert(self, series: pd.Series) -> pd.Series:
        """
        Convert series to target frequency.

        Args:
            series: Time series with datetime index

        Returns:
            Converted series at target frequency

        Raises:
            ValueError: If series has invalid index
        """
        if not isinstance(series.index, pd.DatetimeIndex):
            raise ValueError("Series must have DatetimeIndex")

        if len(series) == 0:
            raise ValueError("Series cannot be empty")

        logger.info(
            "converting_frequency",
            series_name=series.name or "unnamed",
            series_length=len(series),
            source_freq=self.source_freq,
            target_freq=self.target_freq,
        )

        # Perform conversion based on target frequency
        if self.target_freq == "W":
            result = self._convert_to_weekly(series)
        elif self.target_freq == "M":
            result = self._convert_to_monthly(series)
        else:
            raise ValueError(f"Unsupported target frequency: {self.target_freq}")

        logger.info(
            "frequency_converted",
            result_length=len(result),
            missing_values=result.isna().sum(),
        )

        return result

    def _convert_to_weekly(self, series: pd.Series) -> pd.Series:
        """Convert to weekly frequency."""
        # Resample to weekly (ending on Sunday by default)
        resampler = series.resample("W")

        if self.agg_method == "mean":
            result = resampler.mean()
        elif self.agg_method == "sum":
            result = resampler.sum()
        elif self.agg_method == "last":
            result = resampler.last()
        elif self.agg_method == "first":
            result = resampler.first()
        else:
            raise ValueError(f"Unknown aggregation method: {self.agg_method}")

        return result

    def _convert_to_monthly(self, series: pd.Series) -> pd.Series:
        """Convert to monthly frequency."""
        # Resample to month start
        resampler = series.resample("MS")

        if self.agg_method == "mean":
            result = resampler.mean()
        elif self.agg_method == "sum":
            result = resampler.sum()
        elif self.agg_method == "last":
            result = resampler.last()
        elif self.agg_method == "first":
            result = resampler.first()
        else:
            raise ValueError(f"Unknown aggregation method: {self.agg_method}")

        return result


def convert_to_frequency(
    series: pd.Series,
    target_freq: str,
    agg_method: str = "mean",
) -> pd.Series:
    """
    Convenience function for frequency conversion.

    Args:
        series: Time series to convert
        target_freq: Target frequency ('W', 'M')
        agg_method: Aggregation method

    Returns:
        Converted series

    Example:
        >>> weekly = convert_to_frequency(daily_series, target_freq='W', agg_method='mean')
    """
    # Infer source frequency
    source_freq = pd.infer_freq(series.index)

    if source_freq is None:
        # Try to infer from median difference
        diffs = series.index.to_series().diff().median()
        if diffs <= pd.Timedelta(days=1.5):
            source_freq = "D"
        elif diffs <= pd.Timedelta(days=8):
            source_freq = "W"
        else:
            raise ValueError("Could not infer series frequency")
    else:
        # Normalize pandas frequency strings
        if source_freq.startswith("D"):
            source_freq = "D"
        elif source_freq.startswith("B"):
            source_freq = "B"
        elif source_freq.startswith("W"):
            source_freq = "W"
        elif source_freq in ["M", "MS", "ME"]:
            source_freq = "M"

    converter = FrequencyConverter(
        source_freq=source_freq, target_freq=target_freq, agg_method=agg_method
    )
    return converter.convert(series)

