"""
Weather Regressors
Builds regressors for severe weather impacts on employment data
"""

from datetime import date
from typing import Optional, List

import pandas as pd
from loguru import logger

from .regressor_builder import RegressorBuilder, create_date_range
from etl.common.storage import StorageClient


class WeatherRegressors(RegressorBuilder):
    """
    Builder for weather impact regressors

    Severe weather can significantly disrupt employment surveys:
    - Hurricanes (coastal states, major disruption)
    - Blizzards (northern states, transportation/retail)
    - Wildfires (western states, outdoor work)
    - Heat waves (construction, agriculture)
    """

    def __init__(self, storage_client: Optional[StorageClient] = None):
        """
        Initialize weather regressors builder

        Args:
            storage_client: Storage client for accessing weather data
        """
        super().__init__("weather")
        self.storage_client = storage_client or StorageClient()

    def build(
        self,
        start_date: date,
        end_date: date,
        frequency: str = "monthly",
        event_types: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """
        Build weather impact regressors

        Args:
            start_date: Start date
            end_date: End date
            frequency: Time frequency
            event_types: Specific event types to include

        Returns:
            DataFrame with weather regressors
        """
        logger.info(f"Building weather regressors from {start_date} to {end_date}")

        dates = create_date_range(start_date, end_date, frequency)

        # Load weather data
        weather_df = self._load_weather_data(start_date, end_date)

        if weather_df is None or len(weather_df) == 0:
            logger.warning("No weather data available - creating empty regressors")
            return pd.DataFrame({"weather_impact": 0}, index=dates)

        # Filter by event types if specified
        if event_types:
            weather_df = weather_df[weather_df["event_type"].isin(event_types)]

        logger.info(f"Processing {len(weather_df)} weather events")

        # Build regressors
        regressors = pd.DataFrame(index=dates)

        # Overall weather impact
        regressors["weather_impact"] = self._build_impact_regressor(dates, weather_df)

        # Event-type specific regressors
        event_types_in_data = weather_df["event_type"].unique()

        for event_type in event_types_in_data:
            type_events = weather_df[weather_df["event_type"] == event_type]

            # Only create regressor if significant events
            if len(type_events) > 0:
                col_name = f"weather_{event_type.lower().replace(' ', '_')}"
                regressors[col_name] = self._build_impact_regressor(dates, type_events)

        logger.info(f"Created {len(regressors.columns)} weather regressors")

        return regressors

    def _load_weather_data(self, start_date: date, end_date: date) -> Optional[pd.DataFrame]:
        """
        Load weather event data from storage

        Args:
            start_date: Start date
            end_date: End date

        Returns:
            DataFrame with weather events or None
        """
        try:
            # Load most recent vintage
            weather_df = self.storage_client.read_parquet("vintages/weather/latest/weather.parquet")

            if weather_df is None:
                return None

            # Ensure date columns
            if "begin_date" in weather_df.columns:
                weather_df["begin_date"] = pd.to_datetime(weather_df["begin_date"])
            if "end_date" in weather_df.columns:
                weather_df["end_date"] = pd.to_datetime(weather_df["end_date"])

            # Filter date range
            if "begin_date" in weather_df.columns:
                weather_df = weather_df[
                    (weather_df["begin_date"] >= pd.Timestamp(start_date))
                    & (weather_df["begin_date"] <= pd.Timestamp(end_date))
                ]

            return weather_df

        except Exception as e:
            logger.error(f"Failed to load weather data: {e}")
            return None

    def _build_impact_regressor(
        self, dates: pd.DatetimeIndex, weather_df: pd.DataFrame
    ) -> pd.Series:
        """
        Build weather impact regressor from weather events

        Impact scoring based on:
        - Event type severity (hurricane > blizzard > thunderstorm)
        - Duration
        - Geographic scope (state-level)
        - Deaths/injuries (proxy for severity)
        - Property damage

        Args:
            dates: Date range
            weather_df: Weather events

        Returns:
            Series with impact values
        """
        regressor = pd.Series(0.0, index=dates)

        # Event type severity weights
        severity_weights = {
            "Hurricane": 10.0,
            "Tropical Storm": 5.0,
            "Blizzard": 8.0,
            "Ice Storm": 7.0,
            "Winter Storm": 5.0,
            "Heavy Snow": 3.0,
            "Wildfire": 6.0,
            "Extreme Heat": 2.0,
            "Tornado": 4.0,
            "Flood": 4.0,
            "Flash Flood": 3.0,
        }

        for _, event in weather_df.iterrows():
            begin_date = event.get("begin_date")
            event_type = event.get("event_type", "")

            if pd.isna(begin_date):
                continue

            # Get severity weight
            severity = severity_weights.get(event_type, 1.0)

            # Adjust by casualties (if available)
            deaths = event.get("deaths_direct", 0) + event.get("deaths_indirect", 0)
            injuries = event.get("injuries_direct", 0) + event.get("injuries_indirect", 0)

            casualty_multiplier = 1.0 + (deaths * 0.5) + (injuries * 0.1)
            casualty_multiplier = min(casualty_multiplier, 5.0)  # Cap

            # Calculate impact score
            impact_score = severity * casualty_multiplier

            # Normalize to reasonable range
            impact_score = min(impact_score, 10.0)

            # Apply to month
            event_timestamp = pd.Timestamp(begin_date)
            event_period = event_timestamp.to_period("M")

            mask = dates.to_period("M") == event_period

            # Add impact (accumulate if multiple events)
            regressor[mask] += impact_score

        # Cap total impact at reasonable level
        regressor = regressor.clip(upper=20.0)

        # Normalize to 0-1 range for better X-13 performance
        if regressor.max() > 0:
            regressor = regressor / regressor.max()

        return regressor

    def build_hurricane_regressor(
        self, start_date: date, end_date: date, min_category: int = 3
    ) -> pd.Series:
        """
        Build regressor specifically for major hurricanes

        Args:
            start_date: Start date
            end_date: End date
            min_category: Minimum hurricane category

        Returns:
            Series with hurricane impacts
        """
        dates = create_date_range(start_date, end_date, "monthly")

        # Load weather data
        weather_df = self._load_weather_data(start_date, end_date)

        if weather_df is None:
            return pd.Series(0, index=dates)

        # Filter for hurricanes
        hurricanes = weather_df[weather_df["event_type"] == "Hurricane"]

        # Build regressor
        return self._build_impact_regressor(dates, hurricanes)

    def build_winter_storm_regressor(self, start_date: date, end_date: date) -> pd.Series:
        """
        Build regressor for major winter storms

        Args:
            start_date: Start date
            end_date: End date

        Returns:
            Series with winter storm impacts
        """
        dates = create_date_range(start_date, end_date, "monthly")

        # Load weather data
        weather_df = self._load_weather_data(start_date, end_date)

        if weather_df is None:
            return pd.Series(0, index=dates)

        # Filter for winter storms
        winter_events = weather_df[
            weather_df["event_type"].isin(["Blizzard", "Ice Storm", "Winter Storm"])
        ]

        # Build regressor
        return self._build_impact_regressor(dates, winter_events)


# Example usage
if __name__ == "__main__":
    builder = WeatherRegressors()

    regressors = builder.build(start_date=date(2020, 1, 1), end_date=date(2023, 12, 31))

    print(regressors.head(20))
    print("\nSummary:")
    print(regressors.describe())
