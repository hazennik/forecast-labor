#!/usr/bin/env python3
"""
Run Validation
Execute validation checks on ingested data
"""

import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger
import pandas as pd

from etl.validators import (
    SchemaValidator,
    FreshnessValidator,
    QualityValidator,
    ValidationResult
)


# Validation configurations for each source

UI_CLAIMS_VALIDATION = {
    "schema": {
        "required_columns": ["report_date", "state_code", "initial_claims", "continued_claims"],
        "column_types": {
            "report_date": "datetime",
            "state_code": "str",
            "initial_claims": "numeric",
            "continued_claims": "numeric"
        }
    },
    "freshness": {
        "date_column": "report_date",
        "max_age_days": 14,  # Claims released weekly
        "expected_frequency": "weekly"
    },
    "quality": {
        "critical_columns": ["report_date", "state_code", "initial_claims"],
        "unique_keys": ["report_date", "state_code"],
        "numeric_ranges": {
            "initial_claims": (0, 1000000),  # 0 to 1M
            "continued_claims": (0, 10000000)  # 0 to 10M
        }
    }
}

TREASURY_VALIDATION = {
    "schema": {
        "required_columns": ["date"],
        "column_types": {"date": "datetime"}
    },
    "freshness": {
        "date_column": "date",
        "max_age_days": 7,  # Daily data
        "expected_frequency": "daily"
    },
    "quality": {
        "critical_columns": ["date"],
        "unique_keys": ["date"]
    }
}

CES_VALIDATION = {
    "schema": {
        "required_columns": ["series_id", "date", "value"],
        "column_types": {
            "series_id": "str",
            "date": "datetime",
            "value": "numeric"
        }
    },
    "freshness": {
        "date_column": "date",
        "max_age_days": 45,  # Monthly data
        "expected_frequency": "monthly"
    },
    "quality": {
        "critical_columns": ["series_id", "date", "value"],
        "unique_keys": ["series_id", "date"],
        "numeric_ranges": {
            "value": (-1000, 200000)  # Job changes in thousands
        }
    }
}


def validate_dataset(
    df: pd.DataFrame,
    source_name: str,
    validation_config: dict
) -> bool:
    """
    Validate a dataset using configured validators
    
    Args:
        df: DataFrame to validate
        source_name: Name of data source
        validation_config: Validation configuration
        
    Returns:
        bool: True if validation passed (no blocking failures)
    """
    logger.info(f"Starting validation for: {source_name}")
    logger.info("=" * 60)
    
    all_results = []
    
    # Schema validation
    if "schema" in validation_config:
        logger.info("Running schema validation...")
        schema_config = validation_config["schema"]
        
        schema_validator = SchemaValidator(
            source_name=source_name,
            required_columns=schema_config["required_columns"],
            column_types=schema_config.get("column_types")
        )
        
        schema_results = schema_validator.validate(df)
        all_results.extend(schema_results)
        schema_validator.log_summary(schema_results)
    
    # Freshness validation
    if "freshness" in validation_config:
        logger.info("Running freshness validation...")
        freshness_config = validation_config["freshness"]
        
        freshness_validator = FreshnessValidator(
            source_name=source_name,
            date_column=freshness_config["date_column"],
            max_age_days=freshness_config.get("max_age_days", 7),
            expected_frequency=freshness_config.get("expected_frequency", "daily")
        )
        
        freshness_results = freshness_validator.validate(df)
        all_results.extend(freshness_results)
        freshness_validator.log_summary(freshness_results)
    
    # Quality validation
    if "quality" in validation_config:
        logger.info("Running quality validation...")
        quality_config = validation_config["quality"]
        
        quality_validator = QualityValidator(
            source_name=source_name,
            critical_columns=quality_config.get("critical_columns"),
            unique_keys=quality_config.get("unique_keys"),
            numeric_ranges=quality_config.get("numeric_ranges")
        )
        
        quality_results = quality_validator.validate(df)
        all_results.extend(quality_results)
        quality_validator.log_summary(quality_results)
    
    # Check if pipeline should be blocked
    blocking_failures = [r for r in all_results if r.is_blocking()]
    
    if blocking_failures:
        logger.error(f"❌ Validation BLOCKED: {len(blocking_failures)} critical failures")
        for failure in blocking_failures:
            logger.error(f"  - {failure.rule_name}: {failure.message}")
        return False
    
    # Check for any failures (non-blocking)
    failures = [r for r in all_results if r.status == "failed"]
    if failures:
        logger.warning(f"⚠️  Validation passed with {len(failures)} non-critical failures")
    else:
        logger.info("✅ All validations passed")
    
    return True


def validate_ui_claims(claims_path: Path) -> bool:
    """Validate UI Claims data"""
    logger.info("Loading UI Claims data...")
    df = pd.read_parquet(claims_path)
    
    return validate_dataset(df, "ui_claims", UI_CLAIMS_VALIDATION)


def validate_treasury(treasury_path: Path) -> bool:
    """Validate Treasury Withholdings data"""
    logger.info("Loading Treasury data...")
    df = pd.read_parquet(treasury_path)
    
    return validate_dataset(df, "treasury_withholdings", TREASURY_VALIDATION)


def validate_ces(ces_path: Path) -> bool:
    """Validate CES data"""
    logger.info("Loading CES data...")
    df = pd.read_parquet(ces_path)
    
    return validate_dataset(df, "ces", CES_VALIDATION)


def main():
    """
    Run validation on all data sources
    """
    logger.info("=" * 60)
    logger.info("DATA VALIDATION SUITE")
    logger.info(f"Started: {datetime.now()}")
    logger.info("=" * 60)
    
    data_dir = Path("data/raw")
    
    results = {}
    
    # Validate UI Claims
    claims_files = list((data_dir / "claims").glob("*.parquet"))
    if claims_files:
        latest_claims = max(claims_files, key=lambda p: p.stat().st_mtime)
        results["ui_claims"] = validate_ui_claims(latest_claims)
    else:
        logger.warning("No UI Claims data found")
        results["ui_claims"] = None
    
    # Validate Treasury
    treasury_files = list((data_dir / "treasury").glob("*.parquet"))
    if treasury_files:
        latest_treasury = max(treasury_files, key=lambda p: p.stat().st_mtime)
        results["treasury"] = validate_treasury(latest_treasury)
    else:
        logger.warning("No Treasury data found")
        results["treasury"] = None
    
    # Validate CES
    ces_files = list((data_dir / "bls_ces").glob("*.parquet"))
    if ces_files:
        latest_ces = max(ces_files, key=lambda p: p.stat().st_mtime)
        results["ces"] = validate_ces(latest_ces)
    else:
        logger.warning("No CES data found")
        results["ces"] = None
    
    # Summary
    logger.info("=" * 60)
    logger.info("VALIDATION SUMMARY")
    logger.info("=" * 60)
    
    for source, passed in results.items():
        if passed is None:
            logger.info(f"⊘ {source}: No data")
        elif passed:
            logger.info(f"✅ {source}: PASSED")
        else:
            logger.error(f"❌ {source}: FAILED")
    
    logger.info(f"Completed: {datetime.now()}")
    logger.info("=" * 60)
    
    # Exit with error if any validations failed
    if any(v == False for v in results.values()):
        sys.exit(1)
    
    sys.exit(0)


if __name__ == "__main__":
    main()

