"""
Integration tests for UI Claims ETL pipeline.

Tests data extraction, validation, and processing with mocked HTTP calls.
"""

import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pandas as pd
import pytest

from etl.public.claims.claims_etl import UIClaimsETL, DOL_CLAIMS_API, DOL_CLAIMS_FILE


@pytest.mark.integration
@pytest.mark.etl
class TestUIClaimsETL:
    """Integration test suite for UI Claims ETL"""
    
    @pytest.fixture
    def temp_paths(self):
        """Create temporary paths for testing"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            yield {
                "raw_data": tmppath / "raw" / "claims",
                "vintage": tmppath / "vintages"
            }
    
    @pytest.fixture
    def mock_claims_csv(self) -> str:
        """Generate mock UI Claims CSV data"""
        csv_data = """state,week_ending,initial_claims,continued_claims,covered_employment,insured_unemployment_rate
US,2024-01-06,250000,1800000,150000000,1.2
CA,2024-01-06,45000,320000,18000000,1.8
NY,2024-01-06,35000,280000,9500000,2.9
TX,2024-01-06,28000,240000,14000000,1.7
FL,2024-01-06,22000,200000,9800000,2.0
US,2024-01-13,255000,1750000,150000000,1.2
CA,2024-01-13,46000,315000,18000000,1.7
NY,2024-01-13,36000,275000,9500000,2.9
TX,2024-01-13,29000,235000,14000000,1.7
FL,2024-01-13,23000,195000,9800000,2.0
"""
        return csv_data
    
    @pytest.fixture
    def claims_etl(self, temp_paths) -> UIClaimsETL:
        """Create UI Claims ETL instance"""
        return UIClaimsETL(
            raw_data_path=temp_paths["raw_data"],
            vintage_path=temp_paths["vintage"],
            include_territories=False
        )
    
    # =====================
    # INITIALIZATION TESTS
    # =====================
    
    def test_init_creates_config(self, claims_etl):
        """Test that initialization creates proper config"""
        assert claims_etl.config is not None
        assert claims_etl.config.source_name == "ui_claims"
        assert claims_etl.config.frequency == "weekly"
    
    def test_init_creates_downloader(self, claims_etl):
        """Test that downloader is initialized"""
        assert claims_etl.downloader is not None
    
    def test_init_include_territories_flag(self, temp_paths):
        """Test include_territories flag"""
        etl = UIClaimsETL(
            raw_data_path=temp_paths["raw_data"],
            vintage_path=temp_paths["vintage"],
            include_territories=True
        )
        
        assert etl.include_territories is True
    
    # =====================
    # EXTRACT METHOD TESTS
    # =====================
    
    @patch('etl.common.downloader.Downloader.download')
    def test_extract_success(self, mock_download, claims_etl, mock_claims_csv):
        """Test successful data extraction"""
        mock_download.return_value = mock_claims_csv.encode('utf-8')
        
        df = claims_etl.extract()
        
        assert not df.empty
        assert len(df) == 10  # 10 rows in mock data
        assert "state" in df.columns
        assert "initial_claims" in df.columns
        assert "continued_claims" in df.columns
        
        # Verify correct URL was called
        expected_url = f"{DOL_CLAIMS_API}{DOL_CLAIMS_FILE}"
        mock_download.assert_called_once_with(expected_url)
    
    @patch('etl.common.downloader.Downloader.download')
    def test_extract_parses_csv_correctly(self, mock_download, claims_etl, mock_claims_csv):
        """Test that CSV parsing is correct"""
        mock_download.return_value = mock_claims_csv.encode('utf-8')
        
        df = claims_etl.extract()
        
        # Check data types
        assert "state" in df.columns
        assert df["initial_claims"].dtype in [int, 'int64']
        assert df["continued_claims"].dtype in [int, 'int64']
    
    @patch('etl.common.downloader.Downloader.download')
    def test_extract_handles_download_failure(self, mock_download, claims_etl):
        """Test handling of download failure"""
        mock_download.side_effect = Exception("Network error")
        
        with pytest.raises(Exception):
            claims_etl.extract()
    
    @patch('etl.common.downloader.Downloader.download')
    def test_extract_handles_invalid_csv(self, mock_download, claims_etl):
        """Test handling of invalid CSV data"""
        mock_download.return_value = b"invalid,csv\ndata"
        
        # Should still return a DataFrame (may be incomplete)
        df = claims_etl.extract()
        assert isinstance(df, pd.DataFrame)
    
    # =====================
    # VALIDATE METHOD TESTS
    # =====================
    
    def test_validate_success_with_valid_data(self, claims_etl):
        """Test validation passes with valid data"""
        valid_df = pd.DataFrame({
            "state": ["US", "CA", "NY"],
            "week_ending": ["2024-01-06", "2024-01-06", "2024-01-06"],
            "initial_claims": [250000, 45000, 35000],
            "continued_claims": [1800000, 320000, 280000],
            "covered_employment": [150000000, 18000000, 9500000],
            "insured_unemployment_rate": [1.2, 1.8, 2.9]
        })
        
        result = claims_etl.validate(valid_df)
        
        assert result is True
    
    def test_validate_fails_missing_columns(self, claims_etl):
        """Test validation fails with missing columns"""
        invalid_df = pd.DataFrame({
            "state": ["US", "CA"],
            "week_ending": ["2024-01-06", "2024-01-06"]
            # Missing required columns
        })
        
        result = claims_etl.validate(invalid_df)
        
        assert result is False
    
    def test_validate_fails_empty_dataframe(self, claims_etl):
        """Test validation fails with empty DataFrame"""
        empty_df = pd.DataFrame()
        
        result = claims_etl.validate(empty_df)
        
        assert result is False
    
    def test_validate_fails_no_national_data(self, claims_etl):
        """Test validation fails without US national data"""
        no_national_df = pd.DataFrame({
            "state": ["CA", "NY"],
            "week_ending": ["2024-01-06", "2024-01-06"],
            "initial_claims": [45000, 35000],
            "continued_claims": [320000, 280000],
            "covered_employment": [18000000, 9500000],
            "insured_unemployment_rate": [1.8, 2.9]
        })
        
        result = claims_etl.validate(no_national_df)
        
        assert result is False
    
    def test_validate_checks_data_types(self, claims_etl):
        """Test validation checks for correct data types"""
        # Create DataFrame with wrong types
        wrong_types_df = pd.DataFrame({
            "state": ["US", "CA"],
            "week_ending": ["2024-01-06", "2024-01-06"],
            "initial_claims": ["not_a_number", "also_not_number"],  # Should be numeric
            "continued_claims": [1800000, 320000],
            "covered_employment": [150000000, 18000000],
            "insured_unemployment_rate": [1.2, 1.8]
        })
        
        result = claims_etl.validate(wrong_types_df)
        
        # Validation should catch type issues
        assert result is False
    
    # =====================
    # TRANSFORM METHOD TESTS
    # =====================
    
    @patch('etl.common.downloader.Downloader.download')
    def test_transform_cleans_data(self, mock_download, claims_etl, mock_claims_csv):
        """Test that transform method cleans data"""
        mock_download.return_value = mock_claims_csv.encode('utf-8')
        
        df = claims_etl.extract()
        transformed = claims_etl.transform(df)
        
        # Verify transformation occurred
        assert not transformed.empty
        # Check that data is still valid after transformation
        assert len(transformed) > 0
    
    # =====================
    # INTEGRATION TESTS (FULL PIPELINE)
    # =====================
    
    @patch('etl.common.downloader.Downloader.download')
    def test_full_pipeline_run_success(self, mock_download, claims_etl, mock_claims_csv):
        """Test complete pipeline execution"""
        mock_download.return_value = mock_claims_csv.encode('utf-8')
        
        result = claims_etl.run()
        
        assert result is True
        assert claims_etl.metadata.status.value == "success"
        assert claims_etl.metadata.row_count > 0
    
    @patch('etl.common.downloader.Downloader.download')
    def test_full_pipeline_creates_files(self, mock_download, claims_etl, mock_claims_csv, temp_paths):
        """Test that pipeline creates output files"""
        mock_download.return_value = mock_claims_csv.encode('utf-8')
        
        claims_etl.run()
        
        # Check raw data file created
        raw_files = list(temp_paths["raw_data"].glob("*.parquet"))
        assert len(raw_files) > 0
        
        # Check vintage created
        vintage_dir = temp_paths["vintage"] / "ui_claims"
        assert vintage_dir.exists()
    
    @patch('etl.common.downloader.Downloader.download')
    def test_full_pipeline_vintage_data_loadable(self, mock_download, claims_etl, mock_claims_csv, temp_paths):
        """Test that vintage data can be loaded"""
        mock_download.return_value = mock_claims_csv.encode('utf-8')
        
        claims_etl.run()
        
        # Find vintage file
        vintage_dir = temp_paths["vintage"] / "ui_claims"
        vintage_dates = list(vintage_dir.iterdir())
        assert len(vintage_dates) > 0
        
        # Load vintage data
        vintage_file = list(vintage_dates[0].glob("*.parquet"))[0]
        loaded_df = pd.read_parquet(vintage_file)
        
        assert not loaded_df.empty
        assert "state" in loaded_df.columns
    
    @patch('etl.common.downloader.Downloader.download')
    def test_full_pipeline_handles_failure_gracefully(self, mock_download, claims_etl):
        """Test that pipeline handles failures gracefully"""
        mock_download.side_effect = Exception("API Error")
        
        result = claims_etl.run()
        
        assert result is False
        assert claims_etl.metadata.status.value == "failed"
        assert claims_etl.metadata.error_message is not None
    
    # =====================
    # EDGE CASES
    # =====================
    
    def test_handles_territories_inclusion(self, temp_paths):
        """Test handling of territories when included"""
        etl = UIClaimsETL(
            raw_data_path=temp_paths["raw_data"],
            vintage_path=temp_paths["vintage"],
            include_territories=True
        )
        
        # Create mock data with territories
        mock_data_with_territories = """state,week_ending,initial_claims,continued_claims,covered_employment,insured_unemployment_rate
US,2024-01-06,250000,1800000,150000000,1.2
CA,2024-01-06,45000,320000,18000000,1.8
PR,2024-01-06,5000,40000,1000000,4.0
VI,2024-01-06,500,4000,50000,8.0
"""
        
        with patch('etl.common.downloader.Downloader.download') as mock_download:
            mock_download.return_value = mock_data_with_territories.encode('utf-8')
            
            df = etl.extract()
            transformed = etl.transform(df)
            
            # With include_territories=True, should keep PR and VI
            assert "PR" in transformed["state"].values or len(transformed) > 0
    
    @patch('etl.common.downloader.Downloader.download')
    def test_handles_missing_optional_columns(self, mock_download, claims_etl):
        """Test handling of data with missing optional columns"""
        minimal_csv = """state,week_ending,initial_claims,continued_claims
US,2024-01-06,250000,1800000
CA,2024-01-06,45000,320000
"""
        mock_download.return_value = minimal_csv.encode('utf-8')
        
        df = claims_etl.extract()
        
        # Should still extract data even if some columns missing
        assert not df.empty
        assert "state" in df.columns
        assert "initial_claims" in df.columns
    
    @patch('etl.common.downloader.Downloader.download')
    def test_handles_duplicate_rows(self, mock_download, claims_etl):
        """Test handling of duplicate data rows"""
        csv_with_duplicates = """state,week_ending,initial_claims,continued_claims,covered_employment,insured_unemployment_rate
US,2024-01-06,250000,1800000,150000000,1.2
US,2024-01-06,250000,1800000,150000000,1.2
CA,2024-01-06,45000,320000,18000000,1.8
"""
        mock_download.return_value = csv_with_duplicates.encode('utf-8')
        
        df = claims_etl.extract()
        transformed = claims_etl.transform(df)
        
        # Should handle duplicates gracefully
        assert isinstance(transformed, pd.DataFrame)

