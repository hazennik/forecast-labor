#!/usr/bin/env python3
"""
ETL Runner - Execute data ingestion pipelines

Runs all or specified ETL pipelines to ingest public data sources.

Usage:
    python scripts/run_etl.py              # Run all ETL pipelines
    python scripts/run_etl.py --source claims  # Run specific source
    python scripts/run_etl.py --list        # List available sources
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

# Import all ETL pipelines
from etl.public.claims import UIClaimsETL
from etl.public.treasury_withholdings import TreasuryWithholdingsETL
from etl.public.bls_ces import CESETL
from etl.public.bls_laus import LAUSETL
from etl.public.strikes import StrikesETL
from etl.public.weather import WeatherETL
from etl.public.cnbfs import CNBFSETL


# Available ETL pipelines
ETL_PIPELINES = {
    "claims": ("UI Claims", UIClaimsETL),
    "treasury": ("Treasury Withholdings", TreasuryWithholdingsETL),
    "ces": ("BLS CES (Nonfarm Payrolls)", CESETL),
    "laus": ("BLS LAUS (State Employment)", LAUSETL),
    "strikes": ("BLS Work Stoppages", StrikesETL),
    "weather": ("NOAA Weather Events", WeatherETL),
    "cnbfs": ("Census Business Formation", CNBFSETL),
}


def list_sources():
    """List all available ETL sources"""
    logger.info("Available ETL Sources:")
    logger.info("=" * 60)
    for key, (name, _) in ETL_PIPELINES.items():
        logger.info(f"  {key:12} - {name}")
    logger.info("=" * 60)


def run_etl(source: str = None):
    """
    Run ETL pipeline(s)
    
    Args:
        source: Source name or None for all sources
    """
    if source:
        # Run specific source
        if source not in ETL_PIPELINES:
            logger.error(f"Unknown source: {source}")
            logger.info("Use --list to see available sources")
            sys.exit(1)
        
        name, etl_class = ETL_PIPELINES[source]
        logger.info(f"Running {name} ETL...")
        logger.info("=" * 60)
        
        try:
            etl = etl_class()
            etl.run()
            logger.info(f"✅ {name} ETL completed successfully")
        except Exception as e:
            logger.error(f"❌ {name} ETL failed: {e}")
            logger.exception(e)
            sys.exit(1)
    
    else:
        # Run all sources
        logger.info("Running ALL ETL pipelines...")
        logger.info("=" * 60)
        
        results = {}
        for key, (name, etl_class) in ETL_PIPELINES.items():
            logger.info(f"\n{'='*60}")
            logger.info(f"Running {name} ETL...")
            logger.info(f"{'='*60}")
            
            try:
                etl = etl_class()
                etl.run()
                results[key] = "SUCCESS"
                logger.info(f"✅ {name} ETL completed successfully\n")
            except Exception as e:
                results[key] = f"FAILED: {e}"
                logger.error(f"❌ {name} ETL failed: {e}")
                # Continue with other pipelines
        
        # Summary
        logger.info(f"\n{'='*60}")
        logger.info("ETL Run Summary:")
        logger.info(f"{'='*60}")
        
        success_count = sum(1 for v in results.values() if v == "SUCCESS")
        total_count = len(results)
        
        for key, status in results.items():
            name = ETL_PIPELINES[key][0]
            status_icon = "✅" if status == "SUCCESS" else "❌"
            logger.info(f"{status_icon} {name:30} - {status}")
        
        logger.info(f"{'='*60}")
        logger.info(f"Total: {success_count}/{total_count} pipelines succeeded")
        
        if success_count < total_count:
            sys.exit(1)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Run ETL pipelines to ingest public data"
    )
    
    parser.add_argument(
        "--source",
        type=str,
        help="Run specific source only (e.g., claims, ces, laus)"
    )
    
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all available sources"
    )
    
    args = parser.parse_args()
    
    if args.list:
        list_sources()
        sys.exit(0)
    
    run_etl(source=args.source)


if __name__ == "__main__":
    main()

