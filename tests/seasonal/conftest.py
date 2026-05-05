"""Shared fixtures for seasonal diagnostics tests."""

from typing import Dict

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def simple_decomposition() -> Dict[str, pd.Series]:
    """Create a simple deterministic monthly decomposition."""
    dates = pd.date_range(start="2020-01-01", periods=24, freq="MS")
    seasonal_component = np.sin(np.arange(24) * 2 * np.pi / 12) * 10
    trend_component = np.linspace(100, 120, 24)
    irregular_component = np.random.RandomState(42).normal(0, 2, 24)
    original = seasonal_component + trend_component + irregular_component

    return {
        "original": pd.Series(original, index=dates),
        "seasonal": pd.Series(seasonal_component, index=dates),
        "trend": pd.Series(trend_component, index=dates),
        "irregular": pd.Series(irregular_component, index=dates),
        "seasonally_adjusted": pd.Series(trend_component + irregular_component, index=dates),
    }


@pytest.fixture
def high_quality_decomposition() -> Dict[str, pd.Series]:
    """Create a deterministic high-quality seasonal decomposition."""
    dates = pd.date_range(start="2020-01-01", periods=60, freq="MS")
    seasonal = np.tile(np.sin(np.arange(12) * 2 * np.pi / 12) * 20, 5)
    trend = np.linspace(100, 150, 60)
    irregular = np.random.RandomState(42).normal(0, 1, 60)
    original = seasonal + trend + irregular

    return {
        "original": pd.Series(original, index=dates),
        "seasonal": pd.Series(seasonal, index=dates),
        "trend": pd.Series(trend, index=dates),
        "irregular": pd.Series(irregular, index=dates),
        "seasonally_adjusted": pd.Series(trend + irregular, index=dates),
    }
