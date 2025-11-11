#!/usr/bin/env python3
"""
Seed Public Data
Initial data ingestion for all public data sources
Run this once during setup to populate vintages
"""

import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from etl.public.claims import UIClaimsETL


def seed_ui_claims():
    """Seed UI Claims data"""
    logger.info("=" * 60)
    logger.info("SEEDING UI CLAIMS")
    logger.info("=" * 60)
    
    etl = UIClaimsETL()
    success = etl.run()
    
    if success:
        logger.info("✅ UI Claims seeded successfully")
        return True
    else:
        logger.error("❌ UI Claims seeding failed")
        return False


def main():
    """
    Seed all public data sources
    """
    logger.info("=" * 60)
    logger.info("FORECAST-LABOR DATA SEEDING")
    logger.info(f"Started: {datetime.now()}")
    logger.info("=" * 60)
    
    results = {}
    
    # Seed UI Claims (most critical)
    results["ui_claims"] = seed_ui_claims()
    
    # TODO: Add other public sources
    # results["treasury"] = seed_treasury_withholdings()
    # results["ces"] = seed_ces()
    # results["laus"] = seed_laus()
    # results["strikes"] = seed_strikes()
    # results["weather"] = seed_weather()
    # results["cnbfs"] = seed_cnbfs()
    
    # Summary
    logger.info("=" * 60)
    logger.info("SEEDING SUMMARY")
    logger.info("=" * 60)
    
    for source, success in results.items():
        status = "✅" if success else "❌"
        logger.info(f"{status} {source}")
    
    total = len(results)
    succeeded = sum(results.values())
    
    logger.info("")
    logger.info(f"Total: {succeeded}/{total} sources seeded successfully")
    logger.info(f"Completed: {datetime.now()}")
    logger.info("=" * 60)
    
    return all(results.values())


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

