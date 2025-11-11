"""
BLS LAUS ETL Implementation
Local Area Unemployment Statistics - State-level employment and unemployment
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


# State FIPS codes for LAUS series construction
STATE_FIPS = {
    "01": "Alabama", "02": "Alaska", "04": "Arizona", "05": "Arkansas",
    "06": "California", "08": "Colorado", "09": "Connecticut", "10": "Delaware",
    "11": "District of Columbia", "12": "Florida", "13": "Georgia", "15": "Hawaii",
    "16": "Idaho", "17": "Illinois", "18": "Indiana", "19": "Iowa",
    "20": "Kansas", "21": "Kentucky", "22": "Louisiana", "23": "Maine",
    "24": "Maryland", "25": "Massachusetts", "26": "Michigan", "27": "Minnesota",
    "28": "Mississippi", "29": "Missouri", "30": "Montana", "31": "Nebraska",
    "32": "Nevada", "33": "New Hampshire", "34": "New Jersey", "35": "New Mexico",
    "36": "New York", "37": "North Carolina", "38": "North Dakota", "39": "Ohio",
    "40": "Oklahoma", "41": "Oregon", "42": "Pennsylvania", "44": "Rhode Island",
    "45": "South Carolina", "46": "South Dakota", "47": "Tennessee", "48": "Texas",
    "49": "Utah", "50": "Vermont", "51": "Virginia", "53": "Washington",
    "54": "West Virginia", "55": "Wisconsin", "56": "Wyoming"
}


class LAUSETL(BaseETL):
    """
    ETL pipeline for BLS Local Area Unemployment Statistics (LAUS)
    
    Data includes:
    - Employment level by state
    - Unemployment level by state
    - Unemployment rate by state
    - Labor force by state
    - Labor force participation rate
    """
    
    def __init__(
        self,
        raw_data_path: Path = Path("data/raw/bls_laus"),
        vintage_path: Path = Path("data/vintages"),
        api_key: Optional[str] = None,
        lookback_years: int = 10
    ):
        """
        Initialize LAUS ETL
        
        Args:
            raw_data_path: Path for raw data storage
            vintage_path: Path for vintage snapshots
            api_key: BLS API key (optional, increases rate limits)
            lookback_years: Years of history to fetch
        """
        config = ETLConfig(
            source_name=DataSource.BLS_LAUS.value,
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
    
    def _build_laus_series_ids(self) -> Dict[str, str]:
        """
        Build LAUS series IDs for all states
        
        LAUS series format: LASST{FIPS}0000000000{measure}
        Measures:
        - 03: Unemployment rate
        - 04: Unemployment level
        - 05: Employment level
        - 06: Labor force
        
        Returns:
            dict: Series ID to description mapping
        """
        series = {}
        
        # National series
        series["LNS14000000"] = "National Unemployment Rate"
        series["LNS13000000"] = "National Unemployment Level (thousands)"
        series["LNS12000000"] = "National Employment Level (thousands)"
        series["LNS11000000"] = "National Labor Force (thousands)"
        
        # State series (just unemployment rate and employment for now to limit API calls)
        for fips, state_name in STATE_FIPS.items():
            # Unemployment rate
            series[f"LASST{fips}0000000000003"] = f"{state_name} Unemployment Rate"
            # Employment level
            series[f"LASST{fips}0000000000005"] = f"{state_name} Employment (thousands)"
        
        return series
    
    def extract(self) -> pd.DataFrame:
        """
        Extract LAUS data from BLS API
        
        Returns:
            pd.DataFrame: Raw LAUS data
        """
        # Calculate year range
        end_year = datetime.now().year
        start_year = end_year - self.lookback_years
        
        logger.info(f"Fetching LAUS data for {start_year}-{end_year}")
        
        # Build series list
        series_dict = self._build_laus_series_ids()
        series_list = list(series_dict.keys())
        
        logger.info(f"Fetching {len(series_list)} LAUS series")
        
        all_data = []
        
        # Process in batches (BLS API limits: 50 series per request)
        batch_size = 50 if self.api_key else 25
        
        for i in range(0, len(series_list), batch_size):
            batch = series_list[i:i + batch_size]
            
            logger.info(f"Fetching batch {i//batch_size + 1} ({len(batch)} series)...")
            
            try:
                batch_data = self._fetch_series_batch(batch, series_dict, start_year, end_year)
                all_data.extend(batch_data)
                
                # Rate limiting
                delay = 3 if not self.api_key else 0.5
                time.sleep(delay)
                
            except Exception as e:
                logger.error(f"Error fetching batch: {e}")
                raise
        
        if not all_data:
            raise ValueError("No LAUS data retrieved")
        
        # Convert to DataFrame
        df = pd.DataFrame(all_data)
        
        logger.info(f"Downloaded {len(df)} observations across {df['series_id'].nunique()} series")
        
        return df
    
    def _fetch_series_batch(
        self,
        series_ids: List[str],
        series_dict: Dict[str, str],
        start_year: int,
        end_year: int
    ) -> List[Dict]:
        """
        Fetch a batch of series from BLS API
        
        Args:
            series_ids: List of series IDs to fetch
            series_dict: Mapping of series IDs to descriptions
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
            series_name = series_dict.get(series_id, "Unknown")
            
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
        Validate LAUS data
        
        Args:
            df: DataFrame to validate
            
        Returns:
            bool: True if valid
        """
        logger.info("Validating LAUS data...")
        
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
        
        # Check for national series
        national_series = ["LNS14000000", "LNS12000000"]
        found_national = any(s in df["series_id"].values for s in national_series)
        
        if not found_national:
            logger.error("National LAUS series not found")
            return False
        
        # Check for recent data
        most_recent_year = df["year"].max()
        current_year = datetime.now().year
        
        if most_recent_year < current_year - 1:
            logger.warning(f"Data may be stale. Most recent: {most_recent_year}")
        
        # Check for reasonable number of series
        n_series = df["series_id"].nunique()
        if n_series < 50:
            logger.warning(f"Only {n_series} series found (expected ~100)")
        
        logger.info("✓ LAUS validation passed")
        return True
    
    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Transform LAUS data
        
        Args:
            df: Raw DataFrame
            
        Returns:
            pd.DataFrame: Cleaned DataFrame
        """
        logger.info("Transforming LAUS data...")
        
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
        
        # Extract state FIPS from series ID
        def extract_state_fips(series_id):
            if series_id.startswith("LASST"):
                return series_id[5:7]
            return "00"  # National
        
        df["state_fips"] = df["series_id"].apply(extract_state_fips)
        
        # Extract measure type
        def extract_measure(series_id):
            if "LNS14" in series_id or series_id.endswith("003"):
                return "unemployment_rate"
            elif "LNS13" in series_id or series_id.endswith("004"):
                return "unemployment_level"
            elif "LNS12" in series_id or series_id.endswith("005"):
                return "employment_level"
            elif "LNS11" in series_id or series_id.endswith("006"):
                return "labor_force"
            return "other"
        
        df["measure"] = df["series_id"].apply(extract_measure)
        
        # Add state name
        df["state_name"] = df["state_fips"].map(STATE_FIPS)
        df["state_name"] = df["state_name"].fillna("National")
        
        # Calculate month-over-month change
        df = df.sort_values(["series_id", "date"])
        df["mom_change"] = df.groupby("series_id")["value"].diff()
        
        # Calculate year-over-year change
        df["yoy_change"] = df.groupby("series_id")["value"].diff(12)
        
        # Flag preliminary vs revised
        df["is_preliminary"] = df["footnotes"].apply(
            lambda x: any("preliminary" in str(f).lower() for f in x) if isinstance(x, list) else False
        )
        
        # Add metadata
        df["ingested_at"] = datetime.now()
        df["source"] = "BLS_LAUS_API"
        
        # Sort final output
        df = df.sort_values(["date", "state_fips", "measure"])
        
        logger.info(f"Transformed data: {len(df)} observations")
        logger.info(f"States: {df['state_fips'].nunique()}, Measures: {df['measure'].nunique()}")
        
        return df
    
    def get_state_employment_summary(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Get latest employment levels by state
        
        Args:
            df: LAUS DataFrame
            
        Returns:
            pd.DataFrame: State employment summary
        """
        # Filter to employment level measure
        emp_df = df[df["measure"] == "employment_level"].copy()
        
        if emp_df.empty:
            logger.warning("No employment level data found")
            return pd.DataFrame()
        
        # Get latest for each state
        latest = emp_df.sort_values("date").groupby("state_fips").tail(1)
        
        summary = latest[["state_name", "state_fips", "date", "value", "mom_change", "yoy_change"]].copy()
        summary.rename(columns={"value": "employment_level_thousands"}, inplace=True)
        
        summary = summary.sort_values("employment_level_thousands", ascending=False)
        
        return summary


def main():
    """Test the LAUS ETL"""
    etl = LAUSETL()
    success = etl.run()
    
    if success:
        print("✅ LAUS ETL completed successfully")
    else:
        print("❌ LAUS ETL failed")


if __name__ == "__main__":
    main()

