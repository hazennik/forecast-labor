"""
Quality Validator
Validates data quality (nulls, duplicates, outliers, ranges)
"""

from typing import Dict, List, Optional, Tuple

import pandas as pd
import numpy as np
from loguru import logger

from .base_validator import (
    BaseValidator,
    ValidationRule,
    ValidationResult,
    ValidationStatus,
    ValidationSeverity,
    check_no_nulls,
    check_unique_key
)


class QualityValidator(BaseValidator):
    """
    Validates data quality metrics
    """
    
    def __init__(
        self,
        source_name: str,
        critical_columns: List[str] = None,
        unique_keys: List[str] = None,
        numeric_ranges: Dict[str, Tuple[float, float]] = None
    ):
        """
        Initialize quality validator
        
        Args:
            source_name: Name of data source
            critical_columns: Columns that should not have nulls
            unique_keys: Columns that should form unique key
            numeric_ranges: Expected ranges for numeric columns {col: (min, max)}
        """
        self.critical_columns = critical_columns or []
        self.unique_keys = unique_keys or []
        self.numeric_ranges = numeric_ranges or {}
        super().__init__(source_name)
    
    def _setup_rules(self):
        """Setup quality validation rules"""
        
        # Rule 1: No nulls in critical columns
        if self.critical_columns:
            self.add_rule(ValidationRule(
                name="no_critical_nulls",
                description=f"Critical columns must not have nulls",
                severity=ValidationSeverity.ERROR,
                check_function=lambda df: check_no_nulls(
                    df, self.critical_columns, "no_critical_nulls"
                )
            ))
        
        # Rule 2: Unique key constraint
        if self.unique_keys:
            self.add_rule(ValidationRule(
                name="unique_keys",
                description=f"Key columns must form unique identifier",
                severity=ValidationSeverity.ERROR,
                check_function=lambda df: check_unique_key(
                    df, self.unique_keys, "unique_keys"
                )
            ))
        
        # Rule 3: Numeric ranges
        if self.numeric_ranges:
            self.add_rule(ValidationRule(
                name="numeric_ranges",
                description="Numeric values should be within expected ranges",
                severity=ValidationSeverity.WARNING,
                check_function=self._check_numeric_ranges
            ))
        
        # Rule 4: No excessive nulls in any column
        self.add_rule(ValidationRule(
            name="no_excessive_nulls",
            description="No column should be mostly null (>50%)",
            severity=ValidationSeverity.WARNING,
            check_function=self._check_no_excessive_nulls
        ))
        
        # Rule 5: Reasonable row count
        self.add_rule(ValidationRule(
            name="reasonable_row_count",
            description="Dataset should have reasonable number of rows",
            severity=ValidationSeverity.WARNING,
            check_function=self._check_reasonable_row_count
        ))
    
    def _check_numeric_ranges(self, df: pd.DataFrame) -> ValidationResult:
        """Check if numeric values are within expected ranges"""
        range_violations = {}
        
        for col, (min_val, max_val) in self.numeric_ranges.items():
            if col not in df.columns:
                continue
            
            # Convert to numeric, coercing errors
            values = pd.to_numeric(df[col], errors="coerce")
            
            # Check for values outside range
            below_min = (values < min_val).sum()
            above_max = (values > max_val).sum()
            
            if below_min > 0 or above_max > 0:
                range_violations[col] = {
                    "expected_range": (min_val, max_val),
                    "actual_range": (values.min(), values.max()),
                    "below_min_count": int(below_min),
                    "above_max_count": int(above_max)
                }
        
        if range_violations:
            total_violations = sum(
                v["below_min_count"] + v["above_max_count"] 
                for v in range_violations.values()
            )
            
            return ValidationResult(
                rule_name="numeric_ranges",
                status=ValidationStatus.WARNING,
                severity=ValidationSeverity.WARNING,
                message=f"Found {total_violations} values outside expected ranges",
                details={"range_violations": range_violations}
            )
        
        return ValidationResult(
            rule_name="numeric_ranges",
            status=ValidationStatus.PASSED,
            severity=ValidationSeverity.WARNING,
            message="All numeric values within expected ranges",
            details={"checked_columns": list(self.numeric_ranges.keys())}
        )
    
    def _check_no_excessive_nulls(self, df: pd.DataFrame) -> ValidationResult:
        """Check that no column is mostly null"""
        excessive_null_threshold = 0.5  # 50%
        excessive_null_columns = {}
        
        for col in df.columns:
            null_ratio = df[col].isnull().sum() / len(df)
            if null_ratio > excessive_null_threshold:
                excessive_null_columns[col] = {
                    "null_ratio": round(null_ratio, 3),
                    "null_count": int(df[col].isnull().sum()),
                    "total_count": len(df)
                }
        
        if excessive_null_columns:
            return ValidationResult(
                rule_name="no_excessive_nulls",
                status=ValidationStatus.WARNING,
                severity=ValidationSeverity.WARNING,
                message=f"Found {len(excessive_null_columns)} columns with >50% nulls",
                details={"excessive_null_columns": excessive_null_columns}
            )
        
        return ValidationResult(
            rule_name="no_excessive_nulls",
            status=ValidationStatus.PASSED,
            severity=ValidationSeverity.WARNING,
            message="No columns have excessive null values",
            details={"total_columns": len(df.columns)}
        )
    
    def _check_reasonable_row_count(self, df: pd.DataFrame) -> ValidationResult:
        """Check if dataset has reasonable number of rows"""
        row_count = len(df)
        
        # Thresholds (configurable)
        min_rows = 10
        warning_threshold = 5
        
        if row_count < warning_threshold:
            return ValidationResult(
                rule_name="reasonable_row_count",
                status=ValidationStatus.WARNING,
                severity=ValidationSeverity.WARNING,
                message=f"Very few rows: {row_count}",
                details={"row_count": row_count}
            )
        
        if row_count < min_rows:
            return ValidationResult(
                rule_name="reasonable_row_count",
                status=ValidationStatus.WARNING,
                severity=ValidationSeverity.WARNING,
                message=f"Low row count: {row_count}",
                details={"row_count": row_count}
            )
        
        return ValidationResult(
            rule_name="reasonable_row_count",
            status=ValidationStatus.PASSED,
            severity=ValidationSeverity.WARNING,
            message=f"Reasonable row count: {row_count}",
            details={"row_count": row_count}
        )


def detect_outliers(
    df: pd.DataFrame,
    column: str,
    method: str = "iqr",
    threshold: float = 3.0
) -> pd.Series:
    """
    Detect outliers in a numeric column
    
    Args:
        df: DataFrame
        column: Column name
        method: Detection method ("iqr" or "zscore")
        threshold: Threshold for outlier detection
        
    Returns:
        Boolean Series indicating outliers
    """
    values = pd.to_numeric(df[column], errors="coerce")
    
    if method == "iqr":
        Q1 = values.quantile(0.25)
        Q3 = values.quantile(0.75)
        IQR = Q3 - Q1
        lower_bound = Q1 - threshold * IQR
        upper_bound = Q3 + threshold * IQR
        return (values < lower_bound) | (values > upper_bound)
    
    elif method == "zscore":
        z_scores = np.abs((values - values.mean()) / values.std())
        return z_scores > threshold
    
    else:
        raise ValueError(f"Unknown outlier detection method: {method}")

