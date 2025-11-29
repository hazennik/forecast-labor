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
from etl.public.treasury_withholdings import TreasuryWithholdingsETL
from etl.public.bls_ces import CESETL
from etl.public.bls_laus import LAUSETL
from etl.public.strikes import StrikesETL
from etl.public.weather import WeatherETL
from etl.public.cnbfs import CNBFSETL


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


def seed_treasury_withholdings():
    """Seed Treasury Withholdings data"""
    logger.info("=" * 60)
    logger.info("SEEDING TREASURY WITHHOLDINGS")
    logger.info("=" * 60)
    
    etl = TreasuryWithholdingsETL()
    success = etl.run()
    
    if success:
        logger.info("✅ Treasury Withholdings seeded successfully")
        return True
    else:
        logger.error("❌ Treasury Withholdings seeding failed")
        return False


def seed_ces():
    """Seed BLS CES (Nonfarm Payrolls) data"""
    logger.info("=" * 60)
    logger.info("SEEDING BLS CES (NONFARM PAYROLLS)")
    logger.info("=" * 60)
    
    import os
    api_key = os.getenv('BLS_API_KEY')
    etl = CESETL(api_key=api_key)
    success = etl.run()
    
    if success:
        logger.info("✅ CES seeded successfully")
        return True
    else:
        logger.error("❌ CES seeding failed")
        return False


def seed_laus():
    """Seed BLS LAUS (State Employment) data"""
    logger.info("=" * 60)
    logger.info("SEEDING BLS LAUS (STATE EMPLOYMENT)")
    logger.info("=" * 60)
    
    import os
    api_key = os.getenv('BLS_API_KEY')
    etl = LAUSETL(api_key=api_key)
    success = etl.run()
    
    if success:
        logger.info("✅ LAUS seeded successfully")
        return True
    else:
        logger.error("❌ LAUS seeding failed")
        return False


def seed_strikes():
    """Seed BLS Strikes data"""
    logger.info("=" * 60)
    logger.info("SEEDING STRIKES DATA")
    logger.info("=" * 60)
    
    etl = StrikesETL()
    success = etl.run()
    
    if success:
        logger.info("✅ Strikes seeded successfully")
        return True
    else:
        logger.error("❌ Strikes seeding failed")
        return False


def seed_weather():
    """Seed NOAA Weather data"""
    logger.info("=" * 60)
    logger.info("SEEDING WEATHER DISRUPTIONS")
    logger.info("=" * 60)
    
    etl = WeatherETL()
    success = etl.run()
    
    if success:
        logger.info("✅ Weather seeded successfully")
        return True
    else:
        logger.error("❌ Weather seeding failed")
        return False


def seed_cnbfs():
    """Seed Census Business Formation Statistics"""
    logger.info("=" * 60)
    logger.info("SEEDING BUSINESS FORMATION STATISTICS")
    logger.info("=" * 60)
    
    etl = CNBFSETL()
    success = etl.run()
    
    if success:
        logger.info("✅ CNBFS seeded successfully")
        return True
    else:
        logger.error("❌ CNBFS seeding failed")
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
    
    # Seed all public data sources (in order of importance)
    results["ui_claims"] = seed_ui_claims()
    results["treasury_withholdings"] = seed_treasury_withholdings()
    results["ces"] = seed_ces()
    results["laus"] = seed_laus()
    results["strikes"] = seed_strikes()
    results["weather"] = seed_weather()
    results["cnbfs"] = seed_cnbfs()
    
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

