"""
Strikes ETL Implementation
BLS Work Stoppages - Major strikes and lockouts affecting employment
"""

from datetime import datetime, date
from pathlib import Path
from typing import Optional
import os

import pandas as pd
from loguru import logger

from etl.common.base import BaseETL, ETLConfig, DataSource
from etl.common.downloader import Downloader


# BLS Work Stoppages data
BLS_WORK_STOPPAGES_URL = "https://www.bls.gov/web/wkstp.supp.toc.htm"
BLS_ANNUAL_DATA_URL = "https://download.bls.gov/pub/time.series/ws/"

# Production safety: Set to 'false' in production to fail instead of using fallback data
# Default changed to 'false' for production safety (consistent with Weather ETL)
# Reference: CODEX_VALIDATION_FIX_REQUIRED.md (2025-11-29)
ALLOW_FALLBACK_DATA = os.getenv("ALLOW_FALLBACK_DATA", "false").lower() == "true"


class StrikesETL(BaseETL):
    """
    ETL pipeline for BLS Work Stoppages data

    Data includes:
    - Major work stoppages (1,000+ workers)
    - Workers involved
    - Days idle
    - Industry affected
    - Start and end dates
    - Resolution status
    """

    def __init__(
        self,
        raw_data_path: Path = Path("data/raw/strikes"),
        vintage_path: Path = Path("data/vintages"),
        lookback_years: int = 10,
    ):
        """
        Initialize Strikes ETL

        Args:
            raw_data_path: Path for raw data storage
            vintage_path: Path for vintage snapshots
            lookback_years: Years of history to fetch
        """
        config = ETLConfig(
            source_name=DataSource.STRIKES.value,
            raw_data_path=raw_data_path,
            vintage_path=vintage_path,
            frequency="monthly",  # Aggregate to monthly
            validate_schema=True,
            create_vintage=True,
        )

        super().__init__(config)
        self.lookback_years = lookback_years
        self.downloader = Downloader()

    def extract(self) -> pd.DataFrame:
        """
        Extract strikes data from BLS

        Note: BLS work stoppages data is published as Excel/CSV files
        We'll fetch the most recent data file

        Returns:
            pd.DataFrame: Raw strikes data
        """
        logger.info("Fetching BLS Work Stoppages data...")

        # BLS publishes work stoppages data in text format
        # Series files: ws.data.1.AllData contains all work stoppage records

        try:
            # Try to fetch main data file
            base_url = "https://download.bls.gov/pub/time.series/ws/"

            # Fetch data series file (all work stoppages)
            # Note: File updated to ws.data.1.AllData (as of 9/9/2025)
            data_url = f"{base_url}ws.data.1.AllData"

            logger.info(f"Downloading from {data_url}")

            content = self.downloader.download(data_url)
            decoded_content = content.decode("utf-8")

            # Parse tab-delimited BLS time series format
            from io import StringIO

            df = pd.read_csv(StringIO(decoded_content), sep="\t", skipinitialspace=True)

            # Clean column names (BLS adds trailing spaces)
            df.columns = df.columns.str.strip()

            # Legacy/mock fixtures use a simple comma-delimited event format.
            # Detect it before fetching metadata that only exists for BLS series files.
            if "series_id" not in df.columns:
                legacy_df = pd.read_csv(StringIO(decoded_content))
                legacy_df.columns = legacy_df.columns.str.strip()
                legacy_columns = {col.lower() for col in legacy_df.columns}
                if {"year", "month"}.issubset(legacy_columns):
                    logger.info("Detected legacy strikes CSV format")
                    return legacy_df

            # Also fetch series metadata
            series_url = f"{base_url}ws.series"
            series_content = self.downloader.download(series_url)
            series_df = pd.read_csv(
                StringIO(series_content.decode("utf-8")), sep="\t", skipinitialspace=True
            )
            series_df.columns = series_df.columns.str.strip()

            # Load measure metadata for descriptions
            measure_url = f"{base_url}ws.measure"
            measure_content = self.downloader.download(measure_url)
            measure_df = pd.read_csv(
                StringIO(measure_content.decode("utf-8")), sep="\t", skipinitialspace=True
            )
            measure_df.columns = measure_df.columns.str.strip()

            logger.info(f"Downloaded {len(df)} work stoppage time series observations")

            # Merge with series metadata (series_id, series_title, measure_code)
            df = df.merge(
                series_df[["series_id", "series_title", "measure_code"]], on="series_id", how="left"
            )

            # Merge with measure descriptions
            df = df.merge(
                measure_df[["measure_code", "measure_text"]], on="measure_code", how="left"
            )

            logger.info(f"Loaded metadata for {df['series_id'].nunique()} work stoppage series")

            return df

        except Exception as e:
            logger.warning(f"Failed to fetch from primary source: {e}")

            # Fallback: Create synthetic recent data (only if allowed)
            if ALLOW_FALLBACK_DATA:
                logger.warning("Using fallback strike data (ALLOW_FALLBACK_DATA=true)")
                logger.warning("Set ALLOW_FALLBACK_DATA=false in production to fail instead")
                df = self._create_fallback_data()
                return df
            else:
                logger.error("Strike data fetch failed and ALLOW_FALLBACK_DATA=false")
                raise Exception("Strike data fetch failed and fallback data disabled in production")

    def _create_fallback_data(self) -> pd.DataFrame:
        """
        Create fallback strike data when primary source unavailable
        Based on known major recent strikes for validation

        Returns:
            pd.DataFrame: Fallback data
        """
        logger.warning("Using fallback strike data (limited)")

        # Known major strikes for reference
        strikes = [
            {
                "year": 2023,
                "month": 9,
                "industry": "Motion picture and sound recording",
                "workers_involved": 160000,
                "description": "SAG-AFTRA and Writers Guild strikes",
                "duration_days": 148,
            },
            {
                "year": 2023,
                "month": 9,
                "industry": "Motor vehicles and parts",
                "workers_involved": 25000,
                "description": "UAW targeted strikes",
                "duration_days": 46,
            },
            {
                "year": 2023,
                "month": 8,
                "industry": "Transportation",
                "workers_involved": 340000,
                "description": "UPS threatened strike (averted)",
                "duration_days": 0,
            },
            {
                "year": 2022,
                "month": 12,
                "industry": "Rail transportation",
                "workers_involved": 115000,
                "description": "Rail workers dispute",
                "duration_days": 0,
            },
        ]

        df = pd.DataFrame(strikes)

        return df

    def validate(self, df: pd.DataFrame) -> bool:
        """
        Validate strikes data

        Args:
            df: DataFrame to validate

        Returns:
            bool: True if valid
        """
        logger.info("Validating strikes data...")

        # Check for required columns (flexible based on source)
        if df.empty:
            logger.warning("No strikes data available (this is okay)")
            return True  # Empty is valid (no strikes)

        # Check basic structure
        if "year" not in df.columns and "period" not in df.columns:
            logger.error("Missing date information")
            return False

        logger.info("✓ Strikes validation passed")
        return True

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Transform strikes data

        Args:
            df: Raw DataFrame

        Returns:
            pd.DataFrame: Cleaned DataFrame
        """
        logger.info("Transforming strikes data...")

        if df.empty:
            logger.info("No strikes data to transform")
            return df

        df = df.copy()

        # Standardize column names
        df.columns = df.columns.str.lower().str.strip()

        # Handle different data formats
        if "period" in df.columns:
            # BLS format with period codes
            df["month"] = df["period"].str.extract(r"M(\d+)").astype(float)
            df = df[df["month"] <= 12]  # Exclude annual averages
        elif "month" not in df.columns and "date" not in df.columns:
            # Assume current month if not specified
            df["month"] = datetime.now().month

        # Create date column
        if "date" not in df.columns:
            df["date"] = pd.to_datetime(
                df["year"].astype(str)
                + "-"
                + df["month"].astype(int).astype(str).str.zfill(2)
                + "-01",
                errors="coerce",
            )
        else:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")

        # Standardize industry names
        if "industry_name" in df.columns:
            df["industry"] = df["industry_name"]

        # Extract workers affected
        if "value" in df.columns and "workers" not in df.columns:
            df["workers_involved"] = pd.to_numeric(df["value"], errors="coerce")
        elif "workers_involved" in df.columns:
            df["workers_involved"] = pd.to_numeric(df["workers_involved"], errors="coerce")

        # Calculate monthly aggregates
        # Handle different data formats (new BLS time series vs old format)
        if "measure_code" in df.columns:
            # New BLS time series format - pivot by series
            # WSU010 = workers involved (thousands), WSU100 = number of stoppages

            monthly_agg = (
                df.groupby([pd.Grouper(key="date", freq="M"), "series_id"])
                .agg({"workers_involved": "sum"})
                .reset_index()
            )

            # Pivot to get workers and stoppages as separate columns
            monthly_pivot = monthly_agg.pivot_table(
                index="date", columns="series_id", values="workers_involved", aggfunc="sum"
            ).reset_index()

            # Rename series columns to meaningful names
            column_rename = {
                "WSU001": "days_idleness_thousands",
                "WSU010": "workers_involved_thousands",
                "WSU020": "workers_in_effect_thousands",
                "WSU100": "num_stoppages_beginning",
                "WSU200": "num_stoppages_in_effect",
            }

            monthly_pivot = monthly_pivot.rename(
                columns={
                    col: column_rename.get(col, col)
                    for col in monthly_pivot.columns
                    if col != "date"
                }
            )

            monthly_agg = monthly_pivot
            monthly_agg["industry"] = "All Industries (National)"
            monthly_agg["num_stoppages"] = monthly_agg.get("num_stoppages_beginning", 0)
            monthly_agg["workers_involved"] = (
                monthly_agg.get("workers_involved_thousands", 0) * 1000
            )  # Convert to actual count

        else:
            # Fallback format with direct columns
            agg_dict = {"workers_involved": "sum"}
            if "industry" in df.columns:
                agg_dict["industry"] = (
                    lambda x: ", ".join(x.dropna().unique())
                    if len(x.dropna()) > 0
                    else "All Industries"
                )

            monthly_agg = df.groupby([pd.Grouper(key="date", freq="M")]).agg(agg_dict).reset_index()
            monthly_agg["num_stoppages"] = (
                df.groupby([pd.Grouper(key="date", freq="M")]).size().values
            )

            if "industry" not in monthly_agg.columns:
                monthly_agg["industry"] = "All Industries"

        # Calculate strike impact score (workers × duration proxy)
        monthly_agg["strike_impact_score"] = (
            monthly_agg["workers_involved"] * monthly_agg["num_stoppages"]
        )

        # Flag significant months (>50k workers affected)
        monthly_agg["is_significant_month"] = monthly_agg["workers_involved"] > 50000

        # Add metadata
        monthly_agg["ingested_at"] = datetime.now()
        monthly_agg["source"] = "BLS_Work_Stoppages"

        # Sort by date
        monthly_agg = monthly_agg.sort_values("date")

        logger.info(f"Transformed to {len(monthly_agg)} monthly records")
        logger.info(f"Significant strike months: {monthly_agg['is_significant_month'].sum()}")

        return monthly_agg

    def get_active_strikes(
        self, df: pd.DataFrame, as_of_date: Optional[date] = None
    ) -> pd.DataFrame:
        """
        Get currently active strikes

        Args:
            df: Strikes DataFrame
            as_of_date: Date to check (default: today)

        Returns:
            pd.DataFrame: Active strikes
        """
        as_of_date = as_of_date or date.today()

        # Filter to recent month
        recent = df[df["date"].dt.date >= as_of_date.replace(day=1)]

        # Filter to significant strikes
        active = recent[recent["is_significant_month"] is True]

        return active


def main():
    """Test the Strikes ETL"""
    etl = StrikesETL()
    success = etl.run()

    if success:
        print("✅ Strikes ETL completed successfully")
    else:
        print("❌ Strikes ETL failed")


if __name__ == "__main__":
    main()
