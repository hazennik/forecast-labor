"""
BLS CES ETL Implementation
Current Employment Statistics - Nonfarm Payrolls and related series
"""

from datetime import datetime, date
from pathlib import Path
from typing import Optional, List, Dict
import time

import pandas as pd
from loguru import logger

from etl.common.base import BaseETL, ETLConfig, DataSource
from etl.common.downloader import Downloader


# BLS API Configuration
BLS_API_BASE = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
BLS_API_V1 = "https://api.bls.gov/publicAPI/v1/timeseries/data/"


# Key CES Series IDs
CES_SERIES = {
    # National Employment
    "CES0000000001": "Total Nonfarm (thousands)",
    "CES0500000001": "Total Private (thousands)",
    "CES9000000001": "Government (thousands)",
    
    # Major Sectors
    "CES0600000001": "Goods-Producing (thousands)",
    "CES0700000001": "Service-Providing (thousands)",
    "CES0800000001": "Private Service-Providing (thousands)",
    
    # Industries (Top predictors)
    "CES4200000001": "Retail Trade (thousands)",
    "CES7000000001": "Leisure and Hospitality (thousands)",
    "CES6500000001": "Professional and Business Services (thousands)",
    "CES6562000001": "Education and Health Services (thousands)",
    "CES3000000001": "Manufacturing (thousands)",
    "CES2000000001": "Construction (thousands)",
    
    # Wages
    "CES0000000003": "Average Hourly Earnings - Total Private (dollars)",
    "CES0500000003": "Average Hourly Earnings - Private (dollars)",
    
    # Hours
    "CES0000000002": "Average Weekly Hours - Total Private",
    "CES0500000002": "Average Weekly Hours - Private",
}


class CESETL(BaseETL):
    """
    ETL pipeline for BLS Current Employment Statistics (CES)
    
    Critical features:
    - Maintains vintages (first print vs revisions)
    - Handles monthly releases
    - Tracks revision history
    - National and sector-level data
    """
    
    def __init__(
        self,
        raw_data_path: Path = Path("data/raw/bls_ces"),
        vintage_path: Path = Path("data/vintages"),
        api_key: Optional[str] = None,
        lookback_years: int = 10
    ):
        """
        Initialize CES ETL
        
        Args:
            raw_data_path: Path for raw data storage
            vintage_path: Path for vintage snapshots
            api_key: BLS API key (optional, increases rate limits)
            lookback_years: Years of history to fetch
        """
        config = ETLConfig(
            source_name=DataSource.BLS_CES.value,
            raw_data_path=raw_data_path,
            vintage_path=vintage_path,
            frequency="monthly",
            validate_schema=True,
            create_vintage=True
        )
        
        super().__init__(config)
        self.api_key = api_key
        self.lookback_years = lookback_years
        self.downloader = Downloader()
    
    def extract(self) -> pd.DataFrame:
        """
        Extract CES data from BLS API
        
        Returns:
            pd.DataFrame: Raw CES data
        """
        # Calculate year range
        end_year = datetime.now().year
        start_year = end_year - self.lookback_years
        
        logger.info(f"Fetching CES data for {start_year}-{end_year}")
        
        all_data = []
        
        # BLS API limits: 50 series per request, 10 years max
        series_list = list(CES_SERIES.keys())
        
        # Process in batches of 50 series
        batch_size = 50 if self.api_key else 25  # Smaller batches without API key
        
        for i in range(0, len(series_list), batch_size):
            batch = series_list[i:i + batch_size]
            
            logger.info(f"Fetching batch {i//batch_size + 1} ({len(batch)} series)...")
            
            try:
                batch_data = self._fetch_series_batch(batch, start_year, end_year)
                all_data.extend(batch_data)
                
                # Rate limiting (20 requests/min without key, 120 with key)
                delay = 3 if not self.api_key else 0.5
                time.sleep(delay)
                
            except Exception as e:
                logger.error(f"Error fetching batch: {e}")
                raise
        
        if not all_data:
            raise ValueError("No CES data retrieved")
        
        # Convert to DataFrame
        df = pd.DataFrame(all_data)
        
        logger.info(f"Downloaded {len(df)} observations across {df['series_id'].nunique()} series")
        
        return df
    
    def _fetch_series_batch(
        self,
        series_ids: List[str],
        start_year: int,
        end_year: int
    ) -> List[Dict]:
        """
        Fetch a batch of series from BLS API
        
        Args:
            series_ids: List of series IDs to fetch
            start_year: Start year
            end_year: End year
            
        Returns:
            list: List of observation dictionaries
        """
        # Build request payload
        payload = {
            "seriesid": series_ids,
            "startyear": str(start_year),
            "endyear": str(end_year),
        }
        
        if self.api_key:
            payload["registrationkey"] = self.api_key
        
        # Use v2 if we have API key, v1 otherwise
        url = BLS_API_BASE if self.api_key else BLS_API_V1
        
        # Make request
        import requests
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get("status") != "REQUEST_SUCCEEDED":
            error_msg = data.get("message", ["Unknown error"])[0]
            raise ValueError(f"BLS API error: {error_msg}")
        
        # Parse response
        results = []
        for series in data.get("Results", {}).get("series", []):
            series_id = series["seriesID"]
            series_name = CES_SERIES.get(series_id, "Unknown")
            
            for obs in series.get("data", []):
                results.append({
                    "series_id": series_id,
                    "series_name": series_name,
                    "year": int(obs["year"]),
                    "period": obs["period"],
                    "period_name": obs.get("periodName", ""),
                    "value": obs["value"],
                    "footnotes": obs.get("footnotes", [])
                })
        
        return results
    
    def validate(self, df: pd.DataFrame) -> bool:
        """
        Validate CES data
        
        Args:
            df: DataFrame to validate
            
        Returns:
            bool: True if valid
        """
        logger.info("Validating CES data...")
        
        # Required columns
        required_cols = ["series_id", "year", "period", "value"]
        
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            logger.error(f"Missing required columns: {missing_cols}")
            return False
        
        # Check for null values
        if df[required_cols].isnull().any().any():
            logger.error("Found null values in critical columns")
            return False
        
        # Check for NFP series (most critical)
        if "CES0000000001" not in df["series_id"].values:
            logger.error("Total Nonfarm Payrolls series not found")
            return False
        
        # Check for recent data
        most_recent_year = df["year"].max()
        current_year = datetime.now().year
        
        if most_recent_year < current_year - 1:
            logger.warning(f"Data may be stale. Most recent: {most_recent_year}")
        
        # Check for reasonable number of series
        n_series = df["series_id"].nunique()
        if n_series < 10:
            logger.warning(f"Only {n_series} series found (expected ~20)")
        
        logger.info("✓ CES validation passed")
        return True
    
    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Transform CES data
        
        Args:
            df: Raw DataFrame
            
        Returns:
            pd.DataFrame: Cleaned DataFrame
        """
        logger.info("Transforming CES data...")
        
        df = df.copy()
        
        # Parse period (M01-M13, where M13 is annual average)
        df["month"] = df["period"].str.extract(r"M(\d+)").astype(int)
        
        # Filter to monthly data only (exclude M13 annual averages)
        df = df[df["month"] <= 12]
        
        # Create date column
        df["date"] = pd.to_datetime(
            df["year"].astype(str) + "-" + df["month"].astype(str).str.zfill(2) + "-01"
        )
        
        # Convert value to numeric
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        
        # Calculate month-over-month change
        df = df.sort_values(["series_id", "date"])
        df["mom_change"] = df.groupby("series_id")["value"].diff()
        
        # Calculate year-over-year change
        df["yoy_change"] = df.groupby("series_id")["value"].diff(12)
        
        # Add series metadata
        df["unit"] = "thousands"  # Most CES series are in thousands
        df["unit"] = df["series_id"].apply(
            lambda x: "dollars" if x.endswith("003") else "hours" if x.endswith("002") else "thousands"
        )
        
        # Flag preliminary vs revised (based on footnotes)
        df["is_preliminary"] = df["footnotes"].apply(
            lambda x: any("preliminary" in str(f).lower() for f in x) if isinstance(x, list) else False
        )
        
        # Add metadata
        df["ingested_at"] = datetime.now()
        df["source"] = "BLS_CES_API"
        
        # Sort final output
        df = df.sort_values(["date", "series_id"])
        
        logger.info(f"Transformed data: {len(df)} observations, {df['series_id'].nunique()} series")
        
        return df
    
    def get_nfp_latest(self, df: pd.DataFrame) -> Optional[Dict]:
        """
        Get latest NFP reading
        
        Args:
            df: CES DataFrame
            
        Returns:
            dict: Latest NFP data
        """
        nfp = df[df["series_id"] == "CES0000000001"].copy()
        
        if nfp.empty:
            return None
        
        latest = nfp.iloc[-1]
        
        return {
            "date": latest["date"],
            "level": latest["value"],
            "mom_change": latest["mom_change"],
            "yoy_change": latest["yoy_change"],
            "is_preliminary": latest["is_preliminary"]
        }


def main():
    """Test the CES ETL"""
    etl = CESETL()
    success = etl.run()
    
    if success:
        print("✅ CES ETL completed successfully")
    else:
        print("❌ CES ETL failed")


if __name__ == "__main__":
    main()

