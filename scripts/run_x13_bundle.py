#!/usr/bin/env python3
"""
X-13 Bundle Runner (Alias to run_seasonal_adjustment.py)

This script is maintained for backwards compatibility with Makefile targets.
It simply wraps the main seasonal adjustment script.

Usage:
    python scripts/run_x13_bundle.py [args]
    
All arguments are passed through to run_seasonal_adjustment.py
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger


def main():
    """Main entry point - wraps run_seasonal_adjustment.py"""
    logger.info("X-13 Bundle Runner (wrapper for run_seasonal_adjustment.py)")
    logger.info("=" * 60)

    # Import and run the main seasonal adjustment script
    try:
        from scripts import run_seasonal_adjustment

        # Execute main function from run_seasonal_adjustment
        logger.info("Executing seasonal adjustment pipeline...")
        run_seasonal_adjustment.main()

    except Exception as e:
        logger.error(f"X-13 bundle execution failed: {e}")
        logger.exception(e)
        sys.exit(1)


if __name__ == "__main__":
    main()
