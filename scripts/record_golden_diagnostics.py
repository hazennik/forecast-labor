"""
Golden Seasonal Diagnostics Recorder

Records baseline M-statistics and Q-statistics from seasonal adjustment.
These baselines are used in CI/CD to detect quality degradation.

Usage:
    python scripts/record_golden_diagnostics.py --vintage-date 2024-01-15
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Dict, Any

from loguru import logger

# Golden diagnostics file
GOLDEN_DIAGNOSTICS_FILE = Path("tests/fixtures/golden_baselines/golden_seasonal_diagnostics.json")

# Pinned vintage date
PINNED_VINTAGE_DATE = date(2024, 1, 15)

# Key series to monitor
MONITORED_SERIES = [
    "CES0000000001",  # Total Nonfarm (primary NFP series)
    "CES0500000003",  # Total Private
    "LASST060000000000003",  # CA Unemployment Rate
]


def record_golden_diagnostics(vintage_date: date, output_file: Path = GOLDEN_DIAGNOSTICS_FILE) -> bool:
    """
    Record golden seasonal adjustment diagnostics.
    
    Args:
        vintage_date: Vintage date to use
        output_file: Output file path
        
    Returns:
        True if successful
    """
    logger.info(f"Recording golden diagnostics for vintage: {vintage_date}")
    
    # TODO: This would typically run actual seasonal adjustment
    # For now, create template structure with example values
    
    golden_diagnostics = {
        "vintage_date": vintage_date.isoformat(),
        "recorded_at": str(date.today()),
        "series": {}
    }
    
    # Template M-statistics (from literature / typical good values)
    for series_id in MONITORED_SERIES:
        golden_diagnostics["series"][series_id] = {
            "m_statistics": {
                "m1": 0.15,  # Relative contribution of irregular over 3 months span
                "m2": 0.20,  # Relative contribution of irregular to stationary portion
                "m3": 0.50,  # Amount of month-to-month change compared to irregular
                "m4": 0.45,  # Randomness of irregular
                "m5": 0.30,  # Number of periods for cyclical dominance
                "m6": 0.25,  # Amount of annual change compared to irregular
                "m7": 0.35,  # Amount of MCD compared to TD
                "m8": 0.40,  # Smoothness of SI curve
                "m9": 0.20,  # Average linear movement in final SI ratios
                "m10": 0.55,  # Average linear movement in final irregular
                "m11": 0.60,  # Average linear movement in final seasonal factors
                "q": 0.42,   # Overall Q-statistic
            },
            "thresholds": {
                "m1_max": 0.25,
                "m2_max": 0.30,
                "m3_max": 0.70,
                "m4_max": 0.60,
                "m5_max": 0.45,
                "m6_max": 0.35,
                "m7_max": 0.50,
                "m8_max": 0.55,
                "m9_max": 0.30,
                "m10_max": 0.70,
                "m11_max": 0.75,
                "q_max": 0.50,
            },
            "quality_grade": "acceptable",  # acceptable, good, excellent
            "notes": "Baseline diagnostics for regression testing"
        }
    
    # Save
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w') as f:
        json.dump(golden_diagnostics, f, indent=2)
    
    logger.info(f"✅ Golden diagnostics saved to: {output_file}")
    logger.info(f"   Series monitored: {len(golden_diagnostics['series'])}")
    
    return True


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

