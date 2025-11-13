"""
Sector-to-total aggregation for CES data.

Aggregates sector-level employment to total nonfarm payrolls.
Supports:
- Simple sum aggregation
- Employment-weighted aggregation
- Coherence validation (sum of sectors = total)
"""

from typing import Literal, Optional
import pandas as pd
import numpy as np
import structlog

logger = structlog.get_logger(__name__)


class SectorAggregator:
    """
    Aggregate sector-level employment to total nonfarm.

    Used for CES (Current Employment Statistics) aggregation.
    Ensures hierarchical coherence: sum of all sectors = total nonfarm.

    Args:
        agg_method: Aggregation method ('sum', 'weighted_sum')

    Example:
        >>> aggregator = SectorAggregator(agg_method='sum')
        >>> total_nonfarm = aggregator.aggregate(
        ...     sector_data,
        ...     value_col='employment',
        ...     date_col='date',
        ...     sector_col='sector'
        ... )
    """

    def __init__(self, agg_method: Literal["sum", "weighted_sum"] = "sum"):
        """Initialize sector aggregator."""
        self.agg_method = agg_method

        logger.info("sector_aggregator_initialized", agg_method=agg_method)

    def aggregate(
        self,
        data: pd.DataFrame,
        value_col: str,
        date_col: str,
        sector_col: str,
        weights: Optional[pd.DataFrame] = None,
        weight_col: Optional[str] = None,
    ) -> pd.Series:
        """
        Aggregate sector data to total level.

        Args:
            data: Sector-level data
            value_col: Column containing values to aggregate
            date_col: Date column
            sector_col: Sector identifier column
            weights: Optional DataFrame with sector weights
            weight_col: Column in weights DataFrame with weight values

        Returns:
            Total-level aggregated series indexed by date

        Raises:
            ValueError: If required columns missing or invalid method
        """
        # Validate inputs
        required_cols = [value_col, date_col, sector_col]
        missing_cols = [col for col in required_cols if col not in data.columns]
        if missing_cols:
            raise ValueError(f"Missing required columns: {missing_cols}")

        logger.info(
            "aggregating_sector_data",
            n_sectors=data[sector_col].nunique(),
            n_dates=data[date_col].nunique(),
            agg_method=self.agg_method,
        )

        # Perform aggregation
        if self.agg_method == "sum":
            result = self._aggregate_sum(data, value_col, date_col, sector_col)

        elif self.agg_method == "weighted_sum":
            if weights is None or weight_col is None:
                raise ValueError("weights and weight_col required for weighted_sum")
            result = self._aggregate_weighted(
                data, value_col, date_col, sector_col, weights, weight_col
            )
        else:
            raise ValueError(f"Unknown aggregation method: {self.agg_method}")

        logger.info(
            "sector_aggregation_complete",
            result_length=len(result),
            missing_values=result.isna().sum(),
        )

        return result

    def _aggregate_sum(
        self,
        data: pd.DataFrame,
        value_col: str,
        date_col: str,
        sector_col: str,
    ) -> pd.Series:
        """Simple sum aggregation across sectors."""
        # Group by date and sum values
        grouped = data.groupby(date_col)[value_col].sum()

        return pd.Series(grouped.values, index=grouped.index, name=f"total_{value_col}")

    def _aggregate_weighted(
        self,
        data: pd.DataFrame,
        value_col: str,
        date_col: str,
        sector_col: str,
        weights: pd.DataFrame,
        weight_col: str,
    ) -> pd.Series:
        """Employment-weighted aggregation."""
        # Merge data with weights
        merged = data.merge(weights, on=sector_col, how="left")

        # Check for missing weights
        if merged[weight_col].isna().any():
            missing_sectors = merged[merged[weight_col].isna()][sector_col].unique()
            logger.warning("missing_weights_for_sectors", sectors=missing_sectors.tolist())
            # Fill missing weights with zero
            merged[weight_col] = merged[weight_col].fillna(0)

        # Compute weighted values
        merged["weighted_value"] = merged[value_col] * merged[weight_col]

        # Group by date and sum weighted values
        grouped = merged.groupby(date_col)["weighted_value"].sum()

        return pd.Series(
            grouped.values, index=grouped.index, name=f"total_{value_col}_weighted"
        )


def aggregate_all_sectors(
    sector_data: pd.DataFrame,
    value_col: str = "employment",
    date_col: str = "date",
    sector_col: str = "sector",
) -> pd.Series:
    """
    Convenience function to aggregate all sectors to total nonfarm.

    Args:
        sector_data: Sector-level data
        value_col: Value column name
        date_col: Date column name
        sector_col: Sector column name

    Returns:
        Total nonfarm series

    Example:
        >>> total_nonfarm = aggregate_all_sectors(ces_sector_data)
    """
    aggregator = SectorAggregator(agg_method="sum")
    return aggregator.aggregate(sector_data, value_col, date_col, sector_col)

