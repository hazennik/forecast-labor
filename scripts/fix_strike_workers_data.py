#!/usr/bin/env python3
"""
Fix Strike Workers Data
Phase 6.2.0: Derive workers_involved from WSU010 column

The strike vintage data has WSU010 (workers involved in thousands) but
the workers_involved column is all zeros. This script fixes that.
"""

import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from loguru import logger


def fix_strike_vintage_data(vintage_date: str = "2025-11-29"):
    """
    Fix workers_involved column in strike vintage data
    
    Args:
        vintage_date: Vintage date to fix
    """
    vintage_path = Path(f"data/vintages/strikes/{vintage_date}/strikes_vintage.parquet")
    
    if not vintage_path.exists():
        logger.error(f"Vintage file not found: {vintage_path}")
        return False
    
    logger.info(f"Loading strike vintage data: {vintage_path}")
    df = pd.read_parquet(vintage_path)
    
    logger.info(f"Original shape: {df.shape}")
    logger.info(f"Original workers_involved: min={df['workers_involved'].min()}, max={df['workers_involved'].max()}, mean={df['workers_involved'].mean():.2f}")
    
    # Find WSU010 column (workers involved in thousands)
    wsu010_col = None
    for col in df.columns:
        if 'WSU010' in str(col):
            wsu010_col = col
            break
    
    if wsu010_col is None:
        logger.error("WSU010 column not found!")
        return False
    
    logger.info(f"Found workers data in column: {wsu010_col}")
    logger.info(f"WSU010 stats: min={df[wsu010_col].min()}, max={df[wsu010_col].max()}, mean={df[wsu010_col].mean():.2f}, non-zero={( df[wsu010_col] > 0).sum()}")
    
    # Derive workers_involved from WSU010 (convert thousands to actual count)
    df["workers_involved"] = df[wsu010_col] * 1000
    
    logger.info(f"Fixed workers_involved: min={df['workers_involved'].min():.0f}, max={df['workers_involved'].max():.0f}, mean={df['workers_involved'].mean():.0f}")
    logger.info(f"Non-zero workers_involved: {(df['workers_involved'] > 0).sum()} / {len(df)} ({(df['workers_involved'] > 0).sum() / len(df) * 100:.1f}%)")
    
    # Recalculate strike_impact_score
    df["strike_impact_score"] = df["workers_involved"] * df["num_stoppages"]
    
    # Recalculate is_significant_month (>50k workers affected)
    df["is_significant_month"] = df["workers_involved"] > 50000
    
    logger.info(f"Significant months: {df['is_significant_month'].sum()} / {len(df)} ({df['is_significant_month'].sum() / len(df) * 100:.1f}%)")
    
    # Save fixed data
    backup_path = vintage_path.with_suffix('.parquet.backup')
    logger.info(f"Creating backup: {backup_path}")
    df_original = pd.read_parquet(vintage_path)
    df_original.to_parquet(backup_path)
    
    logger.info(f"Saving fixed data: {vintage_path}")
    df.to_parquet(vintage_path, index=False)
    
    logger.info("✅ Strike vintage data fixed successfully")
    
    # Show some examples
    logger.info("\nSample records with significant strikes:")
    significant = df[df["is_significant_month"]].sort_values("workers_involved", ascending=False).head(10)
    print(significant[["date", "workers_involved", "num_stoppages", "strike_impact_score", "is_significant_month"]].to_string())
    
    return True


def main():
    """Main function"""
    logger.info("=" * 70)
    logger.info("FIX STRIKE WORKERS DATA")
    logger.info("Phase 6.2.0: Derive workers_involved from WSU010")
    logger.info("=" * 70)
    
    success = fix_strike_vintage_data("2025-11-29")
    
    if success:
        logger.info("\n✅ SUCCESS: Strike data fixed")
        return 0
    else:
        logger.error("\n❌ FAILED: Could not fix strike data")
        return 1


if __name__ == "__main__":
    sys.exit(main())

