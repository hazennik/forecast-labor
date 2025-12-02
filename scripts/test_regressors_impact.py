#!/usr/bin/env python3
"""
Test Regressors Impact
Phase 6.2.0: Test seasonal adjustment with fixed strike/weather data

This script runs seasonal adjustment with all regressors enabled and compares
Q-statistics before/after to measure improvement.
"""

import sys
from pathlib import Path
from datetime import date, datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np
from loguru import logger

# Import after path setup
from seasonal.pipeline import SeasonalAdjustmentPipeline
from etl.common.storage import StorageClient


# Series to test
# CRITICAL: Each series type requires different regressor configurations
# - CES (employment counts): Use holiday + strike regressors
# - LAUS (unemployment rates): Use NO external regressors (rates are smoothed)
MONITORED_SERIES = {
    "CES0000000001": {
        "name": "Total Nonfarm Payrolls",
        "source": "bls_ces",
        "series_type": "employment_count",
        "config": {
            "mode": "mult",
            "easter": True,
            "trading_day": True,
            "use_holiday_regressors": True,
            "use_strike_regressors": True,
            "use_weather_regressors": False,
        },
    },
    "CES0500000003": {
        "name": "Total Private Employment",
        "source": "bls_ces",
        "series_type": "employment_count",
        "config": {
            "mode": "mult",
            "easter": True,
            "trading_day": True,
            "use_holiday_regressors": True,
            "use_strike_regressors": True,
            "use_weather_regressors": False,
        },
    },
    "LASST060000000000003": {
        "name": "California Unemployment Rate",
        "source": "bls_laus",
        "series_type": "unemployment_rate",
        "config": {
            "mode": "add",  # Rates use additive
            "easter": False,
            "trading_day": False,
            "use_holiday_regressors": False,
            "use_strike_regressors": False,
            "use_weather_regressors": False,
        },
    },
}


def load_series_from_vintage(series_id: str, vintage_date: str = "2025-11-29"):
    """Load series from vintage data"""
    storage = StorageClient()
    
    # Map series to source
    if series_id.startswith("CES"):
        source = "bls_ces"
    elif series_id.startswith("LASS"):
        source = "bls_laus"
    else:
        raise ValueError(f"Unknown series source for {series_id}")
    
    # Load vintage data
    try:
        df = storage.read_parquet(f"vintages/{source}/{vintage_date}/data.parquet")
    except Exception as e:
        logger.error(f"Failed to load vintage data: {e}")
        return None
    
    # Filter to series
    if "series_id" in df.columns:
        series_df = df[df["series_id"] == series_id]
    else:
        logger.error(f"No series_id column in data")
        return None
    
    if len(series_df) == 0:
        logger.error(f"Series {series_id} not found in vintage data")
        return None
    
    # Create time series
    series_df = series_df.copy()
    series_df["date"] = pd.to_datetime(series_df["date"])
    series_df = series_df.sort_values("date")
    series = pd.Series(
        series_df["value"].values,
        index=pd.DatetimeIndex(series_df["date"]),
        name=series_id
    )
    
    return series


def run_seasonal_adjustment_test(series_id: str, series_info: dict, with_all_regressors: bool = True):
    """
    Run seasonal adjustment and extract Q-statistics
    
    Args:
        series_id: Series identifier
        series_name: Series name
        with_all_regressors: Whether to use all regressors (strike/weather)
    
    Returns:
        Dict with Q-statistics
    """
    series_name = series_info["name"]
    series_type = series_info.get("series_type", "unknown")
    
    logger.info(f"\n{'='*70}")
    logger.info(f"Testing: {series_name} ({series_id})")
    logger.info(f"Series type: {series_type}")
    logger.info(f"All regressors: {with_all_regressors}")
    logger.info(f"{'='*70}")
    
    # Load series
    series = load_series_from_vintage(series_id)
    
    if series is None:
        logger.error(f"Could not load series {series_id}")
        return None
    
    logger.info(f"Loaded series: {len(series)} observations from {series.index[0]} to {series.index[-1]}")
    
    # Configure regressors - use series-type-appropriate configuration
    config = series_info.get("config", {}).copy()
    config["title"] = series_name
    
    # If testing with all regressors, enable strike/weather (respecting series type)
    # For unemployment rates, this remains False (as designed)
    if with_all_regressors:
        # Only enable if base config allows it (employment counts)
        if series_info.get("series_type") == "employment_count":
            config["use_strike_regressors"] = True
            config["use_weather_regressors"] = True
    
    # Run seasonal adjustment
    try:
        pipeline = SeasonalAdjustmentPipeline()
        results = pipeline.run(
            series_name=series_id,
            series_data=series,
            start_date=series.index[0].date(),
            config=config
        )
        
        # Extract Q-statistics
        q_stats = results.get("q_statistics", {})
        q_stat = q_stats.get("q_statistic", None)
        p_value = q_stats.get("p_value", None)
        
        logger.info(f"\n📊 Results:")
        logger.info(f"  Q-statistic: {q_stat:.4f}" if q_stat else "  Q-statistic: N/A")
        logger.info(f"  P-value: {p_value:.6f}" if p_value else "  P-value: N/A")
        logger.info(f"  Random residuals: {'✅ Yes (p > 0.05)' if p_value and p_value > 0.05 else '❌ No (p ≤ 0.05)'}")
        
        # Extract M-statistics
        m_stats = results.get("m_statistics", {})
        q_m = m_stats.get("q_statistic", None)
        logger.info(f"  M Q-statistic: {q_m:.4f}" if q_m else "  M Q-statistic: N/A")
        
        return {
            "series_id": series_id,
            "series_name": series_name,
            "with_all_regressors": with_all_regressors,
            "q_statistic": q_stat,
            "p_value": p_value,
            "m_q_statistic": q_m,
            "random_residuals": p_value > 0.05 if p_value else False,
        }
        
    except Exception as e:
        logger.error(f"Seasonal adjustment failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    """Main function"""
    logger.info("=" * 70)
    logger.info("TEST REGRESSORS IMPACT")
    logger.info("Phase 6.2.0: Measure Q-statistics improvement with strike/weather data")
    logger.info("=" * 70)
    
    # Load golden baseline for comparison
    golden_path = Path("tests/fixtures/golden_baselines/golden_seasonal_diagnostics.json")
    if golden_path.exists():
        import json
        with open(golden_path) as f:
            golden = json.load(f)
            logger.info(f"\n📋 Golden baseline (recorded {golden.get('recorded_at')}):")
            for sid, data in golden.get("series", {}).items():
                q_old = data.get("q_statistics", {}).get("p_value")
                logger.info(f"  {sid}: p-value = {q_old:.6f}")
    
    # Test each series with ALL regressors
    logger.info("\n" + "=" * 70)
    logger.info("TESTING WITH ALL REGRESSORS (Holiday + Strike + Weather)")
    logger.info("=" * 70)
    
    results = []
    for series_id, series_info in MONITORED_SERIES.items():
        result = run_seasonal_adjustment_test(
            series_id,
            series_info,
            with_all_regressors=True
        )
        if result:
            results.append(result)
    
    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("SUMMARY")
    logger.info("=" * 70)
    
    if golden_path.exists():
        logger.info("\n📊 Before/After Comparison:")
        print(f"\n{'Series':<30} {'Old P-Value':<15} {'New P-Value':<15} {'Change':<15} {'Status':<10}")
        print("-" * 85)
        
        for result in results:
            sid = result["series_id"]
            new_p = result.get("p_value")
            
            golden_series = golden.get("series", {}).get(sid, {})
            old_p = golden_series.get("q_statistics", {}).get("p_value")
            
            if old_p and new_p:
                change = ((new_p - old_p) / old_p) * 100
                change_str = f"{change:+.1f}%"
                status = "✅" if new_p > 0.05 else "⚠️" if new_p > old_p else "❌"
            else:
                change_str = "N/A"
                status = "❓"
            
            print(f"{sid:<30} {old_p:.6f if old_p else 'N/A':<15} {new_p:.6f if new_p else 'N/A':<15} {change_str:<15} {status:<10}")
    
    logger.info(f"\n✅ Testing complete: {len(results)}/{len(MONITORED_SERIES)} series tested")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

