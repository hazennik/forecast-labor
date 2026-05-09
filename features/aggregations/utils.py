"""
Aggregation utility functions.

Utilities for:
- Computing employment-based weights
- Computing population-based weights
- Weight normalization
"""

import pandas as pd
from loguru import logger


def compute_employment_weights(employment: pd.Series) -> pd.Series:
    """
    Compute employment-based weights (proportion of total employment).

    Args:
        employment: Series of employment values indexed by sector/state

    Returns:
        Series of weights summing to 1.0

    Example:
        >>> employment = pd.Series([10_000, 20_000, 30_000], index=['A', 'B', 'C'])
        >>> weights = compute_employment_weights(employment)
        >>> weights['C']  # Largest sector
        0.5
    """
    if len(employment) == 0:
        raise ValueError("Employment series cannot be empty")

    if (employment < 0).any():
        raise ValueError("Employment values must be non-negative")

    total_employment = employment.sum()

    if total_employment == 0:
        logger.warning("zero_total_employment_using_equal_weights")
        # Use equal weights if total is zero
        weights = pd.Series(1.0 / len(employment), index=employment.index)
    else:
        weights = employment / total_employment

    logger.info(
        "employment_weights_computed",
        n_entities=len(weights),
        total_weight=weights.sum(),
        max_weight=weights.max(),
        min_weight=weights.min(),
    )

    return weights


def compute_population_weights(population: pd.Series) -> pd.Series:
    """
    Compute population-based weights (proportion of total population).

    Args:
        population: Series of population values indexed by state

    Returns:
        Series of weights summing to 1.0

    Example:
        >>> population = pd.Series([1_000_000, 2_000_000, 3_000_000], index=['A', 'B', 'C'])
        >>> weights = compute_population_weights(population)
        >>> weights['C']  # Most populous
        0.5
    """
    if len(population) == 0:
        raise ValueError("Population series cannot be empty")

    if (population < 0).any():
        raise ValueError("Population values must be non-negative")

    total_population = population.sum()

    if total_population == 0:
        logger.warning("zero_total_population_using_equal_weights")
        # Use equal weights if total is zero
        weights = pd.Series(1.0 / len(population), index=population.index)
    else:
        weights = population / total_population

    logger.info(
        "population_weights_computed",
        n_states=len(weights),
        total_weight=weights.sum(),
        max_weight=weights.max(),
        min_weight=weights.min(),
    )

    return weights


def normalize_weights(weights: pd.Series) -> pd.Series:
    """
    Normalize weights to sum to 1.0.

    Args:
        weights: Series of unnormalized weights

    Returns:
        Normalized weights summing to 1.0

    Example:
        >>> weights = pd.Series([2, 4, 6], index=['A', 'B', 'C'])
        >>> normalized = normalize_weights(weights)
        >>> normalized.sum()
        1.0
    """
    if len(weights) == 0:
        raise ValueError("Weights series cannot be empty")

    if (weights < 0).any():
        raise ValueError("Weights must be non-negative")

    total = weights.sum()

    if total == 0:
        logger.warning("zero_weight_sum_using_equal_weights")
        # Use equal weights if sum is zero
        return pd.Series(1.0 / len(weights), index=weights.index)

    normalized = weights / total

    logger.debug(
        "weights_normalized",
        original_sum=total,
        normalized_sum=normalized.sum(),
    )

    return normalized
