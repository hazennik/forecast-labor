"""
Vintage Harness

Reconstructs historical data states for vintage-honest backtesting.
Ensures no data leakage by loading only data that would have been 
available at a specific point in time.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
from loguru import logger

from etl.common.vintage import VintageManager


# ============================================================================
# Exceptions
# ============================================================================


class VintageReconstructionError(Exception):
    """Raised when vintage reconstruction fails."""
    pass


# ============================================================================
# Data Structures
# ============================================================================


@dataclass
class ReconstructedState:
    """
    Represents a reconstructed historical state.
    
    Contains all data that would have been available at a specific date,
    with metadata about sources and vintage dates used.
    
    Attributes:
        as_of_date: Date for which state was reconstructed
        data: Dictionary mapping source names to their data DataFrames
        vintage_dates: Dictionary mapping source names to vintage dates used
        sources_requested: List of sources that were requested
        sources_available: List of sources that were successfully loaded
        metadata: Additional metadata about reconstruction
    """
    as_of_date: date
    data: Dict[str, pd.DataFrame]
    vintage_dates: Dict[str, date]
    sources_requested: List[str]
    sources_available: List[str]
    metadata: Dict[str, any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Populate metadata after initialization."""
        if not self.metadata:
            self.metadata = {
                'reconstruction_timestamp': datetime.now().isoformat(),
                'harness_version': '1.0.0',
            }


# ============================================================================
# Vintage Harness
# ============================================================================


class VintageHarness:
    """
    Reconstructs historical data states for vintage-honest backtesting.
    
    Key features:
    - Loads data from vintages that were available at specific dates
    - Validates vintage honesty (no future data leakage)
    - Handles missing data and edge cases
    - Provides consistent interface for backtesting
    
    Example:
        >>> harness = VintageHarness(Path("data/vintages"))
        >>> state = harness.reconstruct_state(
        ...     as_of_date=date(2024, 2, 15),
        ...     sources=["ces", "laus", "claims"]
        ... )
        >>> is_valid, errors = harness.validate_vintage_honesty(state)
    """
    
    def __init__(self, vintage_base_path: Path):
        """
        Initialize vintage harness.
        
        Args:
            vintage_base_path: Base directory for vintage data
        """
        self.vintage_base_path = Path(vintage_base_path)
        self.vintage_manager = VintageManager(self.vintage_base_path)
        
        logger.info(
            "VintageHarness initialized",
            vintage_path=str(self.vintage_base_path)
        )
    
    def reconstruct_state(
        self,
        as_of_date: date,
        sources: List[str],
        allow_partial: bool = False
    ) -> ReconstructedState:
        """
        Reconstruct historical data state as of a specific date.
        
        Loads the latest vintage for each source that was available
        on or before as_of_date, ensuring vintage honesty.
        
        Args:
            as_of_date: Date for which to reconstruct state
            sources: List of data source names to load
            allow_partial: If True, continue even if some sources missing
            
        Returns:
            ReconstructedState: Reconstructed historical state
            
        Raises:
            ValueError: If sources list is empty
            VintageReconstructionError: If reconstruction fails
            
        Example:
            >>> state = harness.reconstruct_state(
            ...     as_of_date=date(2024, 2, 15),
            ...     sources=["ces", "laus"]
            ... )
        """
        if not sources:
            raise ValueError("Sources list cannot be empty")
        
        logger.info(
            "Reconstructing vintage state",
            as_of_date=as_of_date,
            sources=sources,
            allow_partial=allow_partial
        )
        
        data: Dict[str, pd.DataFrame] = {}
        vintage_dates: Dict[str, date] = {}
        sources_available: List[str] = []
        errors: List[str] = []
        
        for source in sources:
            try:
                # Load vintage as of date
                vintage_data = self.vintage_manager.get_vintage_as_of(
                    source_name=source,
                    as_of_date=as_of_date
                )
                
                if vintage_data is None:
                    error_msg = (
                        f"No vintage available for source '{source}' "
                        f"on or before {as_of_date}"
                    )
                    errors.append(error_msg)
                    logger.warning(error_msg)
                    continue
                
                # Get the vintage date that was used
                available_vintages = self.vintage_manager.list_vintages(source)
                vintages_before = [v for v in available_vintages if v <= as_of_date]
                
                if not vintages_before:
                    error_msg = (
                        f"No vintage available for source '{source}' "
                        f"on or before {as_of_date}"
                    )
                    errors.append(error_msg)
                    logger.warning(error_msg)
                    continue
                
                vintage_date = vintages_before[-1]
                
                # Store data and metadata
                data[source] = vintage_data
                vintage_dates[source] = vintage_date
                sources_available.append(source)
                
                logger.info(
                    "Loaded vintage",
                    source=source,
                    vintage_date=vintage_date,
                    as_of_date=as_of_date,
                    rows=len(vintage_data)
                )
                
            except Exception as e:
                error_msg = f"Failed to load source '{source}': {str(e)}"
                errors.append(error_msg)
                logger.error(error_msg, exc_info=True)
        
        # Check if we have required data
        if not allow_partial and errors:
            raise VintageReconstructionError(
                f"Failed to reconstruct complete state. Errors: {'; '.join(errors)}"
            )
        
        if not data:
            raise VintageReconstructionError(
                f"No data available for any source on or before {as_of_date}"
            )
        
        # Create reconstructed state
        state = ReconstructedState(
            as_of_date=as_of_date,
            data=data,
            vintage_dates=vintage_dates,
            sources_requested=sources,
            sources_available=sources_available
        )
        
        logger.info(
            "State reconstruction complete",
            as_of_date=as_of_date,
            sources_available=len(sources_available),
            sources_requested=len(sources)
        )
        
        return state
    
    def validate_vintage_honesty(
        self,
        state: ReconstructedState
    ) -> Tuple[bool, List[str]]:
        """
        Validate that reconstructed state has no future data leakage.
        
        Checks:
        1. All vintage dates are on or before as_of_date
        2. All data timestamps are on or before vintage date
        3. No data points exist after as_of_date
        
        Args:
            state: ReconstructedState to validate
            
        Returns:
            Tuple[bool, List[str]]: (is_valid, list of error messages)
            
        Example:
            >>> is_valid, errors = harness.validate_vintage_honesty(state)
            >>> if not is_valid:
            ...     print(f"Validation failed: {errors}")
        """
        errors: List[str] = []
        
        logger.info(
            "Validating vintage honesty",
            as_of_date=state.as_of_date,
            sources=state.sources_available
        )
        
        # Check 1: Vintage dates on or before as_of_date
        for source, vintage_date in state.vintage_dates.items():
            if vintage_date > state.as_of_date:
                errors.append(
                    f"Source '{source}' vintage date {vintage_date} "
                    f"is after as_of_date {state.as_of_date}"
                )
        
        # Check 2: Data timestamps on or before vintage date
        for source, data in state.data.items():
            vintage_date = state.vintage_dates[source]
            
            # Check if data has date column
            if "date" in data.columns:
                try:
                    dates = pd.to_datetime(data["date"])
                    max_date = dates.max()
                    
                    if pd.notna(max_date) and max_date.date() > vintage_date:
                        errors.append(
                            f"Source '{source}' contains future data: "
                            f"max date {max_date.date()} exceeds "
                            f"vintage date {vintage_date}"
                        )
                except Exception as e:
                    logger.warning(
                        f"Could not validate dates for source '{source}': {e}"
                    )
            
            # Check index if it's a DatetimeIndex
            if isinstance(data.index, pd.DatetimeIndex):
                max_index_date = data.index.max()
                
                if pd.notna(max_index_date) and max_index_date.date() > vintage_date:
                    errors.append(
                        f"Source '{source}' index contains future data: "
                        f"max index {max_index_date.date()} exceeds "
                        f"vintage date {vintage_date}"
                    )
        
        # Check 3: No data after as_of_date
        for source, data in state.data.items():
            if "date" in data.columns:
                try:
                    dates = pd.to_datetime(data["date"])
                    future_data = dates > pd.Timestamp(state.as_of_date)
                    
                    if future_data.any():
                        count = future_data.sum()
                        errors.append(
                            f"Source '{source}' has {count} observations "
                            f"after as_of_date {state.as_of_date}"
                        )
                except Exception as e:
                    logger.warning(
                        f"Could not check future data for source '{source}': {e}"
                    )
        
        is_valid = len(errors) == 0
        
        if is_valid:
            logger.info(
                "Vintage honesty validation passed",
                sources=len(state.sources_available)
            )
        else:
            logger.error(
                "Vintage honesty validation failed",
                errors=errors
            )
        
        return is_valid, errors
    
    def get_available_backtest_dates(
        self,
        sources: List[str],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[date]:
        """
        Get list of dates that have complete vintage data for backtesting.
        
        Returns dates where all requested sources have vintages available.
        
        Args:
            sources: List of required data sources
            start_date: Optional start date filter
            end_date: Optional end date filter
            
        Returns:
            List[date]: Sorted list of backtest-ready dates
            
        Example:
            >>> dates = harness.get_available_backtest_dates(
            ...     sources=["ces", "laus"],
            ...     start_date=date(2023, 1, 1)
            ... )
        """
        if not sources:
            raise ValueError("Sources list cannot be empty")
        
        # Get vintages for all sources
        all_vintages = {}
        for source in sources:
            vintages = self.vintage_manager.list_vintages(source)
            
            if start_date:
                vintages = [v for v in vintages if v >= start_date]
            if end_date:
                vintages = [v for v in vintages if v <= end_date]
            
            all_vintages[source] = set(vintages)
        
        # Find intersection (dates where all sources have vintages)
        if not all_vintages:
            return []
        
        common_dates = set.intersection(*all_vintages.values())
        
        logger.info(
            "Found backtest dates",
            sources=sources,
            dates_available=len(common_dates)
        )
        
        return sorted(list(common_dates))

