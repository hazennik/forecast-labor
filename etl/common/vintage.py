"""
Vintage Manager
Manages immutable historical data snapshots for vintage-honest backtesting
"""

from datetime import datetime, date
from pathlib import Path
from typing import Optional, List

import pandas as pd
from loguru import logger


class VintageError(Exception):
    """Raised when vintage operations fail"""
    pass


class VintageManager:
    """
    Manages vintage snapshots of data
    
    Key principles:
    - Vintages are IMMUTABLE (never overwrite)
    - One vintage per release date
    - Organized by source and date
    """
    
    def __init__(self, base_path: Path):
        """
        Initialize vintage manager
        
        Args:
            base_path: Base directory for vintages (e.g., /data/vintages)
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Vintage manager initialized: {self.base_path}")
    
    def create_vintage(
        self,
        source_name: str,
        data: pd.DataFrame,
        vintage_date: Optional[date] = None,
        allow_overwrite: bool = False
    ) -> Path:
        """
        Create vintage snapshot
        
        Args:
            source_name: Name of data source
            data: DataFrame to snapshot
            vintage_date: Date for this vintage (default: today)
            allow_overwrite: Allow overwriting existing vintage (USE WITH CAUTION)
            
        Returns:
            Path: Path to vintage file
            
        Raises:
            VintageError: If vintage already exists and overwrite not allowed
        """
        if data.empty:
            raise VintageError("Cannot create vintage from empty DataFrame")
        
        vintage_date = vintage_date or date.today()
        
        # Directory structure: {base}/source_name/YYYY-MM-DD/
        vintage_dir = self.base_path / source_name / vintage_date.strftime("%Y-%m-%d")
        vintage_dir.mkdir(parents=True, exist_ok=True)
        
        vintage_file = vintage_dir / f"{source_name}_vintage.parquet"
        
        # Check if vintage already exists
        if vintage_file.exists() and not allow_overwrite:
            logger.warning(f"Vintage already exists: {vintage_file}")
            raise VintageError(
                f"Vintage already exists for {source_name} on {vintage_date}. "
                "Set allow_overwrite=True to overwrite (not recommended)."
            )
        
        # Save vintage
        data.to_parquet(vintage_file, compression="snappy", index=False)
        
        # Make read-only (Unix only)
        try:
            vintage_file.chmod(0o444)
        except Exception:
            pass  # Windows doesn't support chmod
        
        logger.info(f"Created vintage: {vintage_file} ({len(data)} rows)")
        
        return vintage_file
    
    def load_vintage(
        self,
        source_name: str,
        vintage_date: date
    ) -> pd.DataFrame:
        """
        Load vintage snapshot
        
        Args:
            source_name: Name of data source
            vintage_date: Vintage date to load
            
        Returns:
            pd.DataFrame: Vintage data
            
        Raises:
            VintageError: If vintage not found
        """
        vintage_file = (
            self.base_path / 
            source_name / 
            vintage_date.strftime("%Y-%m-%d") / 
            f"{source_name}_vintage.parquet"
        )
        
        if not vintage_file.exists():
            raise VintageError(
                f"Vintage not found: {source_name} on {vintage_date}"
            )
        
        data = pd.read_parquet(vintage_file)
        
        logger.info(f"Loaded vintage: {vintage_file} ({len(data)} rows)")
        
        return data
    
    def list_vintages(self, source_name: str) -> List[date]:
        """
        List all available vintage dates for a source
        
        Args:
            source_name: Name of data source
            
        Returns:
            list: List of vintage dates (sorted oldest to newest)
        """
        source_dir = self.base_path / source_name
        
        if not source_dir.exists():
            logger.warning(f"No vintages found for: {source_name}")
            return []
        
        vintages = []
        for vintage_dir in source_dir.iterdir():
            if vintage_dir.is_dir():
                try:
                    vintage_date = datetime.strptime(vintage_dir.name, "%Y-%m-%d").date()
                    vintages.append(vintage_date)
                except ValueError:
                    logger.warning(f"Invalid vintage directory name: {vintage_dir.name}")
        
        vintages.sort()
        
        logger.info(f"Found {len(vintages)} vintages for {source_name}")
        
        return vintages
    
    def get_latest_vintage(self, source_name: str) -> Optional[pd.DataFrame]:
        """
        Get most recent vintage for a source
        
        Args:
            source_name: Name of data source
            
        Returns:
            pd.DataFrame: Latest vintage data, or None if no vintages
        """
        vintages = self.list_vintages(source_name)
        
        if not vintages:
            logger.warning(f"No vintages available for {source_name}")
            return None
        
        latest_date = vintages[-1]
        return self.load_vintage(source_name, latest_date)
    
    def vintage_exists(self, source_name: str, vintage_date: date) -> bool:
        """
        Check if vintage exists
        
        Args:
            source_name: Name of data source
            vintage_date: Vintage date to check
            
        Returns:
            bool: True if vintage exists
        """
        vintage_file = (
            self.base_path / 
            source_name / 
            vintage_date.strftime("%Y-%m-%d") / 
            f"{source_name}_vintage.parquet"
        )
        
        return vintage_file.exists()
    
    def get_vintage_as_of(
        self,
        source_name: str,
        as_of_date: date
    ) -> Optional[pd.DataFrame]:
        """
        Get the vintage that would have been available as of a specific date
        (For vintage-honest backtesting)
        
        Args:
            source_name: Name of data source
            as_of_date: Date to check what was available
            
        Returns:
            pd.DataFrame: Latest vintage available on or before as_of_date
        """
        vintages = self.list_vintages(source_name)
        
        # Filter to vintages on or before as_of_date
        available_vintages = [v for v in vintages if v <= as_of_date]
        
        if not available_vintages:
            logger.warning(
                f"No vintages available for {source_name} on or before {as_of_date}"
            )
            return None
        
        # Get the latest available vintage
        latest_available = available_vintages[-1]
        
        logger.info(
            f"Using vintage from {latest_available} for as_of_date {as_of_date}"
        )
        
        return self.load_vintage(source_name, latest_available)

