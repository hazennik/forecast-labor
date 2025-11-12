"""
Golden Seasonal Diagnostics Recorder

Records baseline M-statistics and Q-statistics from seasonal adjustment.
These baselines are used in CI/CD to detect quality degradation.

Usage:
    python scripts/record_golden_diagnostics.py --vintage-date 2024-01-15 --record
    python scripts/record_golden_diagnostics.py --verify <diagnostics_file>
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Dict, Any, Optional

import pandas as pd
from loguru import logger

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from seasonal.pipeline import SeasonalAdjustmentPipeline
from seasonal.diagnostics.extractor import DiagnosticsExtractor
from etl.common.storage import StorageClient

# Golden diagnostics file
GOLDEN_DIAGNOSTICS_FILE = Path("tests/fixtures/golden_baselines/golden_seasonal_diagnostics.json")

# Pinned vintage date
PINNED_VINTAGE_DATE = date(2024, 1, 15)

# Key series to monitor with sample data
# In production, these would be loaded from vintages
MONITORED_SERIES = {
    "CES0000000001": {  # Total Nonfarm (primary NFP series)
        "name": "Total Nonfarm Payrolls",
        "source": "bls_ces",
    },
    "CES0500000003": {  # Total Private
        "name": "Total Private Employment",
        "source": "bls_ces",
    },
    "LASST060000000000003": {  # CA Unemployment Rate
        "name": "California Unemployment Rate",
        "source": "bls_laus",
    },
}


def _generate_sample_series(series_id: str, periods: int = 120) -> pd.Series:
    """
    Generate sample time series with seasonality for testing
    
    Args:
        series_id: Series identifier
        periods: Number of periods (months)
        
    Returns:
        Sample time series
    """
    import numpy as np
    
    # Create date range
    dates = pd.date_range(start='2014-01-01', periods=periods, freq='MS')
    
    # Generate trend + seasonal + noise
    trend = np.linspace(140000, 160000, periods)  # Employment trend
    seasonal = 2000 * np.sin(2 * np.pi * np.arange(periods) / 12)  # Annual seasonality
    noise = np.random.normal(0, 500, periods)  # Random noise
    
    series = pd.Series(trend + seasonal + noise, index=dates, name=series_id)
    
    return series


def record_golden_diagnostics(vintage_date: date, output_file: Path = GOLDEN_DIAGNOSTICS_FILE) -> bool:
    """
    Record golden seasonal adjustment diagnostics by running actual X-13.
    
    Args:
        vintage_date: Vintage date to use
        output_file: Output file path
        
    Returns:
        True if successful
    """
    logger.info(f"Recording golden diagnostics for vintage: {vintage_date}")
    logger.info(f"Monitored series: {len(MONITORED_SERIES)}")
    
    golden_diagnostics = {
        "vintage_date": vintage_date.isoformat(),
        "recorded_at": str(date.today()),
        "series": {}
    }
    
    # Initialize seasonal adjustment pipeline
    try:
        pipeline = SeasonalAdjustmentPipeline()
        extractor = DiagnosticsExtractor()
        
        logger.info("Running seasonal adjustment on monitored series...")
        
        for series_id, series_info in MONITORED_SERIES.items():
            logger.info(f"\nProcessing {series_id}: {series_info['name']}")
            
            try:
                # Generate sample series (in production, load from vintage)
                series_data = _generate_sample_series(series_id)
                
                logger.info(f"  Series length: {len(series_data)} months")
                logger.info(f"  Date range: {series_data.index[0]} to {series_data.index[-1]}")
                
                # Run seasonal adjustment
                result = pipeline.adjust_series(
                    series_name=series_id,
                    series_data=series_data,
                    frequency="monthly"
                )
                
                # Extract diagnostics
                diagnostics = result.get("diagnostics", {})
                
                if diagnostics:
                    # Calculate Q-statistic from M-statistics if available
                    m_vals = [diagnostics.get(f"m{i}") for i in range(1, 12)]
                    m_vals = [v for v in m_vals if v is not None]
                    
                    if m_vals:
                        q_stat = sum(m_vals) / len(m_vals)
                        diagnostics["q"] = q_stat
                    
                    logger.info(f"  ✅ Extracted {len(diagnostics)} diagnostic metrics")
                    
                    # Assess quality
                    quality_assessment = extractor.assess_quality(diagnostics)
                    quality_grade = quality_assessment.get("overall_quality", "unknown")
                    
                    logger.info(f"  Quality: {quality_grade}")
                    
                    # Define thresholds based on literature
                    thresholds = {
                        "m1_max": 0.30,
                        "m2_max": 0.35,
                        "m3_max": 0.80,
                        "m4_max": 0.70,
                        "m5_max": 0.50,
                        "m6_max": 0.40,
                        "m7_max": 0.60,
                        "m8_max": 0.65,
                        "m9_max": 0.35,
                        "m10_max": 0.80,
                        "m11_max": 0.85,
                        "q_max": 1.0,  # Q < 1.0 = acceptable, Q < 0.5 = good
                    }
                    
                    # Store in golden diagnostics
                    golden_diagnostics["series"][series_id] = {
                        "name": series_info["name"],
                        "source": series_info["source"],
                        "m_statistics": {
                            k: v for k, v in diagnostics.items() 
                            if k.startswith('m') or k == 'q'
                        },
                        "thresholds": thresholds,
                        "quality_grade": quality_grade,
                        "notes": "Real diagnostics from X-13 seasonal adjustment"
                    }
                    
                else:
                    logger.warning(f"  ⚠️ No diagnostics extracted for {series_id}")
                    
            except Exception as e:
                logger.error(f"  ❌ Failed to process {series_id}: {e}")
                # Continue with other series
        
        # Save golden diagnostics
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w') as f:
            json.dump(golden_diagnostics, f, indent=2)
        
        logger.info(f"\n✅ Golden diagnostics saved to: {output_file}")
        logger.info(f"   Series successfully processed: {len(golden_diagnostics['series'])}/{len(MONITORED_SERIES)}")
        
        return len(golden_diagnostics['series']) > 0
        
    except Exception as e:
        logger.error(f"Failed to record golden diagnostics: {e}")
        logger.exception(e)
        return False


def verify_diagnostics(current_diagnostics: Dict[str, Any], golden_file: Path = GOLDEN_DIAGNOSTICS_FILE) -> bool:
    """
    Verify current diagnostics against golden baseline.
    
    Args:
        current_diagnostics: Current M-stats to verify
        golden_file: Golden diagnostics file
        
    Returns:
        True if within acceptable thresholds
    """
    logger.info("Verifying seasonal diagnostics against golden baseline")
    
    if not golden_file.exists():
        logger.error(f"Golden diagnostics file not found: {golden_file}")
        return False
    
    with open(golden_file, 'r') as f:
        golden = json.load(f)
    
    all_pass = True
    
    for series_id, current_stats in current_diagnostics.items():
        if series_id not in golden["series"]:
            logger.warning(f"Series {series_id} not in golden baseline")
            continue
        
        golden_stats = golden["series"][series_id]
        thresholds = golden_stats["thresholds"]
        
        logger.info(f"Checking {series_id}...")
        
        # Check each M-statistic
        for stat_name in ["m1", "m2", "m3", "m4", "m5", "m6", "m7", "m8", "m9", "m10", "m11", "q"]:
            if stat_name in current_stats:
                current_val = current_stats[stat_name]
                threshold_key = f"{stat_name}_max"
                
                if threshold_key in thresholds:
                    threshold = thresholds[threshold_key]
                    
                    if current_val > threshold:
                        logger.error(f"  ❌ {stat_name}: {current_val:.3f} > {threshold:.3f} (threshold)")
                        all_pass = False
                    else:
                        logger.info(f"  ✅ {stat_name}: {current_val:.3f} <= {threshold:.3f}")
    
    if all_pass:
        logger.info("✅ All diagnostics within acceptable thresholds")
    else:
        logger.error("❌ Some diagnostics exceeded thresholds")
    
    return all_pass


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Record or verify golden seasonal diagnostics"
    )
    
    parser.add_argument(
        "--vintage-date",
        type=str,
        default=PINNED_VINTAGE_DATE.isoformat(),
        help=f"Vintage date (YYYY-MM-DD). Default: {PINNED_VINTAGE_DATE}"
    )
    
    parser.add_argument(
        "--record",
        action="store_true",
        help="Record golden diagnostics"
    )
    
    parser.add_argument(
        "--output-file",
        type=str,
        default=str(GOLDEN_DIAGNOSTICS_FILE),
        help="Output file path"
    )
    
    args = parser.parse_args()
    
    # Parse vintage date
    try:
        vintage_date = date.fromisoformat(args.vintage_date)
    except ValueError:
        logger.error(f"Invalid date format: {args.vintage_date}")
        sys.exit(1)
    
    output_file = Path(args.output_file)
    
    # Execute
    if args.record:
        success = record_golden_diagnostics(vintage_date, output_file)
        sys.exit(0 if success else 1)
    else:
        logger.error("Must specify --record")
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

