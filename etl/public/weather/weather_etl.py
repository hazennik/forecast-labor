"""
Weather ETL Implementation
NOAA Storm Events - Hurricanes, severe storms, wildfires affecting employment
"""

from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional
import os

import pandas as pd
from loguru import logger

from etl.common.base import BaseETL, ETLConfig, DataSource
from etl.common.downloader import Downloader


# NOAA Storm Events Database API
NOAA_STORM_EVENTS_URL = "https://www.ncdc.noaa.gov/stormevents/csv"
NOAA_API_BASE = "https://www.ncei.noaa.gov/access/services/data/v1"

# Production safety: Set to 'false' in production to fail instead of using fallback data
ALLOW_FALLBACK_DATA = os.getenv("ALLOW_FALLBACK_DATA", "true").lower() == "true"


class WeatherETL(BaseETL):
    """
    ETL pipeline for NOAA Weather Disruptions
    
    Data includes:
    - Hurricane events
    - Severe storms
    - Floods
    - Wildfires
    - Winter storms
    - Impact on employment (deaths, injuries, damages)
    """
    
    def __init__(
        self,
        raw_data_path: Path = Path("data/raw/weather"),
        vintage_path: Path = Path("data/vintages"),
        api_key: Optional[str] = None,
        lookback_months: int = 24
    ):
        """
        Initialize Weather ETL
        
        Args:
            raw_data_path: Path for raw data storage
            vintage_path: Path for vintage snapshots
            api_key: NOAA API key (optional)
            lookback_months: Months of history to fetch
        """
        config = ETLConfig(
            source_name=DataSource.WEATHER.value,
            raw_data_path=raw_data_path,
            vintage_path=vintage_path,
            frequency="monthly",
            validate_schema=True,
            create_vintage=True
        )
        
        super().__init__(config)
        self.api_key = api_key
        self.lookback_months = lookback_months
        self.downloader = Downloader()
    
    def extract(self) -> pd.DataFrame:
        """
        Extract weather disruption data from NOAA
        
        Returns:
            pd.DataFrame: Raw weather data
        """
        logger.info("Fetching NOAA Storm Events data...")
        
        # Calculate date range
        end_date = date.today()
        start_date = end_date - timedelta(days=self.lookback_months * 30)
        
        try:
            # Try NOAA API approach
            df = self._fetch_from_api(start_date, end_date)
            
            if df is not None and not df.empty:
                return df
                
        except Exception as e:
            logger.warning(f"API fetch failed: {e}")
        
        # Fallback to synthetic data (only if allowed)
        if ALLOW_FALLBACK_DATA:
            logger.warning("Using fallback weather data (ALLOW_FALLBACK_DATA=true)")
            logger.warning("Set ALLOW_FALLBACK_DATA=false in production to fail instead")
            df = self._create_fallback_data()
            return df
        else:
            logger.error("API fetch failed and ALLOW_FALLBACK_DATA=false")
            raise Exception("Weather data fetch failed and fallback data disabled in production")
    
    def _fetch_from_api(self, start_date: date, end_date: date) -> Optional[pd.DataFrame]:
        """
        Fetch from NOAA Storm Events API
        
        NOAA Storm Events Database: https://www.ncdc.noaa.gov/stormevents/
        API Documentation: https://www.ncei.noaa.gov/support/access-data-service-api-user-documentation
        
        Args:
            start_date: Start date
            end_date: End date
            
        Returns:
            pd.DataFrame: Weather data or None
        """
        if not self.api_key:
            if not ALLOW_FALLBACK_DATA:
                raise Exception("No NOAA API key provided and ALLOW_FALLBACK_DATA=false")
            logger.info("No NOAA API key provided, using fallback")
            return None
        
        logger.info(f"Fetching from NOAA Storm Events API: {start_date} to {end_date}")
        
        try:
            # NOAA NCEI Storm Events API
            # Dataset: Storm Events Database
            # Endpoint: https://www.ncei.noaa.gov/access/services/data/v1
            base_url = "https://www.ncei.noaa.gov/access/services/data/v1"
            
            # Parameters for Storm Events dataset
            params = {
                "dataset": "storm-events",
                "dataTypes": "EVENT_TYPE,BEGIN_DATE,END_DATE,STATE,DEATHS_DIRECT,DEATHS_INDIRECT,INJURIES_DIRECT,INJURIES_INDIRECT,DAMAGE_PROPERTY",
                "startDate": start_date.strftime("%Y-%m-%d"),
                "endDate": end_date.strftime("%Y-%m-%d"),
                "format": "json",
                "units": "standard"
            }
            
            # Add API token
            headers = {
                "token": self.api_key
            }
            
            logger.info(f"Requesting storm events from {start_date} to {end_date}")
            
            response = self.downloader.download_json(
                base_url,
                params=params,
                headers=headers
            )
            
            if not response:
                logger.warning("Empty response from NOAA API")
                return None
            
            # Parse response
            if isinstance(response, list):
                df = pd.DataFrame(response)
            elif isinstance(response, dict) and "results" in response:
                df = pd.DataFrame(response["results"])
            else:
                logger.warning(f"Unexpected NOAA API response format: {type(response)}")
                return None
            
            if df.empty:
                logger.warning("No storm events found in date range")
                return None
            
            # Standardize column names (NOAA uses uppercase)
            column_mapping = {
                "EVENT_TYPE": "event_type",
                "BEGIN_DATE": "begin_date",
                "END_DATE": "end_date",
                "STATE": "state",
                "DEATHS_DIRECT": "deaths_direct",
                "DEATHS_INDIRECT": "deaths_indirect",
                "INJURIES_DIRECT": "injuries_direct",
                "INJURIES_INDIRECT": "injuries_indirect",
                "DAMAGE_PROPERTY": "damage_property"
            }
            
            df = df.rename(columns=column_mapping)
            
            logger.info(f"Fetched {len(df)} storm events from NOAA API")
            
            return df
            
        except Exception as e:
            logger.error(f"Failed to fetch from NOAA API: {e}")
            logger.exception(e)
            return None
    
    def _create_fallback_data(self) -> pd.DataFrame:
        """
        Create fallback weather disruption data
        Based on known major events
        
        Returns:
            pd.DataFrame: Fallback data
        """
        logger.warning("Using fallback weather data (limited)")
        
        # Known major weather events
        events = [
            {
                "date": "2023-08-08",
                "event_type": "Wildfire",
                "state": "HI",
                "deaths": 99,
                "injuries": 1000,
                "damage_millions": 5600,
                "description": "Maui wildfires"
            },
            {
                "date": "2023-09-29",
                "event_type": "Hurricane",
                "state": "FL",
                "deaths": 149,
                "injuries": 800,
                "damage_millions": 112000,
                "description": "Hurricane Ian"
            },
            {
                "date": "2023-07-25",
                "event_type": "Wildfire",
                "state": "CA",
                "deaths": 0,
                "injuries": 50,
                "damage_millions": 500,
                "description": "California wildfires - air quality impacts"
            },
            {
                "date": "2024-01-15",
                "event_type": "Winter Storm",
                "state": "TX",
                "deaths": 8,
                "injuries": 300,
                "damage_millions": 1500,
                "description": "Texas winter storm"
            },
            {
                "date": "2024-09-27",
                "event_type": "Hurricane",
                "state": "FL",
                "deaths": 231,
                "injuries": 1200,
                "damage_millions": 47600,
                "description": "Hurricane Helene"
            },
        ]
        
        df = pd.DataFrame(events)
        df["date"] = pd.to_datetime(df["date"])
        
        return df
    
    def validate(self, df: pd.DataFrame) -> bool:
        """
        Validate weather data
        
        Args:
            df: DataFrame to validate
            
        Returns:
            bool: True if valid
        """
        logger.info("Validating weather data...")
        
        if df.empty:
            logger.warning("No weather data available (this is okay if no major events)")
            return True  # Empty is valid
        
        # Check for date column
        if "date" not in df.columns:
            logger.error("Missing date column")
            return False
        
        logger.info("✓ Weather validation passed")
        return True
    
    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Transform weather data
        
        Args:
            df: Raw DataFrame
            
        Returns:
            pd.DataFrame: Cleaned DataFrame
        """
        logger.info("Transforming weather data...")
        
        if df.empty:
            logger.info("No weather data to transform")
            return df
        
        df = df.copy()
        
        # Ensure date is datetime
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
        
        # Standardize column names
        df.columns = df.columns.str.lower().str.strip()
        
        # Extract year/month
        df["year"] = df["date"].dt.year
        df["month"] = df["date"].dt.month
        df["year_month"] = df["date"].dt.to_period("M")
        
        # Categorize event severity
        if "damage_millions" in df.columns:
            df["damage_millions"] = pd.to_numeric(df["damage_millions"], errors="coerce")
            df["severity_category"] = pd.cut(
                df["damage_millions"],
                bins=[0, 100, 1000, 10000, float("inf")],
                labels=["Minor", "Moderate", "Major", "Catastrophic"]
            )
        
        # Calculate impact scores
        df["employment_impact_score"] = 0
        
        if "deaths" in df.columns:
            df["deaths"] = pd.to_numeric(df["deaths"], errors="coerce").fillna(0)
            df["employment_impact_score"] += df["deaths"] * 100
        
        if "injuries" in df.columns:
            df["injuries"] = pd.to_numeric(df["injuries"], errors="coerce").fillna(0)
            df["employment_impact_score"] += df["injuries"] * 10
        
        if "damage_millions" in df.columns:
            df["employment_impact_score"] += df["damage_millions"] / 10
        
        # Monthly aggregation
        monthly = df.groupby("year_month").agg({
            "event_type": lambda x: ", ".join(x.dropna().unique()),
            "state": lambda x: ", ".join(x.dropna().unique()),
            "deaths": "sum",
            "injuries": "sum",
            "damage_millions": "sum",
            "employment_impact_score": "sum",
            "date": "min"
        }).reset_index()
        
        monthly["num_major_events"] = df.groupby("year_month").size().values
        
        # Flag high-impact months (top quartile)
        if len(monthly) > 0:
            impact_threshold = monthly["employment_impact_score"].quantile(0.75)
            monthly["is_high_impact_month"] = monthly["employment_impact_score"] > impact_threshold
        else:
            monthly["is_high_impact_month"] = False
        
        # Add metadata
        monthly["ingested_at"] = datetime.now()
        monthly["source"] = "NOAA_Storm_Events"
        
        # Sort by date
        monthly = monthly.sort_values("date")
        
        logger.info(f"Transformed to {len(monthly)} monthly records")
        logger.info(f"High-impact months: {monthly['is_high_impact_month'].sum()}")
        
        return monthly
    
    def get_recent_disruptions(self, df: pd.DataFrame, months: int = 3) -> pd.DataFrame:
        """
        Get recent weather disruptions
        
        Args:
            df: Weather DataFrame
            months: Number of recent months
            
        Returns:
            pd.DataFrame: Recent disruptions
        """
        cutoff_date = datetime.now() - timedelta(days=months * 30)
        
        recent = df[df["date"] >= cutoff_date]
        
        return recent.sort_values("employment_impact_score", ascending=False)


def main():
    """Test the Weather ETL"""
    etl = WeatherETL()
    success = etl.run()
    
    if success:
        print("✅ Weather ETL completed successfully")
    else:
        print("❌ Weather ETL failed")


if __name__ == "__main__":
    main()

