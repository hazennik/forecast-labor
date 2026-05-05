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

# Production safety: Defaults to 'false' to prevent synthetic data in production
# Set ALLOW_FALLBACK_DATA=true in development/testing to use synthetic data when API unavailable
# Always provide NOAA_API_TOKEN in production and keep this false
ALLOW_FALLBACK_DATA = os.getenv("ALLOW_FALLBACK_DATA", "false").lower() == "true"


def _allow_fallback_data() -> bool:
    """Return whether fallback weather data is allowed in the current environment."""
    return os.getenv("ALLOW_FALLBACK_DATA", "false").lower() == "true"


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
        if _allow_fallback_data():
            logger.warning("Using fallback weather data (ALLOW_FALLBACK_DATA=true)")
            logger.warning("Set ALLOW_FALLBACK_DATA=false in production to fail instead")
            df = self._create_fallback_data()
            return df
        else:
            logger.error("API fetch failed and ALLOW_FALLBACK_DATA=false")
            raise Exception("Weather data fetch failed and fallback data disabled in production")
    
    def _fetch_from_api(self, start_date: date, end_date: date) -> Optional[pd.DataFrame]:
        """
        Fetch from NOAA Storm Events CSV bulk files
        
        NOAA Storm Events Database: https://www.ncdc.noaa.gov/stormevents/
        CSV Files: https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/
        
        Note: NOAA Storm Events Database has NO JSON API. Only CSV bulk files available.
        Files updated monthly by NOAA. This is the official and most complete source.
        See: docs/planning/WEATHER_DATA_PRODUCTION_STRATEGY.md for rationale.
        
        Args:
            start_date: Start date
            end_date: End date
            
        Returns:
            pd.DataFrame: Weather data or None
        """
        logger.info(f"Fetching from NOAA Storm Events CSV files: {start_date} to {end_date}")
        
        try:
            import gzip
            import io
            
            # NOAA Storm Events CSV bulk files
            # Format: StormEvents_details-ftp_v1.0_d{YEAR}_c{YYYYMMDD}.csv.gz
            # URL: https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/
            base_url = "https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/"
            
            # Determine which years to fetch
            start_year = start_date.year
            end_year = end_date.year
            
            all_data = []
            
            for year in range(start_year, end_year + 1):
                # Download details file for this year
                # Creation dates from NOAA directory (verified 2025-11-28)
                # 2023: c20250731, 2024: c20251118, 2025: c20251118
                # Older years typically use c20250520
                year_specific_dates = {
                    2023: ["20250731", "20250520"],
                    2024: ["20251118", "20250520"],
                    2025: ["20251118", "20250520"]
                }
                possible_dates = year_specific_dates.get(year, ["20251118", "20250731", "20250520"])
                df_year = None
                
                for creation_date in possible_dates:
                    filename = f"StormEvents_details-ftp_v1.0_d{year}_c{creation_date}.csv.gz"
                    file_url = base_url + filename
                    
                    logger.info(f"Attempting {filename}...")
                    
                    try:
                        # Download gzipped CSV
                        response = self.downloader.session.get(file_url, timeout=120)
                        response.raise_for_status()
                        break  # Success, exit creation date loop
                    except Exception as e:
                        logger.debug(f"  {filename} not found, trying next date...")
                        continue
                else:
                    # None of the creation dates worked
                    logger.warning(f"Could not find Storm Events file for {year}")
                    continue
                
                try:
                    
                    # Decompress and read CSV
                    with gzip.open(io.BytesIO(response.content), 'rt') as f:
                        df_year = pd.read_csv(f, low_memory=False)
                    
                    # Construct date from BEGIN_YEARMONTH and BEGIN_DAY
                    if 'BEGIN_YEARMONTH' in df_year.columns and 'BEGIN_DAY' in df_year.columns:
                        df_year['date'] = pd.to_datetime(
                            df_year['BEGIN_YEARMONTH'].astype(str) + df_year['BEGIN_DAY'].astype(str).str.zfill(2),
                            format='%Y%m%d',
                            errors='coerce'
                        )
                    elif 'BEGIN_DATE_TIME' in df_year.columns:
                        df_year['date'] = pd.to_datetime(df_year['BEGIN_DATE_TIME'], errors='coerce')
                    
                    # Rename columns to match expected format
                    df_year = df_year.rename(columns={
                        'EVENT_TYPE': 'event_type',
                        'STATE': 'state',
                        'DEATHS_DIRECT': 'deaths_direct',
                        'DEATHS_INDIRECT': 'deaths_indirect',
                        'INJURIES_DIRECT': 'injuries_direct',
                        'INJURIES_INDIRECT': 'injuries_indirect',
                        'DAMAGE_PROPERTY': 'damage_property_str'
                    })
                    
                    # Calculate total deaths and injuries
                    df_year['deaths'] = (
                        pd.to_numeric(df_year.get('deaths_direct', 0), errors='coerce').fillna(0) +
                        pd.to_numeric(df_year.get('deaths_indirect', 0), errors='coerce').fillna(0)
                    )
                    df_year['injuries'] = (
                        pd.to_numeric(df_year.get('injuries_direct', 0), errors='coerce').fillna(0) +
                        pd.to_numeric(df_year.get('injuries_indirect', 0), errors='coerce').fillna(0)
                    )
                    
                    # Parse damage from string format (e.g., "10.00K", "1.50M")
                    if 'damage_property_str' in df_year.columns:
                        df_year['damage_millions'] = df_year['damage_property_str'].apply(self._parse_damage)
                    else:
                        df_year['damage_millions'] = 0
                    
                    # Filter to date range
                    if 'date' in df_year.columns:
                        df_year = df_year[(df_year['date'] >= pd.Timestamp(start_date)) & 
                                          (df_year['date'] <= pd.Timestamp(end_date))]
                    
                    logger.info(f"Downloaded {len(df_year)} events for {year}")
                    all_data.append(df_year)
                    
                except Exception as e:
                    logger.warning(f"Could not download {filename}: {e}")
                    # Continue to next year
                    continue
            
            if not all_data:
                logger.warning("No Storm Events data downloaded")
                return None
            
            # Combine all years
            df = pd.concat(all_data, ignore_index=True)
            logger.info(f"Downloaded {len(df)} total storm events from NOAA CSV files")
            
            return df
            
        except Exception as e:
            logger.error(f"Error fetching from NOAA CSV files: {e}")
            logger.exception(e)
            return None
    
    def _parse_damage(self, damage_str) -> float:
        """
        Parse damage string to millions (e.g., '10.00K' -> 0.01, '1.50M' -> 1.5)
        
        Args:
            damage_str: Damage string from NOAA CSV
            
        Returns:
            float: Damage in millions
        """
        if pd.isna(damage_str) or damage_str == '':
            return 0.0
        
        try:
            damage_str = str(damage_str).upper().strip()
            
            if 'K' in damage_str:
                # Thousands
                value = float(damage_str.replace('K', ''))
                return value / 1000  # Convert to millions
            elif 'M' in damage_str:
                # Millions
                value = float(damage_str.replace('M', ''))
                return value
            elif 'B' in damage_str:
                # Billions
                value = float(damage_str.replace('B', ''))
                return value * 1000  # Convert to millions
            else:
                # Assume raw dollar value
                value = float(damage_str)
                return value / 1_000_000  # Convert to millions
        except:
            return 0.0
    
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

