"""
Schema Validator
Validates DataFrame schema and data types
"""

from typing import Dict, Any, List

import pandas as pd
import numpy as np
from loguru import logger

from .base_validator import (
    BaseValidator,
    ValidationRule,
    ValidationResult,
    ValidationStatus,
    ValidationSeverity,
    check_required_columns,
    check_not_empty
)


class SchemaValidator(BaseValidator):
    """
    Validates DataFrame schema and data types
    """
    
    def __init__(
        self,
        source_name: str,
        required_columns: List[str],
        column_types: Dict[str, str] = None
    ):
        """
        Initialize schema validator
        
        Args:
            source_name: Name of data source
            required_columns: List of required column names
            column_types: Expected data types for columns
        """
        self.required_columns = required_columns
        self.column_types = column_types or {}
        super().__init__(source_name)
    
    def _setup_rules(self):
        """Setup schema validation rules"""
        
        # Rule 1: DataFrame not empty
        self.add_rule(ValidationRule(
            name="not_empty",
            description="DataFrame must contain at least one row",
            severity=ValidationSeverity.CRITICAL,
            check_function=lambda df: check_not_empty(df, "not_empty")
        ))
        
        # Rule 2: Required columns exist
        self.add_rule(ValidationRule(
            name="required_columns",
            description=f"Required columns: {', '.join(self.required_columns)}",
            severity=ValidationSeverity.CRITICAL,
            check_function=lambda df: check_required_columns(
                df, self.required_columns, "required_columns"
            )
        ))
        
        # Rule 3: Data types match expected
        if self.column_types:
            self.add_rule(ValidationRule(
                name="column_types",
                description="Column data types match expected types",
                severity=ValidationSeverity.ERROR,
                check_function=self._check_column_types
            ))
        
        # Rule 4: No completely empty columns
        self.add_rule(ValidationRule(
            name="no_empty_columns",
            description="No columns should be completely empty",
            severity=ValidationSeverity.WARNING,
            check_function=self._check_no_empty_columns
        ))
    
    def _check_column_types(self, df: pd.DataFrame) -> ValidationResult:
        """Check if column types match expected types"""
        type_mismatches = {}
        
        for col, expected_type in self.column_types.items():
            if col not in df.columns:
                continue
            
            actual_type = str(df[col].dtype)
            
            # Check type compatibility
            if not self._is_compatible_type(actual_type, expected_type):
                type_mismatches[col] = {
                    "expected": expected_type,
                    "actual": actual_type
                }
        
        if type_mismatches:
            return ValidationResult(
                rule_name="column_types",
                status=ValidationStatus.FAILED,
                severity=ValidationSeverity.ERROR,
                message=f"Found {len(type_mismatches)} column type mismatches",
                details={"type_mismatches": type_mismatches}
            )
        
        return ValidationResult(
            rule_name="column_types",
            status=ValidationStatus.PASSED,
            severity=ValidationSeverity.ERROR,
            message="All column types match expected types",
            details={"checked_columns": list(self.column_types.keys())}
        )
    
    def _is_compatible_type(self, actual: str, expected: str) -> bool:
        """Check if actual type is compatible with expected type"""
        # Normalize type strings
        actual = actual.lower()
        expected = expected.lower()
        
        # Define type compatibility groups
        numeric_types = ["int", "float", "number", "numeric"]
        string_types = ["str", "string", "object"]
        date_types = ["datetime", "date", "timestamp"]
        bool_types = ["bool", "boolean"]
        
        # Check if both are in same group
        for type_group in [numeric_types, string_types, date_types, bool_types]:
            if any(t in actual for t in type_group) and any(t in expected for t in type_group):
                return True
        
        return actual == expected
    
    def _check_no_empty_columns(self, df: pd.DataFrame) -> ValidationResult:
        """Check that no columns are completely empty"""
        empty_columns = []
        
        for col in df.columns:
            if df[col].isnull().all():
                empty_columns.append(col)
        
        if empty_columns:
            return ValidationResult(
                rule_name="no_empty_columns",
                status=ValidationStatus.WARNING,
                severity=ValidationSeverity.WARNING,
                message=f"Found {len(empty_columns)} completely empty columns",
                details={"empty_columns": empty_columns}
            )
        
        return ValidationResult(
            rule_name="no_empty_columns",
            status=ValidationStatus.PASSED,
            severity=ValidationSeverity.WARNING,
            message="No completely empty columns found",
            details={"total_columns": len(df.columns)}
        )

