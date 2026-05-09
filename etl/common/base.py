"""
Base ETL Classes
Abstract base classes for all data ingestion pipelines
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional, List

import pandas as pd
from loguru import logger
from pydantic import BaseModel, Field

# Import for validation framework integration
from etl.validators.base_validator import ValidationSeverity


class DataSource(str, Enum):
    """Supported data sources"""

    BLS_CES = "bls_ces"
    BLS_LAUS = "bls_laus"
    UI_CLAIMS = "ui_claims"
    TREASURY_WITHHOLDINGS = "treasury_withholdings"
    STRIKES = "strikes"
    WEATHER = "weather"
    CNBFS = "cnbfs"
    HOMEBASE = "homebase"
    LIGHTCAST = "lightcast"
    UKG = "ukg"


class IngestionStatus(str, Enum):
    """Ingestion status codes"""

    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"
    SKIPPED = "skipped"


class IngestionMetadata(BaseModel):
    """Metadata for data ingestion runs"""

    source_name: str
    ingestion_timestamp: datetime = Field(default_factory=datetime.now)
    vintage_date: Optional[datetime] = None
    row_count: int = 0
    status: IngestionStatus = IngestionStatus.SUCCESS
    error_message: Optional[str] = None
    file_path: Optional[str] = None
    file_size_bytes: Optional[int] = None
    checksum: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


@dataclass
class ETLConfig:
    """Configuration for ETL pipeline"""

    source_name: str
    raw_data_path: Path
    vintage_path: Path
    frequency: str  # daily, weekly, monthly
    retention_days: int = 3650  # 10 years default
    validate_schema: bool = True
    create_vintage: bool = True
    # Validation framework integration
    enable_validators: bool = False  # Use validation framework
    validators: List[Any] = field(default_factory=list)  # List of validator instances
    generate_validation_reports: bool = False  # Generate HTML/PDF reports
    fail_on_validation_error: bool = False  # Halt pipeline on critical validation failures
    # Storage integration (MinIO/S3)
    upload_to_storage: bool = True  # Upload to MinIO for downstream processes
    storage_bucket: str = "data"  # MinIO bucket name


class BaseETL(ABC):
    """
    Abstract base class for all ETL pipelines

    Provides common functionality:
    - Download/fetch data
    - Validate schema and data quality
    - Save raw data
    - Create vintage snapshots
    - Log ingestion metadata
    """

    def __init__(self, config: ETLConfig):
        self.config = config
        self.metadata = IngestionMetadata(source_name=config.source_name)
        self._setup_logging()

        # Initialize storage client if uploads enabled
        self.storage_client = None
        if self.config.upload_to_storage:
            from etl.common.storage import StorageClient

            try:
                self.storage_client = StorageClient()
                logger.debug("StorageClient initialized for data uploads")
            except Exception as e:
                logger.warning(f"Failed to initialize StorageClient: {e}")
                logger.warning("Data will only be saved locally")
                self.config.upload_to_storage = False

    def _setup_logging(self):
        """Configure logging for this ETL pipeline"""
        logger.add(
            f"logs/etl/{self.config.source_name}_{{time}}.log",
            rotation="1 day",
            retention="30 days",
            level="INFO",
        )

    @abstractmethod
    def extract(self) -> pd.DataFrame:
        """
        Extract data from source
        Must be implemented by subclass

        Returns:
            pd.DataFrame: Raw data
        """
        pass

    @abstractmethod
    def validate(self, df: pd.DataFrame) -> bool:
        """
        Validate data schema and quality
        Must be implemented by subclass

        Args:
            df: DataFrame to validate

        Returns:
            bool: True if validation passes
        """
        pass

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Optional transformation before saving
        Override if needed

        Args:
            df: Raw DataFrame

        Returns:
            pd.DataFrame: Transformed DataFrame
        """
        return df

    def run_validators(self, df: pd.DataFrame) -> tuple[List[Any], bool]:
        """
        Run validation framework validators

        Args:
            df: DataFrame to validate

        Returns:
            tuple: (list of validation results, overall pass/fail)
        """
        if not self.config.enable_validators or not self.config.validators:
            return [], True

        logger.info(f"Running {len(self.config.validators)} validators...")

        all_results = []
        has_critical_failure = False

        for validator in self.config.validators:
            try:
                results = validator.validate(df)
                all_results.extend(results)

                # Check for critical failures
                for result in results:
                    if not result.passed and result.severity == ValidationSeverity.CRITICAL:
                        has_critical_failure = True
                        logger.error(f"CRITICAL validation failure: {result.message}")
                    elif not result.passed and result.severity == ValidationSeverity.ERROR:
                        logger.warning(f"ERROR validation failure: {result.message}")

            except Exception as e:
                logger.error(f"Validator {validator.__class__.__name__} failed: {e}")

        # Summary
        total = len(all_results)
        passed = sum(1 for r in all_results if r.passed)
        failed = total - passed

        logger.info(f"Validation complete: {passed}/{total} checks passed, {failed} failed")

        # Generate report if configured
        if self.config.generate_validation_reports and all_results:
            self._generate_validation_report(all_results)

        # Determine overall pass/fail
        if self.config.fail_on_validation_error and has_critical_failure:
            return all_results, False

        return all_results, True

    def _generate_validation_report(self, results: List[Any]):
        """
        Generate validation report

        Args:
            results: Validation results
        """
        try:
            from etl.validators.report_generator import ValidationReportGenerator

            generator = ValidationReportGenerator()
            report_title = f"Validation Report: {self.config.source_name}"

            html_path = generator.generate_html_report(results, title=report_title)
            logger.info(f"Validation report generated: {html_path}")

        except Exception as e:
            logger.error(f"Failed to generate validation report: {e}")

    def save_raw(self, df: pd.DataFrame) -> Path:
        """
        Save raw data to local storage and optionally upload to MinIO

        Args:
            df: DataFrame to save

        Returns:
            Path: Path to saved file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.config.source_name}_{timestamp}.parquet"
        filepath = self.config.raw_data_path / filename

        # Ensure directory exists
        filepath.parent.mkdir(parents=True, exist_ok=True)

        # Save as Parquet locally
        df.to_parquet(filepath, compression="snappy", index=False)

        self.metadata.file_path = str(filepath)
        self.metadata.file_size_bytes = filepath.stat().st_size
        self.metadata.row_count = len(df)

        logger.info(f"Saved raw data: {filepath} ({len(df)} rows)")

        # Upload to MinIO if enabled
        if self.config.upload_to_storage and self.storage_client:
            try:
                object_path = f"raw/{self.config.source_name}/{filename}"
                self.storage_client.upload_file(
                    bucket_name=self.config.storage_bucket,
                    object_name=object_path,
                    file_path=filepath,
                )
                logger.info(f"Uploaded to MinIO: {self.config.storage_bucket}/{object_path}")
            except Exception as e:
                logger.warning(f"Failed to upload raw data to MinIO: {e}")

        return filepath

    def create_vintage(self, df: pd.DataFrame, vintage_date: Optional[datetime] = None) -> Path:
        """
        Create immutable vintage snapshot and optionally upload to MinIO

        Args:
            df: DataFrame to snapshot
            vintage_date: Date for this vintage (default: today)

        Returns:
            Path: Path to vintage snapshot
        """
        if not self.config.create_vintage:
            return None

        vintage_date = vintage_date or datetime.now()
        self.metadata.vintage_date = vintage_date

        # Vintage directory structure: vintages/{source}/{YYYY-MM-DD}/
        vintage_dir = (
            self.config.vintage_path / self.config.source_name / vintage_date.strftime("%Y-%m-%d")
        )
        vintage_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{self.config.source_name}_vintage.parquet"
        filepath = vintage_dir / filename

        # Check if vintage already exists
        if filepath.exists():
            logger.warning(f"Vintage already exists: {filepath}")
            return filepath

        # Add provenance metadata to identify production data
        # CRITICAL: This metadata distinguishes production from synthetic test data
        df.attrs["is_synthetic"] = False
        df.attrs["generated_by"] = f"etl.{self.config.source_name}"
        df.attrs["generation_date"] = datetime.now().isoformat()
        df.attrs["purpose"] = "Production ETL output"
        df.attrs["source_name"] = self.config.source_name
        df.attrs["vintage_date"] = vintage_date.isoformat()

        # Save vintage (immutable) locally (attrs are preserved in parquet format)
        df.to_parquet(filepath, compression="snappy", index=False)

        logger.info(f"Created vintage: {filepath}")
        logger.info("  🏷️  Tagged as PRODUCTION (is_synthetic=False)")

        # Upload to MinIO if enabled
        if self.config.upload_to_storage and self.storage_client:
            try:
                object_path = f"vintages/{self.config.source_name}/{vintage_date.strftime('%Y-%m-%d')}/{filename}"
                self.storage_client.upload_file(
                    bucket_name=self.config.storage_bucket,
                    object_name=object_path,
                    file_path=filepath,
                )
                logger.info(
                    f"Uploaded vintage to MinIO: {self.config.storage_bucket}/{object_path}"
                )
            except Exception as e:
                logger.warning(f"Failed to upload vintage to MinIO: {e}")

        return filepath

    def log_ingestion(
        self, status: IngestionStatus = IngestionStatus.SUCCESS, error_message: Optional[str] = None
    ):
        """
        Log ingestion metadata to database

        Args:
            status: Ingestion status
            error_message: Error message if failed
        """
        self.metadata.status = status
        self.metadata.error_message = error_message

        # TODO: Write to database (logs.ingestion_log table)
        # For now, just log
        logger.info(f"Ingestion {status.value}: {self.config.source_name}")
        if error_message:
            logger.error(f"Error: {error_message}")

    def run(self) -> bool:
        """
        Execute full ETL pipeline

        Returns:
            bool: True if successful
        """
        try:
            logger.info(f"Starting ETL: {self.config.source_name}")

            # Extract
            logger.info("Extracting data...")
            df = self.extract()

            if df is None or df.empty:
                raise ValueError("No data extracted")

            logger.info(f"Extracted {len(df)} rows")

            # Validate (basic schema check)
            if self.config.validate_schema:
                logger.info("Validating data...")
                if not self.validate(df):
                    raise ValueError("Validation failed")
                logger.info("Validation passed")

            # Run validation framework validators (if enabled)
            if self.config.enable_validators:
                validation_results, validation_passed = self.run_validators(df)
                if not validation_passed:
                    raise ValueError(
                        f"Validation framework failed: {len([r for r in validation_results if not r.passed])} critical failures"
                    )

            # Transform (optional)
            logger.info("Transforming data...")
            df = self.transform(df)

            # Save raw
            logger.info("Saving raw data...")
            self.save_raw(df)

            # Create vintage
            if self.config.create_vintage:
                logger.info("Creating vintage snapshot...")
                self.create_vintage(df)

            # Log success
            self.log_ingestion(IngestionStatus.SUCCESS)

            logger.info(f"✅ ETL complete: {self.config.source_name}")
            return True

        except Exception as e:
            logger.error(f"❌ ETL failed: {self.config.source_name}")
            logger.exception(e)
            self.log_ingestion(IngestionStatus.FAILED, str(e))
            return False
