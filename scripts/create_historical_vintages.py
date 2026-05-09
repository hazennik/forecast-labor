#!/usr/bin/env python3
"""
Create Historical Vintage Snapshots from Real BLS CES Data

This script creates pseudo-vintage snapshots by truncating real BLS data
at different historical points in time. This simulates what data would
have been available at each vintage date for vintage-honest backtesting.

The resulting vintages contain REAL BLS data values, just truncated to
represent the information set available at each historical date.

This approach is valid for Phase 6.3.1a DFM validation because:
- Uses actual NFP values (not synthetic)
- Simulates information availability at each vintage date
- Enables testing on real data patterns and characteristics

Usage:
    docker compose exec etl python scripts/create_historical_vintages.py
"""

import sys
from pathlib import Path
from datetime import date
from dateutil.relativedelta import relativedelta
from typing import List

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from loguru import logger
from etl.common.vintage import VintageManager


def create_historical_vintages(
    source_vintage_date: date,
    num_vintages: int = 12,
    vintage_interval_months: int = 3,
    min_history_months: int = 60,
) -> List[date]:
    """
    Create historical pseudo-vintages from real BLS CES data.

    Args:
        source_vintage_date: Date of the source vintage with full data
        num_vintages: Number of historical vintages to create
        vintage_interval_months: Months between each vintage
        min_history_months: Minimum months of history required in each vintage

    Returns:
        List of created vintage dates
    """
    vm = VintageManager(Path("data/vintages"))

    # Load source vintage with real data
    logger.info(f"Loading source vintage: {source_vintage_date}")
    source_data = vm.load_vintage("bls_ces", source_vintage_date)

    if source_data is None or source_data.empty:
        raise ValueError(f"No data found for source vintage {source_vintage_date}")

    # Get date range
    source_data["date"] = pd.to_datetime(source_data["date"])
    min_date = source_data["date"].min()
    max_date = source_data["date"].max()

    logger.info(f"Source data range: {min_date.date()} to {max_date.date()}")
    logger.info(f"Source data rows: {len(source_data)}")

    # Calculate vintage dates going backwards
    created_vintages = []

    for i in range(num_vintages):
        # Calculate vintage date (going backwards from most recent)
        months_back = i * vintage_interval_months
        vintage_date = max_date.date() - relativedelta(months=months_back)

        # Round to first of month
        vintage_date = date(vintage_date.year, vintage_date.month, 1)

        # Check if we have enough history
        data_cutoff = vintage_date
        earliest_data = min_date.date()
        history_months = (data_cutoff.year - earliest_data.year) * 12 + (
            data_cutoff.month - earliest_data.month
        )

        if history_months < min_history_months:
            logger.warning(
                f"Skipping vintage {vintage_date}: only {history_months} months history "
                f"(need {min_history_months})"
            )
            continue

        # Create truncated dataset (only data available at vintage date)
        truncated_data = source_data[source_data["date"] <= pd.Timestamp(vintage_date)].copy()

        if truncated_data.empty:
            logger.warning(f"No data available for vintage {vintage_date}, skipping")
            continue

        # Log vintage info
        nfp_data = truncated_data[truncated_data["series_id"] == "CES0000000001"]
        logger.info(
            f"Creating vintage {vintage_date}: {len(truncated_data)} rows, "
            f"{len(nfp_data)} NFP observations, "
            f"data range: {truncated_data['date'].min().date()} to {truncated_data['date'].max().date()}"
        )

        # Check if vintage already exists
        existing_vintages = vm.list_vintages("bls_ces")
        if vintage_date in existing_vintages:
            logger.info(f"Vintage {vintage_date} already exists, overwriting...")
            # Allow overwrite for historical vintages

        # Create vintage
        try:
            vm.create_vintage(
                source_name="bls_ces",
                data=truncated_data,
                vintage_date=vintage_date,
                allow_overwrite=True,  # Allow overwriting for historical reconstruction
            )
            created_vintages.append(vintage_date)
            logger.info(f"✅ Created vintage: {vintage_date}")
        except Exception as e:
            logger.error(f"Failed to create vintage {vintage_date}: {e}")

    return created_vintages


def main():
    """Create historical vintages for Phase 6.3.1a DFM validation."""
    logger.info("=" * 60)
    logger.info("CREATING HISTORICAL VINTAGES FROM REAL BLS CES DATA")
    logger.info("=" * 60)

    # Check for real data vintage
    vm = VintageManager(Path("data/vintages"))
    available_vintages = vm.list_vintages("bls_ces")

    logger.info(f"Available BLS CES vintages: {available_vintages}")

    # Use the most recent vintage as source (should be real data)
    if not available_vintages:
        logger.error("No BLS CES vintages available. Run ETL first.")
        return False

    source_vintage = available_vintages[-1]
    logger.info(f"Using source vintage: {source_vintage}")

    # Verify it's real data (not synthetic)
    source_data = vm.load_vintage("bls_ces", source_vintage)

    # Check if source column exists indicating real data
    if "source" in source_data.columns:
        source_type = source_data["source"].iloc[0] if len(source_data) > 0 else "unknown"
        logger.info(f"Source data type: {source_type}")

        if "synthetic" in str(source_type).lower():
            logger.warning("⚠️ Source vintage appears to be synthetic data!")
            logger.warning("For Phase 6.3.1a, run CES ETL first to get real data:")
            logger.warning(
                "  docker compose exec etl python -c \"from etl.public.bls_ces.ces_etl import CESETL; import os; CESETL(api_key=os.getenv('BLS_API_KEY')).run()\""
            )
            return False

    # Check NFP series exists with reasonable data
    nfp_data = source_data[source_data["series_id"] == "CES0000000001"]
    if len(nfp_data) < 60:
        logger.error(f"Insufficient NFP data: {len(nfp_data)} observations (need 60+)")
        return False

    logger.info(f"NFP observations in source: {len(nfp_data)}")

    # Create historical vintages
    # 12 vintages, 3 months apart = 3 years of backtesting
    created = create_historical_vintages(
        source_vintage_date=source_vintage,
        num_vintages=15,  # Create 15 vintages to ensure we have 10+ valid ones
        vintage_interval_months=3,  # Quarterly vintages
        min_history_months=60,  # Need at least 5 years of history for training
    )

    logger.info("=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Created {len(created)} historical vintages")

    for v in sorted(created):
        logger.info(f"  - {v}")

    # Final verification
    all_vintages = vm.list_vintages("bls_ces")
    logger.info(f"\nTotal BLS CES vintages now available: {len(all_vintages)}")

    if len(created) >= 10:
        logger.info("✅ Phase 6.3.1a requirement met: 10+ vintage dates available")
        return True
    else:
        logger.warning(f"⚠️ Only {len(created)} vintages created (need 10+)")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
