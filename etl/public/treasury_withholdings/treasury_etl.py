"""
Treasury Withholdings ETL Implementation
Downloads and processes daily Treasury tax withholding data
"""

from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
from loguru import logger

from etl.common.base import BaseETL, ETLConfig, DataSource
from etl.common.downloader import Downloader


# Treasury Daily Statement URLs (Updated 2025-11-28: v2 endpoint deprecated, now using v1)
TREASURY_BASE_URL = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"
TREASURY_ENDPOINT = "/v1/accounting/dts/deposits_withdrawals_operating_cash"


class TreasuryWithholdingsETL(BaseETL):
    """
    ETL pipeline for Treasury Withholdings data

    Data includes:
    - Individual Income Tax Withheld (daily)
    - Federal Tax Deposits (daily)
    - From Daily Treasury Statement Table 3
    - Business days only
    """

    def __init__(
        self,
        raw_data_path: Path = Path("data/raw/treasury"),
        vintage_path: Path = Path("data/vintages"),
        lookback_days: int = 90,
    ):
        """
        Initialize Treasury Withholdings ETL

        Args:
            raw_data_path: Path for raw data storage
            vintage_path: Path for vintage snapshots
            lookback_days: Days of history to fetch
        """
        config = ETLConfig(
            source_name=DataSource.TREASURY_WITHHOLDINGS.value,
            raw_data_path=raw_data_path,
            vintage_path=vintage_path,
            frequency="daily",
            validate_schema=True,
            create_vintage=True,
        )

        super().__init__(config)
        self.lookback_days = lookback_days
        self.downloader = Downloader()

    def extract(self) -> pd.DataFrame:
        """
        Extract Treasury withholdings data from Fiscal Data API

        Returns:
            pd.DataFrame: Raw withholdings data
        """
        # Calculate date range
        end_date = date.today()
        start_date = end_date - timedelta(days=self.lookback_days)

        logger.info(f"Fetching Treasury data from {start_date} to {end_date}")

        # API parameters
        params = {
            "filter": f"record_date:gte:{start_date},record_date:lte:{end_date}",
            "sort": "-record_date",
            "page[size]": 1000,  # Max per page
        }

        all_data = []
        page_number = 1

        while True:
            params["page[number]"] = page_number

            try:
                logger.info(f"Fetching page {page_number}...")

                response = self.downloader.download_json(
                    f"{TREASURY_BASE_URL}{TREASURY_ENDPOINT}", params=params
                )

                if not response or "data" not in response:
                    logger.warning("No data in response")
                    break

                data = response["data"]

                if not data:
                    logger.info("No more data available")
                    break

                all_data.extend(data)

                # Check if there are more pages
                meta = response.get("meta", {})
                total_pages = meta.get("total-pages", 1)

                logger.info(f"Retrieved {len(data)} records (page {page_number}/{total_pages})")

                if page_number >= total_pages:
                    break

                page_number += 1

            except Exception as e:
                logger.error(f"Error fetching page {page_number}: {e}")
                if page_number == 1:
                    raise  # Fail if first page fails
                else:
                    break  # Partial success is okay

        if not all_data:
            raise ValueError("No Treasury data retrieved")

        # Convert to DataFrame
        df = pd.DataFrame(all_data)

        logger.info(f"Downloaded {len(df)} days of Treasury data")

        return df

    def validate(self, df: pd.DataFrame) -> bool:
        """
        Validate Treasury withholdings data

        Args:
            df: DataFrame to validate

        Returns:
            bool: True if valid
        """
        logger.info("Validating Treasury withholdings data...")

        # Required columns
        required_cols = ["record_date"]

        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            logger.error(f"Missing required columns: {missing_cols}")
            return False

        # Check for null dates
        if df["record_date"].isnull().any():
            logger.error("Found null dates")
            return False

        # Check date format
        try:
            pd.to_datetime(df["record_date"])
        except Exception as e:
            logger.error(f"Invalid date format: {e}")
            return False

        # Check for reasonable data freshness (last 7 days)
        df_copy = df.copy()
        df_copy["record_date"] = pd.to_datetime(df_copy["record_date"])
        most_recent = df_copy["record_date"].max()

        days_old = (datetime.now() - most_recent).days
        if days_old > 7:
            logger.warning(f"Data may be stale. Most recent: {most_recent} ({days_old} days old)")

        # Check for minimum rows
        if len(df) < 30:
            logger.warning(f"Only {len(df)} rows of data (expected ~90)")

        logger.info("✓ Treasury withholdings validation passed")
        return True

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Transform Treasury withholdings data

        Args:
            df: Raw DataFrame

        Returns:
            pd.DataFrame: Cleaned DataFrame
        """
        logger.info("Transforming Treasury withholdings data...")

        df = df.copy()

        # Parse dates
        df["record_date"] = pd.to_datetime(df["record_date"])

        # Extract key withholding columns
        # Treasury API returns nested structure - flatten important fields

        # Individual Income Tax Withheld is the key series
        # Look for columns containing withholding data
        withholding_cols = [col for col in df.columns if "withhold" in col.lower()]
        tax_cols = [col for col in df.columns if "income" in col.lower() and "tax" in col.lower()]

        logger.info(f"Found withholding columns: {withholding_cols}")
        logger.info(f"Found tax columns: {tax_cols}")

        # Common column names in Treasury data
        rename_map = {
            "record_date": "date",
            "account_type": "account_type",
            "classification_desc": "classification",
            "close_today_bal": "balance",
            "open_today_bal": "opening_balance",
            "open_month_bal": "opening_month_balance",
        }

        # Apply renaming for columns that exist
        rename_map = {k: v for k, v in rename_map.items() if k in df.columns}
        df.rename(columns=rename_map, inplace=True)

        # Filter to income tax withholding records
        if "classification" in df.columns:
            df = df[df["classification"].str.contains("Income Tax", case=False, na=False)]

        # Convert numeric columns
        numeric_cols = ["balance", "opening_balance", "opening_month_balance"]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # Sort by date
        df = df.sort_values("date")

        # Calculate daily withholding (change from previous day)
        if "balance" in df.columns:
            df["daily_withholding"] = df["balance"].diff()

        # Calculate rolling averages
        if "daily_withholding" in df.columns:
            df["withholding_5day_ma"] = df["daily_withholding"].rolling(5, min_periods=1).mean()
            df["withholding_20day_ma"] = df["daily_withholding"].rolling(20, min_periods=1).mean()

        # Add business day flags
        df["is_business_day"] = ~df["date"].dt.dayofweek.isin([5, 6])  # Not Sat/Sun

        # Add pay period indicators (bi-weekly, common for payroll)
        df["day_of_month"] = df["date"].dt.day
        df["is_mid_month"] = df["day_of_month"].between(14, 16)
        df["is_month_end"] = df["day_of_month"].between(28, 31)

        # Add metadata
        df["ingested_at"] = datetime.now()
        df["source"] = "Treasury_Fiscal_Data_API"

        logger.info(f"Transformed data: {len(df)} days")

        return df

    def get_latest_date(self) -> Optional[date]:
        """
        Get the most recent date available in the data

        Returns:
            date: Most recent date
        """
        try:
            df = self.extract()
            df["record_date"] = pd.to_datetime(df["record_date"])
            return df["record_date"].max().date()
        except Exception as e:
            logger.error(f"Failed to get latest date: {e}")
            return None

    def get_monthly_aggregate(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Aggregate daily data to monthly (for modeling)

        Args:
            df: Daily DataFrame

        Returns:
            pd.DataFrame: Monthly aggregates
        """
        if "daily_withholding" not in df.columns:
            logger.warning("daily_withholding column not found")
            return df

        df_monthly = df.copy()
        df_monthly["year_month"] = df_monthly["date"].dt.to_period("M")

        monthly = (
            df_monthly.groupby("year_month")
            .agg(
                {
                    "daily_withholding": ["sum", "mean", "std", "count"],
                    "balance": "last",
                    "date": "max",
                }
            )
            .reset_index()
        )

        monthly.columns = [
            "year_month",
            "monthly_withholding_sum",
            "daily_withholding_mean",
            "daily_withholding_std",
            "business_days",
            "month_end_balance",
            "last_date",
        ]

        logger.info(f"Created monthly aggregates: {len(monthly)} months")

        return monthly


def main():
    """Test the Treasury Withholdings ETL"""
    etl = TreasuryWithholdingsETL()
    success = etl.run()

    if success:
        print("✅ Treasury Withholdings ETL completed successfully")
    else:
        print("❌ Treasury Withholdings ETL failed")


if __name__ == "__main__":
    main()
