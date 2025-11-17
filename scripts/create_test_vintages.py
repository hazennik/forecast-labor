#!/usr/bin/env python3
"""
Create minimal test vintage data for golden baseline verification.
This creates stub vintages with realistic structure for testing purposes.

CRITICAL: Uses fixed random seed for deterministic vintages.
This ensures CI determinism verification can function correctly.
"""

import sys
from pathlib import Path
from datetime import datetime, date

import pandas as pd
import numpy as np

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from loguru import logger

# Pinned vintage date for testing
VINTAGE_DATE = date(2024, 1, 15)

# Fixed random seed for deterministic test data
# CRITICAL: This seed ensures vintages are reproducible across CI runs
# DO NOT CHANGE unless you regenerate baseline hashes
RANDOM_SEED = 42

def create_test_vintage(source_name: str, num_rows: int = 100) -> Path:
    """
    Create a test vintage file with realistic structure.
    
    CRITICAL: Sets random seed for deterministic output.
    
    Args:
        source_name: Source name (e.g., 'bls_ces', 'ui_claims')
        num_rows: Number of rows to generate
        
    Returns:
        Path to created vintage file
    """
    # Set random seed for deterministic output
    # CRITICAL: This ensures same vintages every time for determinism verification
    np.random.seed(RANDOM_SEED)
    
    # Create vintage directory structure: data/vintages/{source}/{YYYY-MM-DD}/
    vintage_dir = project_root / "data" / "vintages" / source_name / VINTAGE_DATE.isoformat()
    vintage_dir.mkdir(parents=True, exist_ok=True)
    
    # Create appropriate data based on source
    if source_name == "bls_ces":
        # CES employment data
        dates = pd.date_range(start="2020-01-01", periods=num_rows, freq="MS")
        df = pd.DataFrame({
            "date": dates,
            "series_id": "CES0000000001",
            "value": 150000 + np.random.randn(num_rows).cumsum() * 100,
            "series_name": "Total Nonfarm Payrolls"
        })
    
    elif source_name == "bls_laus":
        # LAUS state employment data
        dates = pd.date_range(start="2020-01-01", periods=num_rows, freq="MS")
        df = pd.DataFrame({
            "date": dates,
            "series_id": "LASST060000000005",
            "state_fips": "06",
            "state_name": "California",
            "measure": "employment_level",
            "value": 15000 + np.random.randn(num_rows).cumsum() * 50
        })
    
    elif source_name == "ui_claims":
        # UI Claims data
        dates = pd.date_range(start="2020-01-01", periods=num_rows, freq="W")
        df = pd.DataFrame({
            "report_date": dates,
            "state_code": "US",
            "initial_claims": 200000 + np.random.randn(num_rows) * 10000,
            "continued_claims": 1800000 + np.random.randn(num_rows) * 50000
        })
    
    elif source_name == "treasury_withholdings":
        # Treasury withholdings
        dates = pd.date_range(start="2020-01-01", periods=num_rows, freq="D")
        df = pd.DataFrame({
            "record_date": dates,
            "account": "Federal Taxes Withheld",
            "close_today_bal": 12000000 + np.random.randn(num_rows) * 100000
        })
    
    else:
        # Generic time series
        dates = pd.date_range(start="2020-01-01", periods=num_rows, freq="MS")
        df = pd.DataFrame({
            "date": dates,
            "value": 1000 + np.random.randn(num_rows).cumsum() * 10
        })
    
    # Save as vintage file
    vintage_file = vintage_dir / f"{source_name}_vintage.parquet"
    df.to_parquet(vintage_file, index=False)
    
    logger.info(f"Created test vintage: {vintage_file}")
    logger.info(f"  Rows: {len(df)}, Columns: {list(df.columns)}")
    
    return vintage_file


def main():
    """Create test vintages for all major sources"""
    logger.info(f"Creating test vintages for date: {VINTAGE_DATE}")
    
    sources = [
        "bls_ces",
        "bls_laus", 
        "ui_claims",
        "treasury_withholdings",
        "weather",
        "strikes",
        "cnbfs"
    ]
    
    created = []
    for source in sources:
        try:
            vintage_file = create_test_vintage(source, num_rows=120)
            created.append(vintage_file)
        except Exception as e:
            logger.error(f"Failed to create vintage for {source}: {e}")
    
    logger.info(f"\n✅ Created {len(created)} test vintages")
    logger.info(f"Location: data/vintages/*/{VINTAGE_DATE.isoformat()}/")
    logger.info("\nThese are TEST VINTAGES for baseline verification only.")
    logger.info("Production should use real ETL-generated data.")
    
    return len(created) > 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

