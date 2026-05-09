"""
Base Regressor Builder
Foundation for creating X-13 external regressors
"""

from abc import ABC, abstractmethod
from datetime import date
from pathlib import Path

import pandas as pd
from loguru import logger


class RegressorBuilder(ABC):
    """
    Abstract base class for X-13 regressor builders

    Regressors are external variables used to adjust for:
    - Holiday timing shifts
    - Strike impacts
    - Weather disruptions
    - Other special events
    """

    def __init__(self, name: str):
        """
        Initialize regressor builder

        Args:
            name: Name of the regressor
        """
        self.name = name
        self.regressors = {}

    @abstractmethod
    def build(self, start_date: date, end_date: date, frequency: str = "monthly") -> pd.DataFrame:
        """
        Build regressor time series

        Args:
            start_date: Start date
            end_date: End date
            frequency: Time frequency (monthly, weekly, daily)

        Returns:
            DataFrame with regressor values
        """
        pass

    def save_regressor(self, regressor_df: pd.DataFrame, output_path: Path, format: str = "x13"):
        """
        Save regressor to file

        Args:
            regressor_df: DataFrame with regressor values
            output_path: Output file path
            format: Output format ("x13" or "csv")
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if format == "x13":
            self._save_x13_format(regressor_df, output_path)
        elif format == "csv":
            regressor_df.to_csv(output_path, index=True)
        else:
            raise ValueError(f"Unknown format: {format}")

        logger.info(f"Saved regressor: {output_path}")

    def _save_x13_format(self, regressor_df: pd.DataFrame, output_path: Path):
        """
        Save regressor in X-13 format

        X-13 regressor format:
        regression {
            user = (regressor_name)
            data = (value1 value2 value3 ...)
            start = YYYY.MM
        }
        """
        if not isinstance(regressor_df.index, pd.DatetimeIndex):
            raise ValueError("DataFrame must have DatetimeIndex")

        start_date = regressor_df.index[0]
        start_year = start_date.year
        start_month = start_date.month

        # Get values (assuming single column or first column)
        if len(regressor_df.columns) > 0:
            values = regressor_df.iloc[:, 0].values
        else:
            values = regressor_df.values.flatten()

        # Format values
        values_str = " ".join(str(v) for v in values)

        # Create X-13 regression specification
        content = f"""regression {{
    user = ({self.name})
    data = ({values_str})
    start = {start_year}.{start_month}
    type = {self._get_regressor_type()}
}}
"""

        output_path.write_text(content)

    def _get_regressor_type(self) -> str:
        """Get regressor type for X-13"""
        # Types: holiday, seasonal, td (trading day), ao (additive outlier), etc.
        return "user"

    def create_impulse(
        self, dates: pd.DatetimeIndex, event_date: date, duration: int = 1
    ) -> pd.Series:
        """
        Create impulse regressor (1 during event, 0 otherwise)

        Args:
            dates: Full date range
            event_date: Date of event
            duration: Duration in periods

        Returns:
            Series with impulse values
        """
        regressor = pd.Series(0, index=dates)

        # Find matching dates
        for i in range(duration):
            event_period = pd.Period(event_date, freq="M") + i
            mask = dates.to_period("M") == event_period
            regressor[mask] = 1

        return regressor

    def create_step(
        self,
        dates: pd.DatetimeIndex,
        step_date: date,
        value_before: float = 0,
        value_after: float = 1,
    ) -> pd.Series:
        """
        Create step regressor (changes level at a point)

        Args:
            dates: Full date range
            step_date: Date of step change
            value_before: Value before step
            value_after: Value after step

        Returns:
            Series with step values
        """
        regressor = pd.Series(value_before, index=dates)
        regressor[dates >= step_date] = value_after

        return regressor

    def create_ramp(
        self,
        dates: pd.DatetimeIndex,
        start_date: date,
        end_date: date,
        start_value: float = 0,
        end_value: float = 1,
    ) -> pd.Series:
        """
        Create ramp regressor (gradual change)

        Args:
            dates: Full date range
            start_date: Ramp start date
            end_date: Ramp end date
            start_value: Starting value
            end_value: Ending value

        Returns:
            Series with ramp values
        """
        regressor = pd.Series(start_value, index=dates)

        # Calculate ramp
        ramp_mask = (dates >= start_date) & (dates <= end_date)
        ramp_dates = dates[ramp_mask]

        if len(ramp_dates) > 0:
            ramp_length = len(ramp_dates)
            ramp_values = [
                start_value + (end_value - start_value) * i / (ramp_length - 1)
                for i in range(ramp_length)
            ]
            regressor[ramp_mask] = ramp_values

        # After ramp
        regressor[dates > end_date] = end_value

        return regressor


def create_date_range(
    start_date: date, end_date: date, frequency: str = "monthly"
) -> pd.DatetimeIndex:
    """
    Create date range for regressors

    Args:
        start_date: Start date
        end_date: End date
        frequency: Frequency (monthly, weekly, daily)

    Returns:
        DatetimeIndex
    """
    freq_map = {"monthly": "MS", "weekly": "W", "daily": "D"}  # Month start

    freq_code = freq_map.get(frequency, "MS")

    return pd.date_range(start=start_date, end=end_date, freq=freq_code)
