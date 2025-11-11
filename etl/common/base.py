"""
Base ETL Classes
Abstract base classes for all data ingestion pipelines
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd
from loguru import logger
from pydantic import BaseModel, Field


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
    
    def _setup_logging(self):
        """Configure logging for this ETL pipeline"""
        logger.add(
            f"logs/etl/{self.config.source_name}_{{time}}.log",
            rotation="1 day",
            retention="30 days",
            level="INFO"
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
    
    def save_raw(self, df: pd.DataFrame) -> Path:
        """
        Save raw data to local storage
        
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
        
        # Save as Parquet
        df.to_parquet(filepath, compression="snappy", index=False)
        
        self.metadata.file_path = str(filepath)
        self.metadata.file_size_bytes = filepath.stat().st_size
        self.metadata.row_count = len(df)
        
        logger.info(f"Saved raw data: {filepath} ({len(df)} rows)")
        
        return filepath
    
    def create_vintage(self, df: pd.DataFrame, vintage_date: Optional[datetime] = None) -> Path:
        """
        Create immutable vintage snapshot
        
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
        vintage_dir = self.config.vintage_path / self.config.source_name / vintage_date.strftime("%Y-%m-%d")
        vintage_dir.mkdir(parents=True, exist_ok=True)
        
        filename = f"{self.config.source_name}_vintage.parquet"
        filepath = vintage_dir / filename
        
        # Check if vintage already exists
        if filepath.exists():
            logger.warning(f"Vintage already exists: {filepath}")
            return filepath
        
        # Save vintage (immutable)
        df.to_parquet(filepath, compression="snappy", index=False)
        
        logger.info(f"Created vintage: {filepath}")
        
        return filepath
    
    def log_ingestion(self, status: IngestionStatus = IngestionStatus.SUCCESS, 
                     error_message: Optional[str] = None):
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
            
            # Validate
            if self.config.validate_schema:
                logger.info("Validating data...")
                if not self.validate(df):
                    raise ValueError("Validation failed")
                logger.info("Validation passed")
            
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

