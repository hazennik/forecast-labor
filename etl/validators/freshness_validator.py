"""
Freshness Validator
Validates data freshness and timeliness
"""

from datetime import datetime, timedelta, date
from typing import Optional

import pandas as pd
from loguru import logger

from .base_validator import (
    BaseValidator,
    ValidationRule,
    ValidationResult,
    ValidationStatus,
    ValidationSeverity
)


class FreshnessValidator(BaseValidator):
    """
    Validates data freshness and timeliness
    """
    
    def __init__(
        self,
        source_name: str,
        date_column: str,
        max_age_days: int = 7,
        expected_frequency: str = "daily"
    ):
        """
        Initialize freshness validator
        
        Args:
            source_name: Name of data source
            date_column: Column containing dates
            max_age_days: Maximum allowed age of most recent data
            expected_frequency: Expected update frequency (daily, weekly, monthly)
        """
        self.date_column = date_column
        self.max_age_days = max_age_days
        self.expected_frequency = expected_frequency
        super().__init__(source_name)
    
    def _setup_rules(self):
        """Setup freshness validation rules"""
        
        # Rule 1: Date column exists
        self.add_rule(ValidationRule(
            name="date_column_exists",
            description=f"Date column '{self.date_column}' must exist",
            severity=ValidationSeverity.CRITICAL,
            check_function=self._check_date_column_exists
        ))
        
        # Rule 2: Most recent data is not too old
        self.add_rule(ValidationRule(
            name="data_not_stale",
            description=f"Most recent data must be within {self.max_age_days} days",
            severity=ValidationSeverity.ERROR,
            check_function=self._check_data_not_stale
        ))
        
        # Rule 3: Data has reasonable temporal coverage
        self.add_rule(ValidationRule(
            name="temporal_coverage",
            description="Data should have reasonable temporal coverage",
            severity=ValidationSeverity.WARNING,
            check_function=self._check_temporal_coverage
        ))
    
    def _check_date_column_exists(self, df: pd.DataFrame) -> ValidationResult:
        """Check if date column exists"""
        if self.date_column not in df.columns:
            return ValidationResult(
                rule_name="date_column_exists",
                status=ValidationStatus.FAILED,
                severity=ValidationSeverity.CRITICAL,
                message=f"Date column '{self.date_column}' not found",
                details={"available_columns": list(df.columns)}
            )
        
        return ValidationResult(
            rule_name="date_column_exists",
            status=ValidationStatus.PASSED,
            severity=ValidationSeverity.CRITICAL,
            message=f"Date column '{self.date_column}' exists",
            details={"date_column": self.date_column}
        )
    
    def _check_data_not_stale(self, df: pd.DataFrame) -> ValidationResult:
        """Check if data is fresh (not too old)"""
        if self.date_column not in df.columns:
            return ValidationResult(
                rule_name="data_not_stale",
                status=ValidationStatus.SKIPPED,
                severity=ValidationSeverity.ERROR,
                message=f"Cannot check freshness: date column missing"
            )
        
        try:
            # Convert to datetime
            dates = pd.to_datetime(df[self.date_column], errors="coerce")
            
            # Get most recent non-null date
            most_recent = dates.max()
            
            if pd.isna(most_recent):
                return ValidationResult(
                    rule_name="data_not_stale",
                    status=ValidationStatus.FAILED,
                    severity=ValidationSeverity.ERROR,
                    message="No valid dates found in date column",
                    details={"date_column": self.date_column}
                )
            
            # Calculate age
            now = datetime.now()
            if isinstance(most_recent, pd.Timestamp):
                most_recent = most_recent.to_pydatetime()
            
            age_days = (now - most_recent).days
            
            if age_days > self.max_age_days:
                return ValidationResult(
                    rule_name="data_not_stale",
                    status=ValidationStatus.FAILED,
                    severity=ValidationSeverity.ERROR,
                    message=f"Data is stale: {age_days} days old (max: {self.max_age_days})",
                    details={
                        "most_recent_date": most_recent.isoformat(),
                        "age_days": age_days,
                        "max_age_days": self.max_age_days
                    }
                )
            
            return ValidationResult(
                rule_name="data_not_stale",
                status=ValidationStatus.PASSED,
                severity=ValidationSeverity.ERROR,
                message=f"Data is fresh: {age_days} days old",
                details={
                    "most_recent_date": most_recent.isoformat(),
                    "age_days": age_days
                }
            )
            
        except Exception as e:
            return ValidationResult(
                rule_name="data_not_stale",
                status=ValidationStatus.FAILED,
                severity=ValidationSeverity.ERROR,
                message=f"Error checking freshness: {str(e)}",
                details={"exception": str(e)}
            )
    
    def _check_temporal_coverage(self, df: pd.DataFrame) -> ValidationResult:
        """Check temporal coverage of data"""
        if self.date_column not in df.columns:
            return ValidationResult(
                rule_name="temporal_coverage",
                status=ValidationStatus.SKIPPED,
                severity=ValidationSeverity.WARNING,
                message="Cannot check coverage: date column missing"
            )
        
        try:
            dates = pd.to_datetime(df[self.date_column], errors="coerce").dropna()
            
            if len(dates) == 0:
                return ValidationResult(
                    rule_name="temporal_coverage",
                    status=ValidationStatus.WARNING,
                    severity=ValidationSeverity.WARNING,
                    message="No valid dates found",
                    details={}
                )
            
            min_date = dates.min()
            max_date = dates.max()
            span_days = (max_date - min_date).days
            
            # Expected minimum span based on frequency
            expected_spans = {
                "daily": 30,      # At least 30 days
                "weekly": 90,     # At least 90 days
                "monthly": 365    # At least 1 year
            }
            
            expected_span = expected_spans.get(self.expected_frequency, 30)
            
            if span_days < expected_span:
                return ValidationResult(
                    rule_name="temporal_coverage",
                    status=ValidationStatus.WARNING,
                    severity=ValidationSeverity.WARNING,
                    message=f"Limited temporal coverage: {span_days} days",
                    details={
                        "min_date": min_date.isoformat(),
                        "max_date": max_date.isoformat(),
                        "span_days": span_days,
                        "expected_min_span": expected_span
                    }
                )
            
            return ValidationResult(
                rule_name="temporal_coverage",
                status=ValidationStatus.PASSED,
                severity=ValidationSeverity.WARNING,
                message=f"Good temporal coverage: {span_days} days",
                details={
                    "min_date": min_date.isoformat(),
                    "max_date": max_date.isoformat(),
                    "span_days": span_days,
                    "row_count": len(dates)
                }
            )
            
        except Exception as e:
            return ValidationResult(
                rule_name="temporal_coverage",
                status=ValidationStatus.WARNING,
                severity=ValidationSeverity.WARNING,
                message=f"Error checking coverage: {str(e)}",
                details={"exception": str(e)}
            )

