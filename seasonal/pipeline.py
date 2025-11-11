"""
Seasonal Adjustment Pipeline
Orchestrates X-13ARIMA-SEATS seasonal adjustment workflow
"""

from datetime import date, datetime
from typing import Dict, List, Optional, Any
from pathlib import Path
import tempfile

import pandas as pd
from loguru import logger

from seasonal.spec_builder import SpecBuilder, X13Spec
from seasonal.service_client.x13_service import X13Service
from seasonal.regressors.holiday_regressors import HolidayRegressors
from seasonal.regressors.strike_regressors import StrikeRegressors
from seasonal.regressors.weather_regressors import WeatherRegressors
from etl.common.storage import StorageClient


class SeasonalAdjustmentPipeline:
    """
    Complete seasonal adjustment pipeline
    
    Workflow:
    1. Load raw series data
    2. Build regressors (holidays, strikes, weather)
    3. Generate X-13 spec files
    4. Run X-13 seasonal adjustment
    5. Extract diagnostics and seasonally adjusted series
    6. Store results and metadata
    """
    
    def __init__(
        self,
        storage_client: Optional[StorageClient] = None,
        x13_service: Optional[X13Service] = None,
        work_dir: Optional[Path] = None
    ):
        """
        Initialize pipeline
        
        Args:
            storage_client: Storage client for data access
            x13_service: X-13 service client
            work_dir: Working directory for temporary files
        """
        self.storage = storage_client or StorageClient()
        self.x13 = x13_service or X13Service()
        self.work_dir = Path(work_dir) if work_dir else Path(tempfile.gettempdir()) / "x13_work"
        self.work_dir.mkdir(parents=True, exist_ok=True)
        
        # Regressor builders
        self.holiday_builder = HolidayRegressors()
        self.strike_builder = StrikeRegressors(self.storage)
        self.weather_builder = WeatherRegressors(self.storage)
        
        # Spec builder
        self.spec_builder = SpecBuilder()
    
    def run(
        self,
        series_name: str,
        series_data: pd.Series,
        start_date: date,
        config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Run complete seasonal adjustment pipeline
        
        Args:
            series_name: Series identifier
            series_data: Time series data (DatetimeIndex)
            start_date: Series start date
            config: Optional configuration overrides
            
        Returns:
            Dict with results (adjusted series, diagnostics, metadata)
        """
        logger.info(f"Running seasonal adjustment for: {series_name}")
        
        config = config or {}
        
        # Step 1: Validate input data
        self._validate_series(series_data)
        
        # Step 2: Build regressors
        regressors = self._build_regressors(
            series_data.index[0].date(),
            series_data.index[-1].date(),
            config
        )
        
        # Step 3: Generate X-13 spec
        spec_content = self._generate_spec(
            series_name,
            series_data,
            regressors,
            config
        )
        
        # Step 4: Run X-13
        results = self._run_x13(
            series_name,
            series_data,
            spec_content,
            regressors
        )
        
        # Step 5: Store results
        self._store_results(series_name, results)
        
        logger.info(f"Seasonal adjustment complete for: {series_name}")
        
        return results
    
    def _validate_series(self, series_data: pd.Series):
        """Validate input series"""
        if not isinstance(series_data.index, pd.DatetimeIndex):
            raise ValueError("Series must have DatetimeIndex")
        
        if len(series_data) < 36:
            raise ValueError("Series must have at least 36 observations (3 years)")
        
        # Check for excessive missing values
        missing_pct = series_data.isna().sum() / len(series_data) * 100
        if missing_pct > 10:
            logger.warning(f"Series has {missing_pct:.1f}% missing values")
    
    def _build_regressors(
        self,
        start_date: date,
        end_date: date,
        config: Dict[str, Any]
    ) -> pd.DataFrame:
        """
        Build all regressors
        
        Args:
            start_date: Start date
            end_date: End date
            config: Configuration
            
        Returns:
            DataFrame with all regressors
        """
        logger.info("Building regressors...")
        
        all_regressors = pd.DataFrame()
        
        # Holiday regressors
        if config.get("use_holiday_regressors", True):
            try:
                holiday_regressors = self.holiday_builder.build(
                    start_date, end_date
                )
                all_regressors = pd.concat([all_regressors, holiday_regressors], axis=1)
                logger.info(f"Added {len(holiday_regressors.columns)} holiday regressors")
            except Exception as e:
                logger.error(f"Failed to build holiday regressors: {e}")
        
        # Strike regressors
        if config.get("use_strike_regressors", True):
            try:
                strike_regressors = self.strike_builder.build(
                    start_date, end_date,
                    min_workers=config.get("strike_min_workers", 10000)
                )
                all_regressors = pd.concat([all_regressors, strike_regressors], axis=1)
                logger.info(f"Added {len(strike_regressors.columns)} strike regressors")
            except Exception as e:
                logger.error(f"Failed to build strike regressors: {e}")
        
        # Weather regressors
        if config.get("use_weather_regressors", True):
            try:
                weather_regressors = self.weather_builder.build(
                    start_date, end_date
                )
                all_regressors = pd.concat([all_regressors, weather_regressors], axis=1)
                logger.info(f"Added {len(weather_regressors.columns)} weather regressors")
            except Exception as e:
                logger.error(f"Failed to build weather regressors: {e}")
        
        logger.info(f"Built {len(all_regressors.columns)} total regressors")
        
        return all_regressors
    
    def _generate_spec(
        self,
        series_name: str,
        series_data: pd.Series,
        regressors: pd.DataFrame,
        config: Dict[str, Any]
    ) -> str:
        """
        Generate X-13 spec file
        
        Args:
            series_name: Series name
            series_data: Series data
            regressors: Regressors DataFrame
            config: Configuration
            
        Returns:
            Spec file content
        """
        logger.info("Generating X-13 spec...")
        
        # Extract series metadata
        start_date = series_data.index[0]
        
        # Build spec config
        spec_config = X13Spec(
            series_name=series_name,
            title=config.get("title", series_name),
            start_year=start_date.year,
            start_month=start_date.month,
            mode=config.get("mode", "mult"),
            auto_model=config.get("auto_model", True),
            arima_model=config.get("arima_model"),
            easter=config.get("easter", True),
            trading_day=config.get("trading_day", True),
            user_regressors=list(regressors.columns) if len(regressors) > 0 else []
        )
        
        # Generate spec
        spec_content = self.spec_builder.build_spec(spec_config)
        
        return spec_content
    
    def _run_x13(
        self,
        series_name: str,
        series_data: pd.Series,
        spec_content: str,
        regressors: pd.DataFrame
    ) -> Dict[str, Any]:
        """
        Run X-13 adjustment
        
        Args:
            series_name: Series name
            series_data: Series data
            spec_content: Spec file content
            regressors: Regressors
            
        Returns:
            Results dictionary
        """
        logger.info("Running X-13 adjustment...")
        
        # Prepare input data
        input_data = {
            "series": series_data.to_dict(),
            "spec": spec_content
        }
        
        # Add regressors if present
        if len(regressors) > 0:
            input_data["regressors"] = {
                col: regressors[col].to_dict()
                for col in regressors.columns
            }
        
        # Run X-13
        try:
            results = self.x13.run_adjustment(input_data)
            
            # Extract key outputs
            return {
                "seasonally_adjusted": results.get("d11"),
                "trend": results.get("d12"),
                "irregular": results.get("d13"),
                "seasonal_factors": results.get("d16"),
                "diagnostics": results.get("diagnostics", {}),
                "metadata": {
                    "series_name": series_name,
                    "timestamp": datetime.now().isoformat(),
                    "spec": spec_content
                }
            }
            
        except Exception as e:
            logger.error(f"X-13 adjustment failed: {e}")
            raise
    
    def _store_results(self, series_name: str, results: Dict[str, Any]):
        """
        Store adjustment results
        
        Args:
            series_name: Series name
            results: Results dictionary
        """
        logger.info("Storing results...")
        
        # Store seasonally adjusted series
        if results.get("seasonally_adjusted"):
            sa_df = pd.DataFrame(results["seasonally_adjusted"])
            output_path = f"seasonal/adjusted/{series_name}_sa.parquet"
            self.storage.write_parquet(sa_df, output_path)
        
        # Store diagnostics
        if results.get("diagnostics"):
            diag_df = pd.DataFrame([results["diagnostics"]])
            output_path = f"seasonal/diagnostics/{series_name}_diagnostics.parquet"
            self.storage.write_parquet(diag_df, output_path)
        
        logger.info(f"Stored results for: {series_name}")
    
    def run_batch(
        self,
        series_dict: Dict[str, pd.Series],
        configs: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        Run seasonal adjustment for multiple series
        
        Args:
            series_dict: Dict of series_name -> series_data
            configs: Optional dict of series_name -> config
            
        Returns:
            Dict of series_name -> results
        """
        logger.info(f"Running batch adjustment for {len(series_dict)} series")
        
        configs = configs or {}
        results = {}
        
        for series_name, series_data in series_dict.items():
            try:
                config = configs.get(series_name, {})
                result = self.run(
                    series_name,
                    series_data,
                    series_data.index[0].date(),
                    config
                )
                results[series_name] = result
                
            except Exception as e:
                logger.error(f"Failed to adjust {series_name}: {e}")
                results[series_name] = {"error": str(e)}
        
        logger.info(f"Batch adjustment complete: {len(results)} series")
        
        return results


# Example usage
if __name__ == "__main__":
    # Create sample series
    dates = pd.date_range("2014-01-01", "2023-12-31", freq="MS")
    series = pd.Series(range(len(dates)), index=dates)
    
    # Run pipeline
    pipeline = SeasonalAdjustmentPipeline()
    
    results = pipeline.run(
        series_name="test_series",
        series_data=series,
        start_date=dates[0].date()
    )
    
    print("Adjustment complete!")
    print(f"Results keys: {results.keys()}")

