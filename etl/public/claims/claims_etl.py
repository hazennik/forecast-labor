"""
UI Claims ETL Implementation
Downloads and processes weekly unemployment insurance claims data
"""

from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
from loguru import logger

from etl.common.base import BaseETL, ETLConfig, DataSource
from etl.common.downloader import Downloader


# DOL UI Claims Data URLs
DOL_CLAIMS_API = "https://oui.doleta.gov/unemploy/csv/"
DOL_CLAIMS_FILE = "ar539.csv"  # National and state weekly claims


class UIClaimsETL(BaseETL):
    """
    ETL pipeline for UI Claims data

    Data includes:
    - Initial claims (IC)
    - Continued claims (CC)
    - National and all 50 states + DC + territories
    - Weekly frequency (released Thursdays)
    """

    def __init__(
        self,
        raw_data_path: Path = Path("data/raw/claims"),
        vintage_path: Path = Path("data/vintages"),
        include_territories: bool = False,
    ):
        """
        Initialize UI Claims ETL

        Args:
            raw_data_path: Path for raw data storage
            vintage_path: Path for vintage snapshots
            include_territories: Include Puerto Rico, Virgin Islands, etc.
        """
        config = ETLConfig(
            source_name=DataSource.UI_CLAIMS.value,
            raw_data_path=raw_data_path,
            vintage_path=vintage_path,
            frequency="weekly",
            validate_schema=True,
            create_vintage=True,
        )

        super().__init__(config)
        self.include_territories = include_territories
        self.downloader = Downloader()

    def extract(self) -> pd.DataFrame:
        """
        Extract UI Claims data from DOL

        Returns:
            pd.DataFrame: Raw claims data
        """
        url = f"{DOL_CLAIMS_API}{DOL_CLAIMS_FILE}"

        logger.info(f"Fetching UI Claims from {url}")

        try:
            # Download CSV
            content = self.downloader.download(url)

            # Parse CSV
            from io import StringIO

            df = pd.read_csv(StringIO(content.decode("utf-8")))

            logger.info(f"Downloaded {len(df)} rows of claims data")

            return df

        except Exception as e:
            logger.error(f"Failed to extract UI Claims: {e}")
            raise

    def validate(self, df: pd.DataFrame) -> bool:
        """
        Validate UI Claims data

        Args:
            df: DataFrame to validate

        Returns:
            bool: True if valid
        """
        logger.info("Validating UI Claims data...")

        if df.empty:
            logger.error("UI Claims data is empty")
            return False

        df = df.copy()
        df.columns = [str(col).lower().strip() for col in df.columns]

        # DOL has used both descriptive and generic c# schemas.
        # c3/ic = Initial Claims, c8/cc = Continued Claims.
        claim_column_pairs = [("c3", "c8"), ("ic", "cc")]
        claims_cols = next(
            (
                (initial_col, continued_col)
                for initial_col, continued_col in claim_column_pairs
                if initial_col in df.columns and continued_col in df.columns
            ),
            None,
        )

        required_cols = ["rptdate", "st"]
        if claims_cols is not None:
            required_cols.extend(claims_cols)

        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols or claims_cols is None:
            if claims_cols is None:
                missing_cols.extend(["c3/c8 or ic/cc"])
            logger.error(f"Missing required columns: {missing_cols}")
            return False

        initial_col, continued_col = claims_cols

        # Check for null values in critical columns
        if df[["rptdate", "st", initial_col, continued_col]].isnull().any().any():
            logger.warning("Found null values in critical columns")

        # Check data types
        try:
            pd.to_datetime(df["rptdate"])
        except Exception as e:
            logger.error(f"Invalid date format in rptdate: {e}")
            return False

        # Check for reasonable values (claims should be positive)
        initial_claims = pd.to_numeric(df[initial_col], errors="coerce")
        continued_claims = pd.to_numeric(df[continued_col], errors="coerce")
        if initial_claims.isna().any() or continued_claims.isna().any():
            logger.error("Found non-numeric claims values")
            return False

        if (initial_claims < 0).any() or (continued_claims < 0).any():
            logger.error("Found negative claims values")
            return False

        # Check for recent data (should have data from last 30 days)
        df_copy = df.copy()
        df_copy["rptdate"] = pd.to_datetime(df_copy["rptdate"])
        most_recent = df_copy["rptdate"].max()

        if most_recent < datetime.now() - timedelta(days=30):
            logger.warning(f"Data may be stale. Most recent: {most_recent}")

        logger.info("✓ UI Claims validation passed")
        return True

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Transform UI Claims data

        Args:
            df: Raw DataFrame

        Returns:
            pd.DataFrame: Cleaned DataFrame
        """
        logger.info("Transforming UI Claims data...")

        df = df.copy()

        # Standardize column names
        df.columns = df.columns.str.lower().str.strip()

        # Parse dates
        df["rptdate"] = pd.to_datetime(df["rptdate"])
        df["filed_week_ended"] = pd.to_datetime(df.get("filed_week_ended", df["rptdate"]))

        # Rename columns for clarity
        # NOTE: As of 2025, DOL changed schema to generic c# columns
        # c3 = IC (Initial Claims), c8 = CW (Continued Claims)
        df.rename(
            columns={
                "rptdate": "report_date",
                "st": "state_code",
                "c3": "initial_claims",  # IC in DOL spec
                "c8": "continued_claims",  # CW in DOL spec
                "ic": "initial_claims",  # Legacy descriptive schema
                "cc": "continued_claims",  # Legacy descriptive schema
                "c13": "continued_claims_13week",  # if exists
            },
            inplace=True,
        )

        # Keep only essential columns to avoid mixed-type issues with c14-c23
        essential_cols = [
            col
            for col in [
                "report_date",
                "state_code",
                "initial_claims",
                "continued_claims",
                "continued_claims_13week",
                "filed_week_ended",
            ]
            if col in df.columns
        ]
        df = df[essential_cols]

        # Filter states if needed
        if not self.include_territories:
            # Standard 50 states + DC + National
            valid_states = [
                "US",  # National
                "AL",
                "AK",
                "AZ",
                "AR",
                "CA",
                "CO",
                "CT",
                "DE",
                "FL",
                "GA",
                "HI",
                "ID",
                "IL",
                "IN",
                "IA",
                "KS",
                "KY",
                "LA",
                "ME",
                "MD",
                "MA",
                "MI",
                "MN",
                "MS",
                "MO",
                "MT",
                "NE",
                "NV",
                "NH",
                "NJ",
                "NM",
                "NY",
                "NC",
                "ND",
                "OH",
                "OK",
                "OR",
                "PA",
                "RI",
                "SC",
                "SD",
                "TN",
                "TX",
                "UT",
                "VT",
                "VA",
                "WA",
                "WV",
                "WI",
                "WY",
                "DC",
            ]
            df = df[df["state_code"].isin(valid_states)]

        # Convert claims to numeric (handle any string issues)
        df["initial_claims"] = pd.to_numeric(df["initial_claims"], errors="coerce")
        df["continued_claims"] = pd.to_numeric(df["continued_claims"], errors="coerce")

        # Convert c13 if it exists (handle mixed types)
        if "continued_claims_13week" in df.columns:
            df["continued_claims_13week"] = pd.to_numeric(
                df["continued_claims_13week"], errors="coerce"
            )

        # Sort by date and state
        df = df.sort_values(["report_date", "state_code"])

        # Add 4-week moving average (common smoothing)
        df["initial_claims_4wk_ma"] = df.groupby("state_code")["initial_claims"].transform(
            lambda x: x.rolling(4, min_periods=1).mean()
        )

        # Add metadata columns
        df["ingested_at"] = datetime.now()
        df["source"] = "DOL_ETA"

        logger.info(f"Transformed data: {len(df)} rows, {df['state_code'].nunique()} states")

        return df

    def get_latest_week(self) -> Optional[date]:
        """
        Get the most recent week available in the data

        Returns:
            date: Most recent week end date
        """
        try:
            df = self.extract()
            df["rptdate"] = pd.to_datetime(df["rptdate"])
            return df["rptdate"].max().date()
        except Exception as e:
            logger.error(f"Failed to get latest week: {e}")
            return None


def main():
    """Test the UI Claims ETL"""
    etl = UIClaimsETL()
    success = etl.run()

    if success:
        print("✅ UI Claims ETL completed successfully")
    else:
        print("❌ UI Claims ETL failed")


if __name__ == "__main__":
    main()
