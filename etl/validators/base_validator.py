"""
Base Validator Classes
Abstract foundation for all data validation
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Callable

import pandas as pd
from loguru import logger


class ValidationStatus(str, Enum):
    """Validation result status"""
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"


class ValidationSeverity(str, Enum):
    """Validation rule severity"""
    CRITICAL = "critical"  # Must pass, blocks pipeline
    ERROR = "error"        # Should pass, logged as error
    WARNING = "warning"    # Nice to pass, logged as warning
    INFO = "info"          # Informational only


@dataclass
class ValidationResult:
    """Result of a validation check"""
    rule_name: str
    status: ValidationStatus
    severity: ValidationSeverity
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    
    def is_blocking(self) -> bool:
        """Check if this result should block the pipeline"""
        return self.severity == ValidationSeverity.CRITICAL and self.status == ValidationStatus.FAILED
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "rule_name": self.rule_name,
            "status": self.status.value,
            "severity": self.severity.value,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class ValidationRule:
    """Definition of a validation rule"""
    name: str
    description: str
    severity: ValidationSeverity
    check_function: Callable[[pd.DataFrame], ValidationResult]
    enabled: bool = True
    
    def execute(self, df: pd.DataFrame) -> ValidationResult:
        """Execute the validation rule"""
        if not self.enabled:
            return ValidationResult(
                rule_name=self.name,
                status=ValidationStatus.SKIPPED,
                severity=self.severity,
                message=f"Rule '{self.name}' is disabled"
            )
        
        try:
            result = self.check_function(df)
            return result
        except Exception as e:
            logger.error(f"Error executing rule '{self.name}': {e}")
            return ValidationResult(
                rule_name=self.name,
                status=ValidationStatus.FAILED,
                severity=self.severity,
                message=f"Validation failed with exception: {str(e)}",
                details={"exception": str(e)}
            )


class BaseValidator(ABC):
    """
    Abstract base class for all validators
    
    Provides framework for validation rules and result aggregation
    """
    
    def __init__(self, source_name: str):
        """
        Initialize validator
        
        Args:
            source_name: Name of data source being validated
        """
        self.source_name = source_name
        self.rules: List[ValidationRule] = []
        self._setup_rules()
    
    @abstractmethod
    def _setup_rules(self):
        """
        Setup validation rules
        Must be implemented by subclass
        """
        pass
    
    def add_rule(self, rule: ValidationRule):
        """
        Add a validation rule
        
        Args:
            rule: ValidationRule to add
        """
        self.rules.append(rule)
        logger.debug(f"Added validation rule: {rule.name} ({rule.severity.value})")
    
    def validate(self, df: pd.DataFrame) -> List[ValidationResult]:
        """
        Run all validation rules
        
        Args:
            df: DataFrame to validate
            
        Returns:
            List of validation results
        """
        logger.info(f"Running {len(self.rules)} validation rules for {self.source_name}")
        
        results = []
        
        for rule in self.rules:
            logger.debug(f"Executing rule: {rule.name}")
            result = rule.execute(df)
            results.append(result)
            
            # Log result
            if result.status == ValidationStatus.PASSED:
                logger.debug(f"✓ {rule.name}: {result.message}")
            elif result.status == ValidationStatus.WARNING:
                logger.warning(f"⚠ {rule.name}: {result.message}")
            elif result.status == ValidationStatus.FAILED:
                if result.severity == ValidationSeverity.CRITICAL:
                    logger.error(f"✗ CRITICAL: {rule.name}: {result.message}")
                else:
                    logger.error(f"✗ {rule.name}: {result.message}")
        
        return results
    
    def get_summary(self, results: List[ValidationResult]) -> Dict[str, Any]:
        """
        Get summary of validation results
        
        Args:
            results: List of validation results
            
        Returns:
            Summary dictionary
        """
        total = len(results)
        passed = sum(1 for r in results if r.status == ValidationStatus.PASSED)
        failed = sum(1 for r in results if r.status == ValidationStatus.FAILED)
        warnings = sum(1 for r in results if r.status == ValidationStatus.WARNING)
        skipped = sum(1 for r in results if r.status == ValidationStatus.SKIPPED)
        
        critical_failures = sum(
            1 for r in results 
            if r.status == ValidationStatus.FAILED and r.severity == ValidationSeverity.CRITICAL
        )
        
        summary = {
            "source_name": self.source_name,
            "total_rules": total,
            "passed": passed,
            "failed": failed,
            "warnings": warnings,
            "skipped": skipped,
            "critical_failures": critical_failures,
            "overall_status": self._get_overall_status(results),
            "timestamp": datetime.now().isoformat(),
        }
        
        return summary
    
    def _get_overall_status(self, results: List[ValidationResult]) -> str:
        """Determine overall validation status"""
        if any(r.is_blocking() for r in results):
            return "BLOCKED"
        elif any(r.status == ValidationStatus.FAILED for r in results):
            return "FAILED"
        elif any(r.status == ValidationStatus.WARNING for r in results):
            return "WARNING"
        else:
            return "PASSED"
    
    def should_block_pipeline(self, results: List[ValidationResult]) -> bool:
        """
        Check if validation results should block the pipeline
        
        Args:
            results: List of validation results
            
        Returns:
            bool: True if pipeline should be blocked
        """
        return any(r.is_blocking() for r in results)
    
    def log_summary(self, results: List[ValidationResult]):
        """
        Log validation summary
        
        Args:
            results: List of validation results
        """
        summary = self.get_summary(results)
        
        logger.info("=" * 60)
        logger.info(f"Validation Summary: {self.source_name}")
        logger.info("=" * 60)
        logger.info(f"Total Rules: {summary['total_rules']}")
        logger.info(f"✓ Passed: {summary['passed']}")
        logger.info(f"✗ Failed: {summary['failed']}")
        logger.info(f"⚠ Warnings: {summary['warnings']}")
        logger.info(f"⊘ Skipped: {summary['skipped']}")
        
        if summary['critical_failures'] > 0:
            logger.error(f"🚫 CRITICAL FAILURES: {summary['critical_failures']}")
            logger.error("Pipeline execution BLOCKED")
        
        logger.info(f"Overall Status: {summary['overall_status']}")
        logger.info("=" * 60)


# Common validation check functions

def check_not_empty(df: pd.DataFrame, rule_name: str = "not_empty") -> ValidationResult:
    """Check if DataFrame is not empty"""
    if df.empty:
        return ValidationResult(
            rule_name=rule_name,
            status=ValidationStatus.FAILED,
            severity=ValidationSeverity.CRITICAL,
            message="DataFrame is empty",
            details={"row_count": 0}
        )
    
    return ValidationResult(
        rule_name=rule_name,
        status=ValidationStatus.PASSED,
        severity=ValidationSeverity.CRITICAL,
        message=f"DataFrame contains {len(df)} rows",
        details={"row_count": len(df)}
    )


def check_required_columns(
    df: pd.DataFrame,
    required_columns: List[str],
    rule_name: str = "required_columns"
) -> ValidationResult:
    """Check if required columns exist"""
    missing = [col for col in required_columns if col not in df.columns]
    
    if missing:
        return ValidationResult(
            rule_name=rule_name,
            status=ValidationStatus.FAILED,
            severity=ValidationSeverity.CRITICAL,
            message=f"Missing required columns: {', '.join(missing)}",
            details={"missing_columns": missing, "found_columns": list(df.columns)}
        )
    
    return ValidationResult(
        rule_name=rule_name,
        status=ValidationStatus.PASSED,
        severity=ValidationSeverity.CRITICAL,
        message="All required columns present",
        details={"required_columns": required_columns}
    )


def check_no_nulls(
    df: pd.DataFrame,
    columns: List[str],
    rule_name: str = "no_nulls"
) -> ValidationResult:
    """Check if specified columns have no null values"""
    null_counts = {}
    
    for col in columns:
        if col in df.columns:
            null_count = df[col].isnull().sum()
            if null_count > 0:
                null_counts[col] = null_count
    
    if null_counts:
        total_nulls = sum(null_counts.values())
        return ValidationResult(
            rule_name=rule_name,
            status=ValidationStatus.FAILED,
            severity=ValidationSeverity.ERROR,
            message=f"Found {total_nulls} null values in critical columns",
            details={"null_counts": null_counts}
        )
    
    return ValidationResult(
        rule_name=rule_name,
        status=ValidationStatus.PASSED,
        severity=ValidationSeverity.ERROR,
        message="No null values in critical columns",
        details={"checked_columns": columns}
    )


def check_unique_key(
    df: pd.DataFrame,
    key_columns: List[str],
    rule_name: str = "unique_key"
) -> ValidationResult:
    """Check if key columns form a unique identifier"""
    if not all(col in df.columns for col in key_columns):
        return ValidationResult(
            rule_name=rule_name,
            status=ValidationStatus.FAILED,
            severity=ValidationSeverity.CRITICAL,
            message=f"Key columns not found: {key_columns}",
            details={"key_columns": key_columns}
        )
    
    duplicates = df.duplicated(subset=key_columns).sum()
    
    if duplicates > 0:
        return ValidationResult(
            rule_name=rule_name,
            status=ValidationStatus.FAILED,
            severity=ValidationSeverity.ERROR,
            message=f"Found {duplicates} duplicate rows based on key columns",
            details={"duplicate_count": duplicates, "key_columns": key_columns}
        )
    
    return ValidationResult(
        rule_name=rule_name,
        status=ValidationStatus.PASSED,
        severity=ValidationSeverity.ERROR,
        message="All rows have unique keys",
        details={"key_columns": key_columns, "row_count": len(df)}
    )

