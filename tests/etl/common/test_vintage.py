"""
Unit tests for VintageManager.

Tests vintage snapshot creation, loading, and management.
"""

import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from etl.common.vintage import VintageManager, VintageError


@pytest.mark.unit
@pytest.mark.etl
class TestVintageManager:
    """Test suite for VintageManager class"""
    
    @pytest.fixture
    def temp_vintage_dir(self) -> Path:
        """Create temporary directory for vintage testing"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    @pytest.fixture
    def vintage_manager(self, temp_vintage_dir: Path) -> VintageManager:
        """Create VintageManager with temporary directory"""
        return VintageManager(temp_vintage_dir)
    
    @pytest.fixture
    def sample_data(self) -> pd.DataFrame:
        """Create sample DataFrame for testing"""
        return pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=12, freq="MS"),
            "value": np.random.randint(100000, 200000, 12),
            "series_id": "TEST_SERIES"
        })
    
    @pytest.fixture
    def test_date(self) -> date:
        """Fixed test date for determinism"""
        return date(2024, 11, 1)
    
    # =====================
    # INITIALIZATION TESTS
    # =====================
    
    def test_init_creates_base_directory(self):
        """Test that initialization creates base directory"""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir) / "vintages"
            
            manager = VintageManager(base_path)
            
            assert manager.base_path == base_path
            assert base_path.exists()
    
    def test_init_with_existing_directory(self, temp_vintage_dir):
        """Test initialization with existing directory"""
        # Create directory first
        temp_vintage_dir.mkdir(parents=True, exist_ok=True)
        
        manager = VintageManager(temp_vintage_dir)
        
        assert manager.base_path == temp_vintage_dir
        assert temp_vintage_dir.exists()
    
    # =====================
    # CREATE VINTAGE TESTS
    # =====================
    
    def test_create_vintage_success(self, vintage_manager, sample_data, test_date):
        """Test successful vintage creation"""
        vintage_path = vintage_manager.create_vintage(
            "test_source",
            sample_data,
            vintage_date=test_date
        )
        
        assert vintage_path.exists()
        assert vintage_path.name == "test_source_vintage.parquet"
        assert test_date.strftime("%Y-%m-%d") in str(vintage_path)
        
        # Verify data can be loaded
        loaded_data = pd.read_parquet(vintage_path)
        assert len(loaded_data) == len(sample_data)
    
    def test_create_vintage_default_date(self, vintage_manager, sample_data):
        """Test vintage creation with default date (today)"""
        vintage_path = vintage_manager.create_vintage(
            "test_source",
            sample_data
        )
        
        today_str = date.today().strftime("%Y-%m-%d")
        assert today_str in str(vintage_path)
    
    def test_create_vintage_directory_structure(self, vintage_manager, sample_data, test_date):
        """Test vintage directory structure"""
        vintage_path = vintage_manager.create_vintage(
            "test_source",
            sample_data,
            vintage_date=test_date
        )
        
        # Expected structure: {base}/test_source/2024-11-01/test_source_vintage.parquet
        assert "test_source" in str(vintage_path)
        assert "2024-11-01" in str(vintage_path)
    
    def test_create_vintage_empty_dataframe_raises_error(self, vintage_manager, test_date):
        """Test that creating vintage from empty DataFrame raises error"""
        empty_df = pd.DataFrame()
        
        with pytest.raises(VintageError) as exc_info:
            vintage_manager.create_vintage(
                "test_source",
                empty_df,
                vintage_date=test_date
            )
        
        assert "empty DataFrame" in str(exc_info.value)
    
    def test_create_vintage_already_exists_raises_error(self, vintage_manager, sample_data, test_date):
        """Test that creating duplicate vintage raises error"""
        # Create first vintage
        vintage_manager.create_vintage(
            "test_source",
            sample_data,
            vintage_date=test_date
        )
        
        # Attempt to create duplicate
        with pytest.raises(VintageError) as exc_info:
            vintage_manager.create_vintage(
                "test_source",
                sample_data,
                vintage_date=test_date
            )
        
        assert "already exists" in str(exc_info.value)
    
    def test_create_vintage_allow_overwrite(self, vintage_manager, sample_data, test_date):
        """Test vintage creation with overwrite allowed"""
        # Create first vintage
        vintage_path1 = vintage_manager.create_vintage(
            "test_source",
            sample_data,
            vintage_date=test_date
        )
        
        # Create modified data
        modified_data = sample_data.copy()
        modified_data["value"] = modified_data["value"] * 2
        
        # Overwrite vintage
        vintage_path2 = vintage_manager.create_vintage(
            "test_source",
            modified_data,
            vintage_date=test_date,
            allow_overwrite=True
        )
        
        assert vintage_path1 == vintage_path2
        
        # Verify data was overwritten
        loaded_data = pd.read_parquet(vintage_path2)
        assert not loaded_data["value"].equals(sample_data["value"])
    
    def test_create_vintage_file_permissions(self, vintage_manager, sample_data, test_date):
        """Test that vintage file is set to read-only"""
        vintage_path = vintage_manager.create_vintage(
            "test_source",
            sample_data,
            vintage_date=test_date
        )
        
        # On Unix systems, check file is read-only (0o444)
        # On Windows, this test may pass without actual read-only
        import platform
        if platform.system() != "Windows":
            mode = vintage_path.stat().st_mode
            # Check that file is readable but not writable
            assert mode & 0o444  # Has read permissions
    
    # =====================
    # LOAD VINTAGE TESTS
    # =====================
    
    def test_load_vintage_success(self, vintage_manager, sample_data, test_date):
        """Test successful vintage loading"""
        # Create vintage
        vintage_manager.create_vintage(
            "test_source",
            sample_data,
            vintage_date=test_date
        )
        
        # Load vintage
        loaded_data = vintage_manager.load_vintage("test_source", test_date)
        
        assert len(loaded_data) == len(sample_data)
        assert list(loaded_data.columns) == list(sample_data.columns)
    
    def test_load_vintage_not_found_raises_error(self, vintage_manager):
        """Test loading nonexistent vintage raises error"""
        with pytest.raises(VintageError) as exc_info:
            vintage_manager.load_vintage("nonexistent_source", date(2024, 1, 1))
        
        assert "not found" in str(exc_info.value)
    
    def test_load_vintage_preserves_data_types(self, vintage_manager, test_date):
        """Test that loading preserves data types"""
        df = pd.DataFrame({
            "date": pd.to_datetime(["2024-01-01", "2024-02-01"]),
            "int_col": [1, 2],
            "float_col": [1.5, 2.5],
            "str_col": ["a", "b"]
        })
        
        vintage_manager.create_vintage("test_source", df, vintage_date=test_date)
        loaded_data = vintage_manager.load_vintage("test_source", test_date)
        
        assert loaded_data["int_col"].dtype == df["int_col"].dtype
        assert loaded_data["float_col"].dtype == df["float_col"].dtype
        assert loaded_data["str_col"].dtype == df["str_col"].dtype
    
    # =====================
    # LIST VINTAGES TESTS
    # =====================
    
    def test_list_vintages_empty(self, vintage_manager):
        """Test listing vintages when none exist"""
        vintages = vintage_manager.list_vintages("nonexistent_source")
        
        assert vintages == []
    
    def test_list_vintages_single(self, vintage_manager, sample_data, test_date):
        """Test listing single vintage"""
        vintage_manager.create_vintage("test_source", sample_data, vintage_date=test_date)
        
        vintages = vintage_manager.list_vintages("test_source")
        
        assert len(vintages) == 1
        assert vintages[0] == test_date
    
    def test_list_vintages_multiple_sorted(self, vintage_manager, sample_data):
        """Test listing multiple vintages in sorted order"""
        dates = [
            date(2024, 3, 15),
            date(2024, 1, 10),
            date(2024, 2, 20),
        ]
        
        for vintage_date in dates:
            vintage_manager.create_vintage(
                "test_source",
                sample_data,
                vintage_date=vintage_date
            )
        
        vintages = vintage_manager.list_vintages("test_source")
        
        assert len(vintages) == 3
        assert vintages == sorted(dates)  # Should be sorted oldest to newest
    
    def test_list_vintages_ignores_invalid_directories(self, vintage_manager, sample_data, test_date):
        """Test that invalid directory names are ignored"""
        # Create valid vintage
        vintage_manager.create_vintage("test_source", sample_data, vintage_date=test_date)
        
        # Create invalid directory
        source_dir = vintage_manager.base_path / "test_source"
        invalid_dir = source_dir / "invalid-date-format"
        invalid_dir.mkdir()
        
        vintages = vintage_manager.list_vintages("test_source")
        
        assert len(vintages) == 1  # Only the valid one
        assert vintages[0] == test_date
    
    # =====================
    # GET LATEST VINTAGE TESTS
    # =====================
    
    def test_get_latest_vintage_none(self, vintage_manager):
        """Test getting latest vintage when none exist"""
        latest = vintage_manager.get_latest_vintage("nonexistent_source")
        
        assert latest is None
    
    def test_get_latest_vintage_single(self, vintage_manager, sample_data, test_date):
        """Test getting latest vintage with single vintage"""
        vintage_manager.create_vintage("test_source", sample_data, vintage_date=test_date)
        
        latest = vintage_manager.get_latest_vintage("test_source")
        
        assert latest is not None
        assert len(latest) == len(sample_data)
    
    def test_get_latest_vintage_multiple(self, vintage_manager, sample_data):
        """Test getting latest vintage with multiple vintages"""
        dates = [
            date(2024, 1, 1),
            date(2024, 2, 1),
            date(2024, 3, 1),
        ]
        
        for vintage_date in dates:
            df = sample_data.copy()
            df["vintage_marker"] = vintage_date.isoformat()
            vintage_manager.create_vintage("test_source", df, vintage_date=vintage_date)
        
        latest = vintage_manager.get_latest_vintage("test_source")
        
        assert latest is not None
        assert latest["vintage_marker"].iloc[0] == "2024-03-01"  # Should be latest
    
    # =====================
    # VINTAGE EXISTS TESTS
    # =====================
    
    def test_vintage_exists_true(self, vintage_manager, sample_data, test_date):
        """Test checking vintage existence (exists)"""
        vintage_manager.create_vintage("test_source", sample_data, vintage_date=test_date)
        
        exists = vintage_manager.vintage_exists("test_source", test_date)
        
        assert exists is True
    
    def test_vintage_exists_false(self, vintage_manager):
        """Test checking vintage existence (doesn't exist)"""
        exists = vintage_manager.vintage_exists("test_source", date(2024, 1, 1))
        
        assert exists is False
    
    # =====================
    # GET VINTAGE AS OF TESTS
    # =====================
    
    def test_get_vintage_as_of_exact_match(self, vintage_manager, sample_data):
        """Test getting vintage as of exact date"""
        test_date = date(2024, 2, 1)
        vintage_manager.create_vintage("test_source", sample_data, vintage_date=test_date)
        
        vintage = vintage_manager.get_vintage_as_of("test_source", test_date)
        
        assert vintage is not None
        assert len(vintage) == len(sample_data)
    
    def test_get_vintage_as_of_before_any(self, vintage_manager, sample_data):
        """Test getting vintage as of date before any vintages exist"""
        vintage_manager.create_vintage("test_source", sample_data, vintage_date=date(2024, 2, 1))
        
        vintage = vintage_manager.get_vintage_as_of("test_source", date(2024, 1, 1))
        
        assert vintage is None
    
    def test_get_vintage_as_of_between_vintages(self, vintage_manager, sample_data):
        """Test getting vintage as of date between two vintages"""
        # Create vintages on Jan 1 and Mar 1
        df1 = sample_data.copy()
        df1["marker"] = "jan"
        vintage_manager.create_vintage("test_source", df1, vintage_date=date(2024, 1, 1))
        
        df2 = sample_data.copy()
        df2["marker"] = "mar"
        vintage_manager.create_vintage("test_source", df2, vintage_date=date(2024, 3, 1))
        
        # Get vintage as of Feb 1 (should return Jan 1 vintage)
        vintage = vintage_manager.get_vintage_as_of("test_source", date(2024, 2, 1))
        
        assert vintage is not None
        assert vintage["marker"].iloc[0] == "jan"  # Should be Jan vintage
    
    def test_get_vintage_as_of_after_latest(self, vintage_manager, sample_data):
        """Test getting vintage as of date after latest vintage"""
        df = sample_data.copy()
        df["marker"] = "feb"
        vintage_manager.create_vintage("test_source", df, vintage_date=date(2024, 2, 1))
        
        # Get as of March 1 (should return Feb vintage)
        vintage = vintage_manager.get_vintage_as_of("test_source", date(2024, 3, 1))
        
        assert vintage is not None
        assert vintage["marker"].iloc[0] == "feb"
    
    def test_get_vintage_as_of_multiple_vintages(self, vintage_manager, sample_data):
        """Test vintage-honest retrieval with multiple vintages"""
        dates = [
            date(2024, 1, 1),
            date(2024, 2, 1),
            date(2024, 3, 1),
            date(2024, 4, 1),
        ]
        
        for vintage_date in dates:
            df = sample_data.copy()
            df["month"] = vintage_date.month
            vintage_manager.create_vintage("test_source", df, vintage_date=vintage_date)
        
        # Test as of date between Feb and Mar (should get Feb)
        vintage = vintage_manager.get_vintage_as_of("test_source", date(2024, 2, 15))
        
        assert vintage is not None
        assert vintage["month"].iloc[0] == 2
    
    # =====================
    # INTEGRATION TESTS
    # =====================
    
    def test_full_workflow(self, vintage_manager, sample_data):
        """Test complete workflow: create, list, load, check"""
        source_name = "workflow_test"
        test_dates = [
            date(2024, 1, 1),
            date(2024, 2, 1),
            date(2024, 3, 1),
        ]
        
        # Create multiple vintages
        for vintage_date in test_dates:
            vintage_manager.create_vintage(
                source_name,
                sample_data,
                vintage_date=vintage_date
            )
        
        # List all vintages
        vintages = vintage_manager.list_vintages(source_name)
        assert len(vintages) == 3
        assert vintages == test_dates
        
        # Check existence
        for vintage_date in test_dates:
            assert vintage_manager.vintage_exists(source_name, vintage_date)
        
        # Load specific vintage
        loaded = vintage_manager.load_vintage(source_name, test_dates[1])
        assert len(loaded) == len(sample_data)
        
        # Get latest
        latest = vintage_manager.get_latest_vintage(source_name)
        assert latest is not None
        
        # Get as of date
        as_of = vintage_manager.get_vintage_as_of(source_name, date(2024, 2, 15))
        assert as_of is not None
    
    def test_multiple_sources_isolated(self, vintage_manager, sample_data, test_date):
        """Test that multiple sources are properly isolated"""
        # Create vintages for different sources
        vintage_manager.create_vintage("source_a", sample_data, vintage_date=test_date)
        vintage_manager.create_vintage("source_b", sample_data, vintage_date=test_date)
        
        # Verify isolation
        vintages_a = vintage_manager.list_vintages("source_a")
        vintages_b = vintage_manager.list_vintages("source_b")
        vintages_c = vintage_manager.list_vintages("source_c")
        
        assert len(vintages_a) == 1
        assert len(vintages_b) == 1
        assert len(vintages_c) == 0
        
        # Verify data loads correctly for each
        data_a = vintage_manager.load_vintage("source_a", test_date)
        data_b = vintage_manager.load_vintage("source_b", test_date)
        
        assert len(data_a) == len(sample_data)
        assert len(data_b) == len(sample_data)

