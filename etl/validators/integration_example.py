"""
Validation Framework Integration Example
Shows how to integrate validators with ETL pipelines
"""

from pathlib import Path

from etl.common.base import ETLConfig
from etl.validators.schema_validator import SchemaValidator, SchemaRule
from etl.validators.freshness_validator import FreshnessValidator
from etl.validators.quality_validator import QualityValidator, QualityRule


def create_validated_etl_config(
    source_name: str,
    required_columns: list[str],
    max_age_days: int = 2,
    max_missing_pct: float = 5.0,
    enable_reports: bool = True,
    fail_on_critical: bool = True,
) -> ETLConfig:
    """
    Create ETL config with validation framework enabled

    Args:
        source_name: Data source name
        required_columns: List of required column names
        max_age_days: Maximum data age in days
        max_missing_pct: Maximum missing value percentage
        enable_reports: Generate HTML validation reports
        fail_on_critical: Halt pipeline on critical failures

    Returns:
        ETLConfig with validators configured
    """

    # Define schema rules
    schema_rules = [SchemaRule(column_name=col, required=True) for col in required_columns]

    # Add date column if needed
    if "date" not in required_columns:
        schema_rules.append(
            SchemaRule(
                column_name="date", required=True, data_type="datetime64[ns]", nullable=False
            )
        )

    # Create validators
    schema_validator = SchemaValidator(name=f"{source_name}_schema", schema_rules=schema_rules)

    freshness_validator = FreshnessValidator(
        name=f"{source_name}_freshness", date_column="date", max_age_days=max_age_days
    )

    quality_rules = [
        QualityRule(
            check_name="missing_values", check_type="missing_values", threshold=max_missing_pct
        ),
        QualityRule(
            check_name="duplicates", check_type="duplicates", threshold=0.0  # No duplicates allowed
        ),
    ]

    quality_validator = QualityValidator(name=f"{source_name}_quality", quality_rules=quality_rules)

    # Create config
    config = ETLConfig(
        source_name=source_name,
        raw_data_path=Path("data/raw") / source_name,
        vintage_path=Path("data/vintages"),
        frequency="daily",  # or weekly/monthly
        validate_schema=True,
        create_vintage=True,
        # Validation framework
        enable_validators=True,
        validators=[schema_validator, freshness_validator, quality_validator],
        generate_validation_reports=enable_reports,
        fail_on_validation_error=fail_on_critical,
    )

    return config


def create_monthly_series_config(
    source_name: str, series_columns: list[str], enable_reports: bool = True
) -> ETLConfig:
    """
    Create config for monthly time series data

    Args:
        source_name: Data source name
        series_columns: List of series column names (e.g., "value", "preliminary")
        enable_reports: Generate validation reports

    Returns:
        ETLConfig with monthly series validators
    """

    ["date", "series_id"] + series_columns

    # Schema rules
    schema_rules = [
        SchemaRule(column_name="date", required=True, data_type="datetime64[ns]", nullable=False),
        SchemaRule(
            column_name="series_id", required=True, data_type="object", nullable=False  # string
        ),
    ]

    # Add series columns
    for col in series_columns:
        schema_rules.append(
            SchemaRule(
                column_name=col,
                required=True,
                data_type="float64",
                nullable=True,  # Allow NaN for missing data
            )
        )

    # Create validators
    schema_validator = SchemaValidator(name=f"{source_name}_schema", schema_rules=schema_rules)

    # Freshness: monthly data can be up to 45 days old
    freshness_validator = FreshnessValidator(
        name=f"{source_name}_freshness", date_column="date", max_age_days=45
    )

    # Quality rules for time series
    quality_rules = [
        QualityRule(
            check_name="missing_values_moderate",
            check_type="missing_values",
            threshold=10.0,  # Allow up to 10% missing for monthly series
        ),
        QualityRule(check_name="no_duplicates", check_type="duplicates", threshold=0.0),
    ]

    quality_validator = QualityValidator(name=f"{source_name}_quality", quality_rules=quality_rules)

    config = ETLConfig(
        source_name=source_name,
        raw_data_path=Path("data/raw") / source_name,
        vintage_path=Path("data/vintages"),
        frequency="monthly",
        validate_schema=True,
        create_vintage=True,
        enable_validators=True,
        validators=[schema_validator, freshness_validator, quality_validator],
        generate_validation_reports=enable_reports,
        fail_on_validation_error=False,  # Don't halt for monthly data issues
    )

    return config


# Example usage for specific data sources


def get_claims_config() -> ETLConfig:
    """Get config for UI Claims data"""
    return create_validated_etl_config(
        source_name="claims",
        required_columns=[
            "state",
            "initial_claims",
            "continuing_claims",
            "initial_claims_4wk",
        ],
        max_age_days=7,  # Weekly data
        max_missing_pct=2.0,  # Very strict
        enable_reports=True,
        fail_on_critical=True,
    )


def get_ces_config() -> ETLConfig:
    """Get config for BLS CES data"""
    return create_monthly_series_config(
        source_name="bls_ces", series_columns=["value", "preliminary"], enable_reports=True
    )


def get_treasury_config() -> ETLConfig:
    """Get config for Treasury Withholdings"""
    return create_validated_etl_config(
        source_name="treasury_withholdings",
        required_columns=[
            "date",
            "withheld",
            "mtd_withheld",
        ],
        max_age_days=3,  # Daily data - very fresh
        max_missing_pct=1.0,  # Very strict
        enable_reports=True,
        fail_on_critical=True,
    )


if __name__ == "__main__":
    # Example: Create configs
    claims_config = get_claims_config()
    print(f"Claims config: {len(claims_config.validators)} validators")

    ces_config = get_ces_config()
    print(f"CES config: {len(ces_config.validators)} validators")

    treasury_config = get_treasury_config()
    print(f"Treasury config: {len(treasury_config.validators)} validators")
