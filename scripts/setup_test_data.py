#!/usr/bin/env python3
"""
Setup Test Data for Development and CI

This script generates synthetic test vintages and diagnostics required for:
- Running the test suite (287 tests)
- Vintage determinism verification
- Seasonal adjustment scripts
- Feature building scripts

⚠️ IMPORTANT: This generates SYNTHETIC test data, not production data.

For production deployment, run real ETL pipelines:
    make seed  # Run all ETL pipelines with production API keys

Usage:
    python scripts/setup_test_data.py
    
    Or via Makefile:
    make setup-test-data
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from loguru import logger


def main():
    """Generate all test data required for development and CI."""
    
    logger.info("=" * 60)
    logger.info("Setting up test data for Forecast-Labor")
    logger.info("=" * 60)
    
    # Step 1: Generate test vintages
    logger.info("\n[1/2] Generating test vintages...")
    logger.info("Creating synthetic vintage data for 7 sources...")
    
    try:
        from scripts.create_test_vintages import main as create_vintages
        create_vintages()
        logger.success("✅ Test vintages created successfully")
    except Exception as e:
        logger.error(f"❌ Failed to create test vintages: {e}")
        sys.exit(1)
    
    # Step 2: Generate test diagnostics
    logger.info("\n[2/2] Generating test diagnostics...")
    logger.info("Creating placeholder seasonal diagnostics...")
    
    try:
        from scripts.create_test_diagnostics import main as create_diagnostics
        create_diagnostics()
        logger.success("✅ Test diagnostics created successfully")
    except Exception as e:
        logger.error(f"❌ Failed to create test diagnostics: {e}")
        sys.exit(1)
    
    # Success summary
    logger.info("\n" + "=" * 60)
    logger.success("✅ Test data setup complete!")
    logger.info("=" * 60)
    logger.info("\nGenerated:")
    logger.info("  - 7 synthetic vintage sources (data/vintages/*/2024-01-15/*.parquet)")
    logger.info("  - Placeholder seasonal diagnostics (tests/fixtures/golden_baselines/)")
    logger.info("\n⚠️  Remember: This is SYNTHETIC test data")
    logger.info("   For production, run: make seed")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()

