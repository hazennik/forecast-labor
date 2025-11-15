#!/usr/bin/env python3
"""
Create minimal test seasonal diagnostics for golden baseline verification.
This creates placeholder diagnostics with realistic values for testing purposes.
"""

import json
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from loguru import logger

# Golden diagnostics file location
GOLDEN_DIAGNOSTICS_FILE = project_root / "tests" / "fixtures" / "golden_baselines" / "golden_seasonal_diagnostics.json"

# Typical acceptable M-statistic values (these are within normal ranges)
# Reference: U.S. Census Bureau X-13ARIMA-SEATS documentation
PLACEHOLDER_M_STATS = {
    "M1": 0.25,  # < 0.30 is acceptable
    "M2": 0.28,  # < 0.35 is acceptable
    "M3": 0.65,  # < 0.80 is acceptable
    "M4": 0.55,  # < 0.70 is acceptable
    "M5": 0.35,  # < 0.50 is acceptable
    "M6": 0.32,  # < 0.40 is acceptable
    "M7": 0.48,  # < 0.60 is acceptable (overall quality)
    "M8": 0.52,  # < 0.65 is acceptable
    "M9": 0.28,  # < 0.35 is acceptable
    "M10": 0.68,  # < 0.80 is acceptable
    "M11": 0.72,  # < 0.85 is acceptable (combined)
}

PLACEHOLDER_Q_STATS = {
    "Q": 0.85,  # < 1.0 is acceptable
    "p_value": 0.42  # > 0.05 is good
}

def create_test_diagnostics():
    """Create test seasonal diagnostics with placeholder values"""
    
    logger.info("Creating test seasonal diagnostics")
    
    # Series to monitor (from the existing golden file structure)
    series_config = {
        "CES0000000001": {
            "name": "Total Nonfarm Payrolls",
            "source": "bls_ces"
        },
        "CES0500000003": {
            "name": "Total Private Employment",
            "source": "bls_ces"
        },
        "CES4200000001": {
            "name": "Retail Trade Employment",
            "source": "bls_ces"
        },
        "CES7000000001": {
            "name": "Leisure and Hospitality Employment",
            "source": "bls_ces"
        }
    }
    
    # Build golden diagnostics structure
    golden_diagnostics = {
        "_comment": "Golden seasonal diagnostics for X-13 regression testing",
        "_generated_by": "scripts/create_test_diagnostics.py (TEST DATA)",
        "_pinned_vintage_date": "2024-01-15",
        "_instructions": "These are PLACEHOLDER values for testing. Production should run: python scripts/record_golden_diagnostics.py --vintage-date 2024-01-15 --record",
        "_note": "M-statistics are within acceptable ranges per Census Bureau guidelines",
        "_quality_thresholds": {
            "M7_acceptable": 1.0,
            "M8_acceptable": 1.0,
            "M9_acceptable": 1.0,
            "M10_acceptable": 1.0,
            "M11_acceptable": 1.0,
            "Q_stat_acceptable": 1.0
        },
        "series": {}
    }
    
    # Add each series with placeholder diagnostics
    for series_id, info in series_config.items():
        golden_diagnostics["series"][series_id] = {
            "name": info["name"],
            "source": info["source"],
            "m_statistics": PLACEHOLDER_M_STATS.copy(),
            "q_statistics": PLACEHOLDER_Q_STATS.copy(),
            "quality_grade": "acceptable (test data)",
            "recorded_at": datetime.now().isoformat()
        }
        
        logger.info(f"Added diagnostics for {series_id}: {info['name']}")
    
    # Save to file
    GOLDEN_DIAGNOSTICS_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    with open(GOLDEN_DIAGNOSTICS_FILE, 'w') as f:
        json.dump(golden_diagnostics, f, indent=2)
    
    logger.info(f"\n✅ Test diagnostics saved to: {GOLDEN_DIAGNOSTICS_FILE}")
    logger.info(f"   Series: {len(golden_diagnostics['series'])}")
    logger.info("\n⚠️  NOTE: These are PLACEHOLDER diagnostics for testing only.")
    logger.info("   Production should use real X-13 diagnostics from:")
    logger.info("   python scripts/record_golden_diagnostics.py --vintage-date 2024-01-15 --record")
    
    return True


def main():
    """Main entry point"""
    try:
        success = create_test_diagnostics()
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"Failed to create test diagnostics: {e}")
        logger.exception(e)
        sys.exit(1)


if __name__ == "__main__":
    main()

