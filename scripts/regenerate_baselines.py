#!/usr/bin/env python3
"""
Regenerate Golden Baselines for CI/CD

This script regenerates both vintage hash baselines and seasonal diagnostics baselines.
Run this after:
- Changing random seed in create_test_vintages.py
- Updating seasonal adjustment logic
- Making structural changes to ETL outputs

Usage:
    python scripts/regenerate_baselines.py
    
    Or via Makefile:
    make regenerate-baselines
"""

import sys
from pathlib import Path
from datetime import date

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from loguru import logger


def main():
    """Regenerate all golden baselines."""

    logger.info("=" * 70)
    logger.info("Regenerating Golden Baselines for CI/CD")
    logger.info("=" * 70)

    # Pinned vintage date for testing
    vintage_date = date(2024, 1, 15)

    # Step 1: Generate deterministic test vintages
    logger.info("\n[1/3] Generating deterministic test vintages...")
    logger.info("Using random seed 42 for reproducibility")

    try:
        from scripts.create_test_vintages import main as create_vintages

        create_vintages()
        logger.success("✅ Deterministic test vintages generated")
    except Exception as e:
        logger.error(f"❌ Failed to generate test vintages: {e}")
        sys.exit(1)

    # Step 2: Record vintage determinism baseline
    logger.info("\n[2/3] Recording vintage determinism baseline...")
    logger.info(f"Computing SHA256 hashes for vintage date: {vintage_date}")

    try:
        import subprocess

        result = subprocess.run(
            [
                sys.executable,
                "scripts/verify_vintage_determinism.py",
                "--vintage-date",
                vintage_date.isoformat(),
                "--create-baseline",
            ],
            cwd=project_root,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            logger.error(f"❌ Failed to create vintage baseline: {result.stderr}")
            sys.exit(1)

        logger.success("✅ Vintage determinism baseline recorded")
    except Exception as e:
        logger.error(f"❌ Failed to record vintage baseline: {e}")
        sys.exit(1)

    # Step 3: Generate placeholder diagnostics (already deterministic)
    logger.info("\n[3/3] Generating placeholder seasonal diagnostics...")

    try:
        from scripts.create_test_diagnostics import main as create_diagnostics

        create_diagnostics()
        logger.success("✅ Placeholder diagnostics generated")
    except Exception as e:
        logger.error(f"❌ Failed to generate diagnostics: {e}")
        sys.exit(1)

    # Success summary
    logger.info("\n" + "=" * 70)
    logger.success("✅ All golden baselines regenerated successfully!")
    logger.info("=" * 70)
    logger.info("\nGenerated:")
    logger.info("  - Deterministic test vintages (with seed 42)")
    logger.info("  - Vintage determinism baseline (SHA256 hashes)")
    logger.info("  - Placeholder seasonal diagnostics")
    logger.info("\n🎯 CI/CD determinism verification will now function correctly")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
