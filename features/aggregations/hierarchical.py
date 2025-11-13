"""
Hierarchical forecasting utilities.

Supports:
- MinT (Minimum Trace) reconciliation structure preparation
- Coherence validation (sum of components = total)
- Summing matrix construction
"""

from typing import Dict, List
import pandas as pd
import numpy as np
from loguru import logger


def prepare_mint_structure(forecasts: pd.DataFrame) -> Dict:
    """
    Prepare hierarchical structure for MinT reconciliation.

    Creates summing matrix S where: y_bottom = S * y_all
    Enables coherent forecast reconciliation.

    Args:
        forecasts: DataFrame with hierarchical forecasts
                   (columns = different hierarchy levels)

    Returns:
        Dictionary with:
        - 'summing_matrix': Summing matrix S
        - 'forecasts': Original forecasts
        - 'hierarchy_info': Metadata about hierarchy

    Example:
        >>> # Forecasts: national, states (CA, TX, NY)
        >>> forecasts = pd.DataFrame({
        ...     'national': [150, 155, 160],
        ...     'CA': [40, 41, 42],
        ...     'TX': [30, 31, 32],
        ...     'NY': [25, 26, 27]
        ... })
        >>> structure = prepare_mint_structure(forecasts)
        >>> S = structure['summing_matrix']
    """
    n_series = len(forecasts.columns)
    n_bottom = n_series - 1  # Assume first column is total

    # Simple summing matrix for 2-level hierarchy
    # S = [1, 1, 1, ..., 1]  (row vector)
    # This says: national = sum of all states

    summing_matrix = np.ones((1, n_bottom))

    logger.info(
        "mint_structure_prepared",
        n_total_series=n_series,
        n_bottom_series=n_bottom,
        summing_matrix_shape=summing_matrix.shape,
    )

    return {
        "summing_matrix": summing_matrix,
        "forecasts": forecasts,
        "hierarchy_info": {
            "n_total": n_series,
            "n_bottom": n_bottom,
            "levels": ["total", "bottom"],
        },
    }


def validate_coherence(
    data: pd.DataFrame,
    total_col: str,
    component_cols: List[str],
    tolerance: float = 1e-6,
) -> bool:
    """
    Validate that sum of components equals total (hierarchical coherence).

    Args:
        data: DataFrame with total and component columns
        total_col: Column name for total
        component_cols: List of component column names
        tolerance: Numerical tolerance for equality check

    Returns:
        True if coherent (sum of components ≈ total), False otherwise

    Example:
        >>> data = pd.DataFrame({
        ...     'total': [100, 110],
        ...     'part1': [60, 66],
        ...     'part2': [40, 44]
        ... })
        >>> validate_coherence(data, 'total', ['part1', 'part2'])
        True
    """
    # Check all required columns exist
    missing = [col for col in [total_col] + component_cols if col not in data.columns]
    if missing:
        raise ValueError(f"Missing columns: {missing}")

    # Compute sum of components
    component_sum = data[component_cols].sum(axis=1)

    # Compare to total
    differences = np.abs(data[total_col] - component_sum)
    is_coherent = (differences < tolerance).all()

    if not is_coherent:
        max_diff = differences.max()
        logger.warning(
            "coherence_validation_failed",
            max_difference=max_diff,
            tolerance=tolerance,
            n_violations=int((differences >= tolerance).sum()),
        )
    else:
        logger.info("coherence_validation_passed", tolerance=tolerance)

    return bool(is_coherent)


def compute_coherence_errors(
    data: pd.DataFrame, total_col: str, component_cols: List[str]
) -> pd.Series:
    """
    Compute coherence errors (total - sum of components).

    Args:
        data: DataFrame with total and component columns
        total_col: Column name for total
        component_cols: List of component column names

    Returns:
        Series of coherence errors

    Example:
        >>> errors = compute_coherence_errors(data, 'total', ['part1', 'part2'])
        >>> print(errors.mean())  # Average coherence error
    """
    component_sum = data[component_cols].sum(axis=1)
    errors = data[total_col] - component_sum

    logger.info(
        "coherence_errors_computed",
        mean_error=errors.mean(),
        max_error=errors.max(),
        min_error=errors.min(),
    )

    return errors


def build_summing_matrix(n_bottom: int, hierarchy_type: str = "single_level") -> np.ndarray:
    """
    Build summing matrix for hierarchical reconciliation.

    Args:
        n_bottom: Number of bottom-level series
        hierarchy_type: Type of hierarchy ('single_level', 'two_level')

    Returns:
        Summing matrix S

    Example:
        >>> # 3 states → 1 national
        >>> S = build_summing_matrix(n_bottom=3, hierarchy_type='single_level')
        >>> S.shape
        (1, 3)
    """
    if hierarchy_type == "single_level":
        # Simple aggregation: total = sum of all bottom series
        S = np.ones((1, n_bottom))

    elif hierarchy_type == "two_level":
        # More complex hierarchy (e.g., national → regions → states)
        # This is simplified - real implementation would be more complex
        raise NotImplementedError("Two-level hierarchy not yet implemented")

    else:
        raise ValueError(f"Unknown hierarchy type: {hierarchy_type}")

    logger.info(
        "summing_matrix_built",
        hierarchy_type=hierarchy_type,
        matrix_shape=S.shape,
    )

    return S

