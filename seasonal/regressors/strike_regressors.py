"""
Strike Regressors
Builds regressors for major labor strike impacts on employment data
"""

from datetime import date
from typing import Optional

import pandas as pd
from loguru import logger

from .regressor_builder import RegressorBuilder, create_date_range
from etl.common.storage import StorageClient


class StrikeRegressors(RegressorBuilder):
    """
    Builder for strike impact regressors

    Major strikes can significantly affect employment readings,
    especially in manufacturing and transportation sectors
    """

    def __init__(self, storage_client: Optional[StorageClient] = None):
        """
        Initialize strike regressors builder

        Args:
            storage_client: Storage client for accessing strike data
        """
        super().__init__("strikes")
        self.storage_client = storage_client or StorageClient()

    def build(
        self,
        start_date: date,
        end_date: date,
        frequency: str = "monthly",
        min_workers: int = 10000,
        min_days: int = 7,
    ) -> pd.DataFrame:
        """
        Build strike impact regressors

        Args:
            start_date: Start date
            end_date: End date
            frequency: Time frequency
            min_workers: Minimum workers for regressor (default 10k)
            min_days: Minimum strike duration in days

        Returns:
            DataFrame with strike regressors
        """
        logger.info(f"Building strike regressors from {start_date} to {end_date}")

        dates = create_date_range(start_date, end_date, frequency)

        # Load strike data
        strikes_df = self._load_strikes_data(start_date, end_date)

        if strikes_df is None or len(strikes_df) == 0:
            logger.warning("No strike data available - creating empty regressors")
            return pd.DataFrame({"strike_impact": 0}, index=dates)

        # Filter by significance
        major_strikes = strikes_df[
            (strikes_df["workers_involved"] >= min_workers)
            & (strikes_df["days_duration"] >= min_days)
        ].copy()

        logger.info(f"Found {len(major_strikes)} major strikes")

        # Build regressors
        regressors = pd.DataFrame(index=dates)

        # Overall strike impact
        regressors["strike_impact"] = self._build_impact_regressor(dates, major_strikes)

        # Sector-specific regressors (if sector info available)
        if "sector" in major_strikes.columns:
            for sector in ["manufacturing", "transportation", "services"]:
                sector_strikes = major_strikes[major_strikes["sector"] == sector]
                if len(sector_strikes) > 0:
                    regressors[f"strike_{sector}"] = self._build_impact_regressor(
                        dates, sector_strikes
                    )

        logger.info(f"Created {len(regressors.columns)} strike regressors")

        return regressors

    def _load_strikes_data(self, start_date: date, end_date: date) -> Optional[pd.DataFrame]:
        """
        Load strikes data from storage

        Args:
            start_date: Start date
            end_date: End date

        Returns:
            DataFrame with strike data or None
        """
        try:
            # Load most recent vintage
            strikes_df = self.storage_client.read_parquet("vintages/strikes/latest/strikes.parquet")

            if strikes_df is None:
                return None

            # Ensure date columns
            if "start_date" in strikes_df.columns:
                strikes_df["start_date"] = pd.to_datetime(strikes_df["start_date"])
            if "end_date" in strikes_df.columns:
                strikes_df["end_date"] = pd.to_datetime(strikes_df["end_date"])

            # Filter date range
            if "start_date" in strikes_df.columns:
                strikes_df = strikes_df[
                    (strikes_df["start_date"] >= pd.Timestamp(start_date))
                    & (strikes_df["start_date"] <= pd.Timestamp(end_date))
                ]

            return strikes_df

        except Exception as e:
            logger.error(f"Failed to load strike data: {e}")
            return None

    def _build_impact_regressor(
        self, dates: pd.DatetimeIndex, strikes_df: pd.DataFrame
    ) -> pd.Series:
        """
        Build strike impact regressor from strike events

        Impact is proportional to:
        - Number of workers involved
        - Duration of strike
        - Timing within survey week

        Args:
            dates: Date range
            strikes_df: Strike events

        Returns:
            Series with impact values
        """
        regressor = pd.Series(0.0, index=dates)

        for _, strike in strikes_df.iterrows():
            start_date = strike.get("start_date")
            end_date = strike.get("end_date")
            workers = strike.get("workers_involved", 0)

            if pd.isna(start_date) or workers == 0:
                continue

            # Calculate impact score
            # Normalize by 10k workers
            impact_score = workers / 10000.0

            # Apply impact to affected months
            strike_start = pd.Timestamp(start_date)
            strike_end = pd.Timestamp(end_date) if not pd.isna(end_date) else strike_start

            # Find overlapping periods
            start_period = strike_start.to_period("M")
            end_period = strike_end.to_period("M")

            for period in pd.period_range(start_period, end_period, freq="M"):
                mask = dates.to_period("M") == period

                # Add impact (can accumulate if multiple strikes)
                regressor[mask] += impact_score

        # Cap impact at reasonable level
        regressor = regressor.clip(upper=10.0)

        return regressor

    def build_specific_event_regressor(
        self,
        start_date: date,
        end_date: date,
        event_name: str,
        event_start: date,
        event_end: date,
        workers: int,
        sector: Optional[str] = None,
    ) -> pd.Series:
        """
        Build regressor for a specific known strike event

        Useful for major historical strikes that require manual coding

        Args:
            start_date: Series start date
            end_date: Series end date
            event_name: Strike name/description
            event_start: Strike start date
            event_end: Strike end date
            workers: Workers involved
            sector: Optional sector

        Returns:
            Series with regressor values
        """
        dates = create_date_range(start_date, end_date, "monthly")

        # Calculate impact
        impact_score = workers / 10000.0

        # Create impulse over strike period
        regressor = pd.Series(0.0, index=dates)

        strike_mask = (dates >= event_start) & (dates <= event_end)
        regressor[strike_mask] = impact_score

        logger.info(f"Created regressor for {event_name}: {workers} workers")

        return regressor


# Example major strikes for manual coding
MAJOR_STRIKES = [
    {
        "name": "GM Strike 2019",
        "start": date(2019, 9, 16),
        "end": date(2019, 10, 25),
        "workers": 48000,
        "sector": "manufacturing",
    },
    {
        "name": "UAW Strike 2023",
        "start": date(2023, 9, 15),
        "end": date(2023, 10, 30),
        "workers": 146000,
        "sector": "manufacturing",
    },
]


# Example usage
if __name__ == "__main__":
    builder = StrikeRegressors()

    regressors = builder.build(
        start_date=date(2019, 1, 1), end_date=date(2023, 12, 31), min_workers=10000
    )

    print(regressors.head(20))
