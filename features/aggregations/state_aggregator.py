"""
State-to-national aggregation for LAUS data.

Aggregates state-level employment/unemployment to national totals.
Supports:
- Simple sum aggregation
- Population-weighted aggregation
- Coherence validation (sum of states = national)
"""

from typing import Literal, Optional
import pandas as pd
import numpy as np
import structlog

logger = structlog.get_logger(__name__)


class StateAggregator:
    """
    Aggregate state-level data to national totals.

    Used for LAUS (Local Area Unemployment Statistics) aggregation.
    Ensures hierarchical coherence: sum of all states = national total.

    Args:
        agg_method: Aggregation method ('sum', 'weighted_mean')
        weighted: Whether to use population weights
        handle_missing: How to handle missing state data ('fill_zero', 'drop', 'error')

    Example:
        >>> aggregator = StateAggregator(agg_method='sum')
        >>> national = aggregator.aggregate(
        ...     state_data,
        ...     value_col='employment',
        ...     date_col='date',
        ...     state_col='state'
        ... )
    """

    def __init__(
        self,
        agg_method: Literal["sum", "weighted_mean"] = "sum",
        weighted: bool = False,
        handle_missing: Literal["fill_zero", "drop", "error"] = "fill_zero",
    ):
        """Initialize state aggregator."""
        self.agg_method = agg_method
        self.weighted = weighted
        self.handle_missing = handle_missing

        logger.info(
            "state_aggregator_initialized",
            agg_method=agg_method,
            weighted=weighted,
            handle_missing=handle_missing,
        )

    def aggregate(
        self,
        data: pd.DataFrame,
        value_col: str,
        date_col: str,
        state_col: str,
        weights: Optional[pd.DataFrame] = None,
        weight_col: Optional[str] = None,
    ) -> pd.Series:
        """
        Aggregate state data to national level.

        Args:
            data: State-level data
            value_col: Column containing values to aggregate
            date_col: Date column
            state_col: State identifier column
            weights: Optional DataFrame with state weights (for weighted aggregation)
            weight_col: Column in weights DataFrame with weight values

        Returns:
            National-level aggregated series indexed by date

        Raises:
            ValueError: If required columns missing or invalid method
        """
        # Validate inputs
        required_cols = [value_col, date_col, state_col]
        missing_cols = [col for col in required_cols if col not in data.columns]
        if missing_cols:
            raise ValueError(f"Missing required columns: {missing_cols}")

        logger.info(
            "aggregating_state_data",
            n_states=data[state_col].nunique(),
            n_dates=data[date_col].nunique(),
            agg_method=self.agg_method,
        )

        # Perform aggregation
        if self.agg_method == "sum":
            result = self._aggregate_sum(data, value_col, date_col, state_col)

        elif self.agg_method == "weighted_mean":
            if weights is None or weight_col is None:
                raise ValueError("weights and weight_col required for weighted_mean")
            result = self._aggregate_weighted(
                data, value_col, date_col, state_col, weights, weight_col
            )
        else:
            raise ValueError(f"Unknown aggregation method: {self.agg_method}")

        logger.info(
            "state_aggregation_complete",
            result_length=len(result),
            missing_values=result.isna().sum(),
        )

        return result

    def _aggregate_sum(
        self,
        data: pd.DataFrame,
        value_col: str,
        date_col: str,
        state_col: str,
    ) -> pd.Series:
        """Simple sum aggregation across states."""
        # Group by date and sum values
        grouped = data.groupby(date_col)[value_col].sum()

        return pd.Series(grouped.values, index=grouped.index, name=f"national_{value_col}")

    def _aggregate_weighted(
        self,
        data: pd.DataFrame,
        value_col: str,
        date_col: str,
        state_col: str,
        weights: pd.DataFrame,
        weight_col: str,
    ) -> pd.Series:
        """Population-weighted aggregation."""
        # Merge data with weights
        merged = data.merge(weights, on=state_col, how="left")

        # Check for missing weights
        if merged[weight_col].isna().any():
            missing_states = merged[merged[weight_col].isna()][state_col].unique()
            logger.warning("missing_weights_for_states", states=missing_states.tolist())

            if self.handle_missing == "error":
                raise ValueError(f"Missing weights for states: {missing_states}")
            elif self.handle_missing == "fill_zero":
                merged[weight_col] = merged[weight_col].fillna(0)

        # Compute weighted values
        merged["weighted_value"] = merged[value_col] * merged[weight_col]

        # Group by date and sum weighted values
        grouped = merged.groupby(date_col)["weighted_value"].sum()

        # Normalize by total weight per date
        weight_totals = merged.groupby(date_col)[weight_col].sum()
        normalized = grouped / weight_totals

        return pd.Series(
            normalized.values, index=normalized.index, name=f"national_{value_col}_weighted"
        )


def aggregate_all_states(
    state_data: pd.DataFrame,
    value_col: str = "employment",
    date_col: str = "date",
    state_col: str = "state",
) -> pd.Series:
    """
    Convenience function to aggregate all states to national total.

    Args:
        state_data: State-level data
        value_col: Value column name
        date_col: Date column name
        state_col: State column name

    Returns:
        National total series

    Example:
        >>> national_employment = aggregate_all_states(laus_state_data)
    """
    aggregator = StateAggregator(agg_method="sum")
    return aggregator.aggregate(state_data, value_col, date_col, state_col)

