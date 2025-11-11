#!/usr/bin/env python3
"""
Run Seasonal Adjustment
Executes X-13ARIMA-SEATS seasonal adjustment on key employment series
"""

import sys
from pathlib import Path
from datetime import date

import pandas as pd
from loguru import logger

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from seasonal.pipeline import SeasonalAdjustmentPipeline
from etl.common.storage import StorageClient


# Series to seasonally adjust
SERIES_CONFIG = {
    "ces_nfp": {
        "title": "Total Nonfarm Payrolls",
        "path": "vintages/bls_ces/latest/ces.parquet",
        "series_id": "CES0000000001",
        "mode": "mult",
        "easter": True,
        "trading_day": True,
        "use_holiday_regressors": True,
        "use_strike_regressors": True,
        "use_weather_regressors": False,  # National aggregate less affected
    },
    "ces_manufacturing": {
        "title": "Manufacturing Payrolls",
        "path": "vintages/bls_ces/latest/ces.parquet",
        "series_id": "CES3000000001",
        "mode": "mult",
        "easter": True,
        "trading_day": True,
        "use_strike_regressors": True,  # Manufacturing heavily affected by strikes
    },
    "laus_unemployment": {
        "title": "National Unemployment Rate",
        "path": "vintages/bls_laus/latest/laus.parquet",
        "series_id": "LASST000000000003",
        "mode": "add",  # Rates typically use additive
        "easter": False,
        "trading_day": False,
    },
    "claims_initial": {
        "title": "Initial UI Claims (4-week MA)",
        "path": "vintages/claims/latest/claims.parquet",
        "column": "initial_claims_4wk",
        "mode": "mult",
        "easter": True,
        "trading_day": True,
        "use_holiday_regressors": True,
        "use_weather_regressors": True,
    },
}


def load_series(
    storage: StorageClient,
    config: dict
) -> pd.Series:
    """
    Load a time series from storage
    
    Args:
        storage: Storage client
        config: Series configuration
        
    Returns:
        Time series
    """
    path = config["path"]
    
    logger.info(f"Loading series from: {path}")
    
    df = storage.read_parquet(path)
    
    if df is None:
        raise ValueError(f"Failed to load data from {path}")
    
    # Ensure date index
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
    
    # Extract specific series
    if "series_id" in config:
        series_id = config["series_id"]
        if "series_id" in df.columns:
            df = df[df["series_id"] == series_id]
        
        if "value" in df.columns:
            series = df["value"]
        else:
            raise ValueError(f"No 'value' column for series_id: {series_id}")
    
    elif "column" in config:
        column = config["column"]
        if column not in df.columns:
            raise ValueError(f"Column not found: {column}")
        series = df[column]
    
    else:
        # Use first numeric column
        numeric_cols = df.select_dtypes(include=["number"]).columns
        if len(numeric_cols) == 0:
            raise ValueError("No numeric columns found")
        series = df[numeric_cols[0]]
    
    # Remove missing values
    series = series.dropna()
    
    logger.info(f"Loaded series: {len(series)} observations")
    
    return series


def run_seasonal_adjustment():
    """Run seasonal adjustment for all configured series"""
    logger.info("Starting seasonal adjustment pipeline")
    
    # Initialize
    storage = StorageClient()
    pipeline = SeasonalAdjustmentPipeline(storage_client=storage)
    
    results = {}
    
    for series_name, config in SERIES_CONFIG.items():
        logger.info(f"\n{'='*60}")
        logger.info(f"Processing: {series_name}")
        logger.info(f"{'='*60}")
        
        try:
            # Load series
            series = load_series(storage, config)
            
            if len(series) < 36:
                logger.warning(f"Insufficient data for {series_name}: {len(series)} obs")
                continue
            
            # Run adjustment
            result = pipeline.run(
                series_name=series_name,
                series_data=series,
                start_date=series.index[0].date(),
                config=config
            )
            
            results[series_name] = result
            
            # Log diagnostics
            if "diagnostics" in result:
                diag = result["diagnostics"]
                logger.info(f"Diagnostics for {series_name}:")
                for key, value in diag.items():
                    logger.info(f"  {key}: {value}")
            
            logger.success(f"✓ Completed: {series_name}")
            
        except Exception as e:
            logger.error(f"✗ Failed: {series_name}")
            logger.error(f"  Error: {e}")
            results[series_name] = {"error": str(e)}
    
    # Summary
    logger.info(f"\n{'='*60}")
    logger.info("Seasonal Adjustment Summary")
    logger.info(f"{'='*60}")
    
    success_count = sum(1 for r in results.values() if "error" not in r)
    fail_count = len(results) - success_count
    
    logger.info(f"Total series: {len(SERIES_CONFIG)}")
    logger.info(f"Successful: {success_count}")
    logger.info(f"Failed: {fail_count}")
    
    if fail_count > 0:
        logger.warning("\nFailed series:")
        for series_name, result in results.items():
            if "error" in result:
                logger.warning(f"  - {series_name}: {result['error']}")
    
    return results


if __name__ == "__main__":
    logger.remove()  # Remove default handler
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO"
    )
    
    try:
        results = run_seasonal_adjustment()
        
        if any("error" in r for r in results.values()):
            sys.exit(1)
        
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        sys.exit(1)

