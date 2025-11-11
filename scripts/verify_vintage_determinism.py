"""
Vintage Determinism Verification Script

Verifies that vintage data is deterministic and creates hash baselines.
This script is used in CI/CD to ensure reproducibility.

Usage:
    python scripts/verify_vintage_determinism.py --vintage-date 2024-01-15 --create-baseline
    python scripts/verify_vintage_determinism.py --vintage-date 2024-01-15 --verify
"""

import argparse
import hashlib
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
from loguru import logger


# Pinned vintage date for CI/CD testing (determinism baseline)
PINNED_VINTAGE_DATE = date(2024, 1, 15)

# Baseline hashes file
BASELINE_HASHES_FILE = Path("tests/fixtures/golden_baselines/vintage_hashes.json")

# Data sources to verify
DATA_SOURCES = [
    "ui_claims",
    "treasury_withholdings",
    "bls_ces",
    "bls_laus",
    "strikes",
    "weather",
    "cnbfs"
]


def compute_file_hash(file_path: Path) -> str:
    """
    Compute SHA256 hash of a file.
    
    Args:
        file_path: Path to file
        
    Returns:
        Hex digest of SHA256 hash
    """
    sha256_hash = hashlib.sha256()
    
    with open(file_path, "rb") as f:
        # Read in chunks for large files
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    
    return sha256_hash.hexdigest()


def compute_dataframe_hash(df: pd.DataFrame) -> str:
    """
    Compute deterministic hash of DataFrame contents.
    
    Args:
        df: DataFrame to hash
        
    Returns:
        Hex digest of hash
    """
    # Convert to CSV for deterministic ordering
    csv_bytes = df.to_csv(index=False).encode('utf-8')
    
    return hashlib.sha256(csv_bytes).hexdigest()


def find_vintage_files(vintage_date: date, base_path: Path = Path("data/vintages")) -> Dict[str, List[Path]]:
    """
    Find all vintage files for a given date.
    
    Args:
        vintage_date: Vintage date to find
        base_path: Base vintage directory
        
    Returns:
        Dictionary mapping source name to list of files
    """
    vintage_date_str = vintage_date.strftime("%Y-%m-%d")
    vintage_files = {}
    
    for source in DATA_SOURCES:
        source_dir = base_path / source / vintage_date_str
        
        if source_dir.exists():
            files = list(source_dir.glob("*.parquet"))
            if files:
                vintage_files[source] = files
                logger.info(f"Found {len(files)} files for {source}")
            else:
                logger.warning(f"No files found for {source}")
        else:
            logger.warning(f"Directory not found: {source_dir}")
    
    return vintage_files


def compute_vintage_hashes(vintage_files: Dict[str, List[Path]]) -> Dict[str, Dict[str, str]]:
    """
    Compute hashes for all vintage files.
    
    Args:
        vintage_files: Dictionary of source -> files
        
    Returns:
        Dictionary of source -> {filename: hash}
    """
    hashes = {}
    
    for source, files in vintage_files.items():
        source_hashes = {}
        
        for file_path in files:
            logger.info(f"Hashing {file_path}")
            
            # Compute file hash
            file_hash = compute_file_hash(file_path)
            
            # Also hash DataFrame contents for double verification
            try:
                df = pd.read_parquet(file_path)
                df_hash = compute_dataframe_hash(df)
                
                source_hashes[file_path.name] = {
                    "file_hash": file_hash,
                    "dataframe_hash": df_hash,
                    "row_count": len(df),
                    "column_count": len(df.columns),
                    "columns": list(df.columns)
                }
                
                logger.info(f"  File hash: {file_hash[:16]}...")
                logger.info(f"  DataFrame hash: {df_hash[:16]}...")
                logger.info(f"  Rows: {len(df)}, Columns: {len(df.columns)}")
                
            except Exception as e:
                logger.error(f"Error reading {file_path}: {e}")
                source_hashes[file_path.name] = {
                    "file_hash": file_hash,
                    "error": str(e)
                }
        
        hashes[source] = source_hashes
    
    return hashes


def create_baseline(vintage_date: date, output_file: Path = BASELINE_HASHES_FILE) -> bool:
    """
    Create baseline hash file for vintage data.
    
    Args:
        vintage_date: Vintage date to baseline
        output_file: Output file path
        
    Returns:
        True if successful
    """
    logger.info(f"Creating baseline for vintage date: {vintage_date}")
    
    # Find vintage files
    vintage_files = find_vintage_files(vintage_date)
    
    if not vintage_files:
        logger.error("No vintage files found")
        return False
    
    # Compute hashes
    hashes = compute_vintage_hashes(vintage_files)
    
    # Create baseline document
    baseline = {
        "vintage_date": vintage_date.isoformat(),
        "created_at": datetime.now().isoformat(),
        "sources": hashes,
        "metadata": {
            "total_sources": len(hashes),
            "total_files": sum(len(files) for files in hashes.values())
        }
    }
    
    # Save baseline
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w') as f:
        json.dump(baseline, f, indent=2)
    
    logger.info(f"✅ Baseline saved to: {output_file}")
    logger.info(f"   Sources: {baseline['metadata']['total_sources']}")
    logger.info(f"   Files: {baseline['metadata']['total_files']}")
    
    return True


def verify_against_baseline(vintage_date: date, baseline_file: Path = BASELINE_HASHES_FILE) -> bool:
    """
    Verify vintage data against baseline hashes.
    
    Args:
        vintage_date: Vintage date to verify
        baseline_file: Baseline hash file
        
    Returns:
        True if all hashes match
    """
    logger.info(f"Verifying vintage date: {vintage_date} against baseline")
    
    # Load baseline
    if not baseline_file.exists():
        logger.error(f"Baseline file not found: {baseline_file}")
        return False
    
    with open(baseline_file, 'r') as f:
        baseline = json.load(f)
    
    baseline_date = date.fromisoformat(baseline["vintage_date"])
    
    if baseline_date != vintage_date:
        logger.warning(f"Vintage dates don't match: {vintage_date} vs {baseline_date}")
    
    # Find current vintage files
    vintage_files = find_vintage_files(vintage_date)
    
    if not vintage_files:
        logger.error("No vintage files found")
        return False
    
    # Compute current hashes
    current_hashes = compute_vintage_hashes(vintage_files)
    
    # Compare
    all_match = True
    mismatches = []
    
    for source, baseline_files in baseline["sources"].items():
        if source not in current_hashes:
            logger.error(f"❌ Source missing: {source}")
            all_match = False
            mismatches.append(f"Missing source: {source}")
            continue
        
        for filename, baseline_hash_info in baseline_files.items():
            if filename not in current_hashes[source]:
                logger.error(f"❌ File missing: {source}/{filename}")
                all_match = False
                mismatches.append(f"Missing file: {source}/{filename}")
                continue
            
            current_hash_info = current_hashes[source][filename]
            
            # Compare file hashes
            if baseline_hash_info["file_hash"] != current_hash_info["file_hash"]:
                logger.error(f"❌ Hash mismatch: {source}/{filename}")
                logger.error(f"   Expected: {baseline_hash_info['file_hash'][:16]}...")
                logger.error(f"   Got:      {current_hash_info['file_hash'][:16]}...")
                all_match = False
                mismatches.append(f"Hash mismatch: {source}/{filename}")
            else:
                logger.info(f"✅ Hash match: {source}/{filename}")
            
            # Compare DataFrame hashes
            if "dataframe_hash" in baseline_hash_info and "dataframe_hash" in current_hash_info:
                if baseline_hash_info["dataframe_hash"] != current_hash_info["dataframe_hash"]:
                    logger.error(f"❌ DataFrame hash mismatch: {source}/{filename}")
                    all_match = False
                    mismatches.append(f"DataFrame hash mismatch: {source}/{filename}")
    
    # Summary
    if all_match:
        logger.info("✅ All vintage hashes match baseline")
        logger.info("   Determinism verified successfully!")
        return True
    else:
        logger.error(f"❌ Verification failed: {len(mismatches)} mismatches")
        for mismatch in mismatches:
            logger.error(f"   - {mismatch}")
        return False


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Verify vintage data determinism"
    )
    
    parser.add_argument(
        "--vintage-date",
        type=str,
        default=PINNED_VINTAGE_DATE.isoformat(),
        help=f"Vintage date (YYYY-MM-DD). Default: {PINNED_VINTAGE_DATE}"
    )
    
    parser.add_argument(
        "--create-baseline",
        action="store_true",
        help="Create baseline hash file"
    )
    
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify against baseline"
    )
    
    parser.add_argument(
        "--baseline-file",
        type=str,
        default=str(BASELINE_HASHES_FILE),
        help="Baseline hash file path"
    )
    
    args = parser.parse_args()
    
    # Parse vintage date
    try:
        vintage_date = date.fromisoformat(args.vintage_date)
    except ValueError:
        logger.error(f"Invalid date format: {args.vintage_date}")
        sys.exit(1)
    
    baseline_file = Path(args.baseline_file)
    
    # Execute
    if args.create_baseline:
        success = create_baseline(vintage_date, baseline_file)
        sys.exit(0 if success else 1)
    
    elif args.verify:
        success = verify_against_baseline(vintage_date, baseline_file)
        sys.exit(0 if success else 1)
    
    else:
        logger.error("Must specify --create-baseline or --verify")
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

