"""
Unit tests for VintageHarness

Tests the vintage harness's ability to reconstruct historical data states
for vintage-honest backtesting.
"""

import pytest
import pandas as pd
import numpy as np
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) in sys.path:
    sys.path.remove(str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT))
sys.modules.pop("backtests", None)

from backtests.vintage_harness.harness import (
    VintageHarness,
    VintageReconstructionError,
    ReconstructedState,
)
from etl.common.vintage import VintageManager


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def temp_vintage_dir(tmp_path):
    """Create temporary vintage directory for testing."""
    vintage_dir = tmp_path / "vintages"
    vintage_dir.mkdir()
    return vintage_dir


@pytest.fixture
def sample_data_sources():
    """Define sample data sources for testing."""
    return ["ces", "laus", "claims", "treasury"]


@pytest.fixture
def vintage_manager(temp_vintage_dir):
    """Create VintageManager for testing."""
    return VintageManager(temp_vintage_dir)


@pytest.fixture
def sample_vintages(vintage_manager, sample_data_sources):
    """
    Create sample vintages for testing.
    
    Creates vintages on 2024-01-01, 2024-02-01, 2024-03-01 for each source.
    """
    vintages_created = {}
    
    for source in sample_data_sources:
        vintages_created[source] = []
        
        for month in range(1, 4):
            vintage_date = date(2024, month, 1)
            
            # Create sample data with date range up to vintage_date
            dates = pd.date_range(
                start="2020-01-01",
                end=vintage_date,
                freq="MS"
            )
            
            data = pd.DataFrame({
                "date": dates,
                "value": np.random.randn(len(dates)) * 100 + 1000,
                "series_id": f"{source}_test_series"
            })
            
            # Create vintage
            vintage_manager.create_vintage(source, data, vintage_date)
            vintages_created[source].append(vintage_date)
    
    return vintages_created


@pytest.fixture
def vintage_harness(temp_vintage_dir):
    """Create VintageHarness for testing."""
    return VintageHarness(temp_vintage_dir)


# ============================================================================
# Unit Tests: Vintage Reconstruction
# ============================================================================


class TestVintageReconstruction:
    """Test vintage reconstruction logic."""
    
    def test_harness_initialization(self, temp_vintage_dir):
        """Test VintageHarness initializes correctly."""
        harness = VintageHarness(temp_vintage_dir)
        
        assert harness.vintage_base_path == temp_vintage_dir
        assert hasattr(harness, 'vintage_manager')
        assert isinstance(harness.vintage_manager, VintageManager)
    
    def test_reconstruct_single_source(
        self, vintage_harness, sample_vintages
    ):
        """Test reconstructing state for a single data source."""
        as_of_date = date(2024, 2, 15)
        source = "ces"
        
        state = vintage_harness.reconstruct_state(
            as_of_date=as_of_date,
            sources=[source]
        )
        
        # Should return ReconstructedState with data
        assert isinstance(state, ReconstructedState)
        assert source in state.data
        assert isinstance(state.data[source], pd.DataFrame)
        assert state.as_of_date == as_of_date
        
        # Data should be from 2024-02-01 vintage (latest before as_of_date)
        assert state.vintage_dates[source] == date(2024, 2, 1)
        
        # Data should not contain dates after vintage_date
        max_date = pd.to_datetime(state.data[source]["date"]).max()
        assert max_date.date() <= date(2024, 2, 1)
    
    def test_reconstruct_multiple_sources(
        self, vintage_harness, sample_vintages
    ):
        """Test reconstructing state for multiple data sources."""
        as_of_date = date(2024, 3, 15)
        sources = ["ces", "laus", "claims"]
        
        state = vintage_harness.reconstruct_state(
            as_of_date=as_of_date,
            sources=sources
        )
        
        # All sources should be present
        assert all(source in state.data for source in sources)
        assert len(state.data) == len(sources)
        
        # Each should have correct vintage date
        for source in sources:
            assert state.vintage_dates[source] == date(2024, 3, 1)
            assert isinstance(state.data[source], pd.DataFrame)
    
    def test_reconstruct_uses_latest_available_vintage(
        self, vintage_harness, sample_vintages
    ):
        """Test that reconstruction uses latest vintage on or before as_of_date."""
        # As of date between two vintages
        as_of_date = date(2024, 2, 15)
        source = "ces"
        
        state = vintage_harness.reconstruct_state(
            as_of_date=as_of_date,
            sources=[source]
        )
        
        # Should use 2024-02-01, not 2024-03-01
        assert state.vintage_dates[source] == date(2024, 2, 1)
        
        # Try with as_of_date on exact vintage date
        as_of_date_exact = date(2024, 3, 1)
        state_exact = vintage_harness.reconstruct_state(
            as_of_date=as_of_date_exact,
            sources=[source]
        )
        
        # Should use exactly 2024-03-01
        assert state_exact.vintage_dates[source] == date(2024, 3, 1)
    
    def test_reconstruct_before_first_vintage(
        self, vintage_harness, sample_vintages
    ):
        """Test reconstruction when as_of_date is before any vintages exist."""
        as_of_date = date(2023, 12, 1)  # Before 2024-01-01
        source = "ces"
        
        with pytest.raises(VintageReconstructionError) as exc_info:
            vintage_harness.reconstruct_state(
                as_of_date=as_of_date,
                sources=[source]
            )
        
        assert "No vintage available" in str(exc_info.value)
        assert source in str(exc_info.value)
    
    def test_reconstruct_with_missing_source(
        self, vintage_harness, sample_vintages
    ):
        """Test reconstruction when a requested source doesn't exist."""
        as_of_date = date(2024, 2, 15)
        sources = ["ces", "nonexistent_source"]
        
        with pytest.raises(VintageReconstructionError) as exc_info:
            vintage_harness.reconstruct_state(
                as_of_date=as_of_date,
                sources=sources
            )
        
        assert "nonexistent_source" in str(exc_info.value)
    
    def test_reconstruct_with_empty_sources_list(self, vintage_harness):
        """Test reconstruction with empty sources list."""
        as_of_date = date(2024, 2, 15)
        
        with pytest.raises(ValueError) as exc_info:
            vintage_harness.reconstruct_state(
                as_of_date=as_of_date,
                sources=[]
            )
        
        assert "sources list cannot be empty" in str(exc_info.value).lower()
    
    def test_reconstructed_state_properties(
        self, vintage_harness, sample_vintages
    ):
        """Test ReconstructedState dataclass properties."""
        as_of_date = date(2024, 2, 15)
        sources = ["ces", "laus"]
        
        state = vintage_harness.reconstruct_state(
            as_of_date=as_of_date,
            sources=sources
        )
        
        # Test dataclass properties
        assert hasattr(state, 'as_of_date')
        assert hasattr(state, 'data')
        assert hasattr(state, 'vintage_dates')
        assert hasattr(state, 'sources_requested')
        assert hasattr(state, 'sources_available')
        
        assert state.sources_requested == sources
        assert state.sources_available == sources
        assert isinstance(state.data, dict)
        assert isinstance(state.vintage_dates, dict)


# ============================================================================
# Unit Tests: Vintage-Honesty Validation
# ============================================================================


class TestVintageHonestyValidation:
    """Test vintage-honesty validation logic."""
    
    def test_validate_no_future_data_leakage(
        self, vintage_harness, sample_vintages
    ):
        """Test that validation catches future data leakage."""
        as_of_date = date(2024, 2, 15)
        source = "ces"
        
        state = vintage_harness.reconstruct_state(
            as_of_date=as_of_date,
            sources=[source]
        )
        
        # Validation should pass (no future data)
        is_valid, errors = vintage_harness.validate_vintage_honesty(state)
        
        assert is_valid is True
        assert len(errors) == 0
    
    def test_detect_future_data_in_reconstruction(
        self, vintage_harness, vintage_manager, sample_vintages
    ):
        """Test detection of future data if present."""
        as_of_date = date(2024, 2, 15)
        source = "ces"
        
        # Create a "poisoned" vintage with future data
        future_dates = pd.date_range(
            start="2020-01-01",
            end="2024-03-01",  # Past as_of_date!
            freq="MS"
        )
        
        poisoned_data = pd.DataFrame({
            "date": future_dates,
            "value": np.random.randn(len(future_dates)),
            "series_id": f"{source}_poisoned"
        })
        
        # Overwrite the 2024-02-01 vintage with poisoned data
        vintage_manager.create_vintage(
            source, poisoned_data, date(2024, 2, 1), allow_overwrite=True
        )
        
        # Reconstruct and validate
        state = vintage_harness.reconstruct_state(
            as_of_date=as_of_date,
            sources=[source]
        )
        
        is_valid, errors = vintage_harness.validate_vintage_honesty(state)
        
        # Should detect future data
        assert is_valid is False
        assert len(errors) > 0
        assert any("future data" in err.lower() for err in errors)
    
    def test_validate_vintage_dates_before_as_of_date(
        self, vintage_harness, sample_vintages
    ):
        """Test that all vintage dates are on or before as_of_date."""
        as_of_date = date(2024, 2, 15)
        sources = ["ces", "laus"]
        
        state = vintage_harness.reconstruct_state(
            as_of_date=as_of_date,
            sources=sources
        )
        
        # Check vintage dates
        for source, vintage_date in state.vintage_dates.items():
            assert vintage_date <= as_of_date
    
    def test_validate_data_timestamps_before_vintage_date(
        self, vintage_harness, sample_vintages
    ):
        """Test that data timestamps don't exceed vintage date."""
        as_of_date = date(2024, 2, 15)
        source = "ces"
        
        state = vintage_harness.reconstruct_state(
            as_of_date=as_of_date,
            sources=[source]
        )
        
        vintage_date = state.vintage_dates[source]
        data = state.data[source]
        
        # All data timestamps should be <= vintage_date
        if "date" in data.columns:
            max_date = pd.to_datetime(data["date"]).max()
            assert max_date.date() <= vintage_date


# ============================================================================
# Unit Tests: Edge Cases
# ============================================================================


class TestEdgeCases:
    """Test edge case handling (missing data, short series)."""
    
    def test_missing_data_source(self, temp_vintage_dir):
        """Test handling when a data source has no vintages."""
        harness = VintageHarness(temp_vintage_dir)
        as_of_date = date(2024, 2, 15)
        
        with pytest.raises(VintageReconstructionError):
            harness.reconstruct_state(
                as_of_date=as_of_date,
                sources=["nonexistent"]
            )
    
    def test_short_series_handling(
        self, vintage_manager, vintage_harness
    ):
        """Test handling of series with insufficient history."""
        source = "short_series"
        vintage_date = date(2024, 1, 1)
        
        # Create vintage with only 3 observations
        short_data = pd.DataFrame({
            "date": pd.date_range(start="2023-11-01", periods=3, freq="MS"),
            "value": [100, 105, 110],
            "series_id": f"{source}_short"
        })
        
        vintage_manager.create_vintage(source, short_data, vintage_date)
        
        # Should still reconstruct, but state should indicate short series
        as_of_date = date(2024, 1, 15)
        state = vintage_harness.reconstruct_state(
            as_of_date=as_of_date,
            sources=[source]
        )
        
        assert source in state.data
        assert len(state.data[source]) == 3
    
    def test_partial_source_availability(
        self, vintage_manager, vintage_harness
    ):
        """Test reconstruction when only some sources are available."""
        # Create vintages for only ces and laus
        for source in ["ces", "laus"]:
            data = pd.DataFrame({
                "date": pd.date_range(start="2023-01-01", periods=12, freq="MS"),
                "value": np.random.randn(12) * 100,
                "series_id": f"{source}_series"
            })
            vintage_manager.create_vintage(source, data, date(2024, 1, 1))
        
        as_of_date = date(2024, 1, 15)
        
        # Request ces, laus (available) and claims (not available)
        with pytest.raises(VintageReconstructionError) as exc_info:
            vintage_harness.reconstruct_state(
                as_of_date=as_of_date,
                sources=["ces", "laus", "claims"]
            )
        
        assert "claims" in str(exc_info.value)
    
    def test_reconstruct_with_allow_partial_sources(
        self, vintage_manager, vintage_harness
    ):
        """Test reconstruction with allow_partial=True for incomplete sources."""
        # Create vintages for only ces and laus
        for source in ["ces", "laus"]:
            data = pd.DataFrame({
                "date": pd.date_range(start="2023-01-01", periods=12, freq="MS"),
                "value": np.random.randn(12) * 100,
                "series_id": f"{source}_series"
            })
            vintage_manager.create_vintage(source, data, date(2024, 1, 1))
        
        as_of_date = date(2024, 1, 15)
        
        # Request 3 sources but allow partial
        state = vintage_harness.reconstruct_state(
            as_of_date=as_of_date,
            sources=["ces", "laus", "claims"],
            allow_partial=True
        )
        
        # Should have ces and laus, but not claims
        assert state.sources_requested == ["ces", "laus", "claims"]
        assert set(state.sources_available) == {"ces", "laus"}
        assert "claims" not in state.data
    
    def test_empty_vintage(self, vintage_manager, vintage_harness):
        """Test handling of empty vintage (edge case, should not happen)."""
        source = "empty_source"
        
        # VintageManager should reject empty DataFrame
        with pytest.raises(Exception):  # VintageError
            vintage_manager.create_vintage(
                source,
                pd.DataFrame(),
                date(2024, 1, 1)
            )
    
    def test_future_as_of_date(self, vintage_harness, sample_vintages):
        """Test reconstruction with as_of_date in the future."""
        # Future date should still work if vintages exist
        as_of_date = date(2025, 1, 1)
        source = "ces"
        
        state = vintage_harness.reconstruct_state(
            as_of_date=as_of_date,
            sources=[source]
        )
        
        # Should use latest available vintage (2024-03-01)
        assert state.vintage_dates[source] == date(2024, 3, 1)


# ============================================================================
# Integration Tests
# ============================================================================


class TestVintageHarnessIntegration:
    """Integration tests for complete reconstruction workflows."""
    
    def test_full_backtest_workflow(
        self, vintage_harness, sample_vintages
    ):
        """Test typical backtest workflow with vintage harness."""
        # Simulate backtest dates
        backtest_dates = [
            date(2024, 1, 15),
            date(2024, 2, 15),
            date(2024, 3, 15),
        ]
        
        sources = ["ces", "laus"]
        
        for backtest_date in backtest_dates:
            # Reconstruct state
            state = vintage_harness.reconstruct_state(
                as_of_date=backtest_date,
                sources=sources
            )
            
            # Validate vintage honesty
            is_valid, errors = vintage_harness.validate_vintage_honesty(state)
            assert is_valid, f"Validation failed on {backtest_date}: {errors}"
            
            # Verify data is available for both sources
            assert all(source in state.data for source in sources)
    
    def test_reconstruct_with_metadata(
        self, vintage_harness, sample_vintages
    ):
        """Test that reconstruction preserves metadata."""
        as_of_date = date(2024, 2, 15)
        sources = ["ces"]
        
        state = vintage_harness.reconstruct_state(
            as_of_date=as_of_date,
            sources=sources
        )
        
        # State should contain metadata
        assert hasattr(state, 'metadata')
        assert 'reconstruction_timestamp' in state.metadata
        assert 'harness_version' in state.metadata


# ============================================================================
# Performance Tests
# ============================================================================


class TestPerformance:
    """Test performance characteristics of vintage harness."""
    
    def test_reconstruction_performance(
        self, vintage_harness, sample_vintages
    ):
        """Test that reconstruction completes in reasonable time."""
        import time
        
        as_of_date = date(2024, 2, 15)
        sources = ["ces", "laus", "claims", "treasury"]
        
        start_time = time.time()
        state = vintage_harness.reconstruct_state(
            as_of_date=as_of_date,
            sources=sources
        )
        elapsed_time = time.time() - start_time
        
        # Should complete in < 1 second for 4 sources
        assert elapsed_time < 1.0
        assert len(state.data) == len(sources)
    
    def test_validation_performance(
        self, vintage_harness, sample_vintages
    ):
        """Test that validation completes quickly."""
        import time
        
        as_of_date = date(2024, 2, 15)
        sources = ["ces", "laus", "claims", "treasury"]
        
        state = vintage_harness.reconstruct_state(
            as_of_date=as_of_date,
            sources=sources
        )
        
        start_time = time.time()
        is_valid, errors = vintage_harness.validate_vintage_honesty(state)
        elapsed_time = time.time() - start_time
        
        # Validation should be very fast (< 0.1s)
        assert elapsed_time < 0.1
        assert is_valid is True

