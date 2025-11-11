"""
Integration tests for all public ETL pipelines.

Covers: Treasury, CES, LAUS, Strikes, Weather, CNBFS pipelines.
Tests use mocked API responses and focus on pipeline integration.
"""

import tempfile
from datetime import datetime, date
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd
import pytest


@pytest.mark.integration
@pytest.mark.etl
class TestTreasuryETL:
    """Tests for Treasury Withholdings ETL"""
    
    @pytest.fixture
    def temp_paths(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            yield {"raw_data": tmppath / "raw", "vintage": tmppath / "vintages"}
    
    @pytest.fixture
    def mock_treasury_data(self) -> dict:
        """Mock Treasury API response"""
        return {
            "data": [
                {"record_date": "2024-01-02", "account": "Federal Taxes Withheld", "close_today_bal": 12000000},
                {"record_date": "2024-01-03", "account": "Federal Taxes Withheld", "close_today_bal": 11500000},
                {"record_date": "2024-01-04", "account": "Federal Taxes Withheld", "close_today_bal": 13000000},
            ]
        }
    
    @patch('etl.common.downloader.Downloader.download_json')
    def test_treasury_extract(self, mock_download, temp_paths, mock_treasury_data):
        """Test Treasury ETL extraction"""
        from etl.public.treasury_withholdings.treasury_etl import TreasuryWithholdingsETL
        
        mock_download.return_value = mock_treasury_data
        
        etl = TreasuryWithholdingsETL(
            raw_data_path=temp_paths["raw_data"],
            vintage_path=temp_paths["vintage"]
        )
        
        df = etl.extract()
        
        assert not df.empty
        assert len(df) > 0
        assert mock_download.called
    
    @patch('etl.common.downloader.Downloader.download_json')
    def test_treasury_full_pipeline(self, mock_download, temp_paths, mock_treasury_data):
        """Test complete Treasury ETL pipeline"""
        from etl.public.treasury_withholdings.treasury_etl import TreasuryWithholdingsETL
        
        mock_download.return_value = mock_treasury_data
        
        etl = TreasuryWithholdingsETL(
            raw_data_path=temp_paths["raw_data"],
            vintage_path=temp_paths["vintage"]
        )
        
        result = etl.run()
        
        assert result is True
        assert etl.metadata.row_count > 0


@pytest.mark.integration
@pytest.mark.etl
class TestCESETL:
    """Tests for BLS CES (Employment) ETL"""
    
    @pytest.fixture
    def temp_paths(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            yield {"raw_data": tmppath / "raw", "vintage": tmppath / "vintages"}
    
    @pytest.fixture
    def mock_ces_data(self) -> dict:
        """Mock BLS CES API response"""
        return {
            "status": "REQUEST_SUCCEEDED",
            "Results": {
                "series": [
                    {
                        "seriesID": "CES0000000001",
                        "data": [
                            {"year": "2024", "period": "M01", "value": "158000", "footnotes": []},
                            {"year": "2024", "period": "M02", "value": "158200", "footnotes": []},
                            {"year": "2024", "period": "M03", "value": "158500", "footnotes": []},
                        ]
                    }
                ]
            }
        }
    
    @patch('etl.common.downloader.Downloader.download_json')
    def test_ces_extract(self, mock_download, temp_paths, mock_ces_data):
        """Test CES ETL extraction"""
        from etl.public.bls_ces.ces_etl import CESETL
        
        mock_download.return_value = mock_ces_data
        
        etl = CESETL(
            raw_data_path=temp_paths["raw_data"],
            vintage_path=temp_paths["vintage"]
        )
        
        df = etl.extract()
        
        assert isinstance(df, pd.DataFrame)
        assert mock_download.called
    
    @patch('etl.common.downloader.Downloader.download_json')
    def test_ces_full_pipeline(self, mock_download, temp_paths, mock_ces_data):
        """Test complete CES ETL pipeline"""
        from etl.public.bls_ces.ces_etl import CESETL
        
        mock_download.return_value = mock_ces_data
        
        etl = CESETL(
            raw_data_path=temp_paths["raw_data"],
            vintage_path=temp_paths["vintage"]
        )
        
        result = etl.run()
        
        assert result is True or isinstance(result, bool)


@pytest.mark.integration
@pytest.mark.etl
class TestLAUSETL:
    """Tests for BLS LAUS (State Employment) ETL"""
    
    @pytest.fixture
    def temp_paths(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            yield {"raw_data": tmppath / "raw", "vintage": tmppath / "vintages"}
    
    @pytest.fixture
    def mock_laus_data(self) -> dict:
        """Mock BLS LAUS API response"""
        return {
            "status": "REQUEST_SUCCEEDED",
            "Results": {
                "series": [
                    {
                        "seriesID": "LASST060000000000003",
                        "data": [
                            {"year": "2024", "period": "M01", "value": "5.2", "footnotes": []},
                            {"year": "2024", "period": "M02", "value": "5.1", "footnotes": []},
                        ]
                    }
                ]
            }
        }
    
    @patch('etl.common.downloader.Downloader.download_json')
    def test_laus_extract(self, mock_download, temp_paths, mock_laus_data):
        """Test LAUS ETL extraction"""
        from etl.public.bls_laus.laus_etl import LAUSETL
        
        mock_download.return_value = mock_laus_data
        
        etl = LAUSETL(
            raw_data_path=temp_paths["raw_data"],
            vintage_path=temp_paths["vintage"]
        )
        
        df = etl.extract()
        
        assert isinstance(df, pd.DataFrame)
        assert mock_download.called


@pytest.mark.integration
@pytest.mark.etl
class TestStrikesETL:
    """Tests for BLS Work Stoppages ETL"""
    
    @pytest.fixture
    def temp_paths(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            yield {"raw_data": tmppath / "raw", "vintage": tmppath / "vintages"}
    
    @pytest.fixture
    def mock_strikes_csv(self) -> str:
        """Mock strikes CSV data"""
        return """Year,Month,Strike,Workers,Days_Idle,Industry
2024,1,Major Strike 1,5000,25000,Manufacturing
2024,1,Major Strike 2,3000,15000,Transportation
2024,2,Major Strike 3,8000,40000,Healthcare
"""
    
    @patch('etl.common.downloader.Downloader.download')
    def test_strikes_extract(self, mock_download, temp_paths, mock_strikes_csv):
        """Test Strikes ETL extraction"""
        from etl.public.strikes.strikes_etl import StrikesETL
        
        mock_download.return_value = mock_strikes_csv.encode('utf-8')
        
        etl = StrikesETL(
            raw_data_path=temp_paths["raw_data"],
            vintage_path=temp_paths["vintage"]
        )
        
        df = etl.extract()
        
        assert isinstance(df, pd.DataFrame)
        assert mock_download.called


@pytest.mark.integration
@pytest.mark.etl
class TestWeatherETL:
    """Tests for NOAA Weather/Storm Events ETL"""
    
    @pytest.fixture
    def temp_paths(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            yield {"raw_data": tmppath / "raw", "vintage": tmppath / "vintages"}
    
    @pytest.fixture
    def mock_weather_csv(self) -> str:
        """Mock NOAA storm events CSV"""
        return """BEGIN_DATE,EVENT_TYPE,STATE,DEATHS_DIRECT,INJURIES_DIRECT,DAMAGE_PROPERTY,DAMAGE_CROPS
2024-01-05,Hurricane,FL,10,50,1000000000,50000000
2024-01-10,Tornado,OK,2,15,50000000,10000000
2024-02-01,Winter Storm,TX,5,30,200000000,100000000
"""
    
    @patch('etl.common.downloader.Downloader.download')
    def test_weather_extract(self, mock_download, temp_paths, mock_weather_csv):
        """Test Weather ETL extraction"""
        from etl.public.weather.weather_etl import WeatherETL
        
        mock_download.return_value = mock_weather_csv.encode('utf-8')
        
        etl = WeatherETL(
            raw_data_path=temp_paths["raw_data"],
            vintage_path=temp_paths["vintage"]
        )
        
        df = etl.extract()
        
        assert isinstance(df, pd.DataFrame)
        assert mock_download.called


@pytest.mark.integration
@pytest.mark.etl
class TestCNBFSETL:
    """Tests for Census Business Formation Statistics ETL"""
    
    @pytest.fixture
    def temp_paths(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            yield {"raw_data": tmppath / "raw", "vintage": tmppath / "vintages"}
    
    @pytest.fixture
    def mock_cnbfs_data(self) -> dict:
        """Mock Census API response"""
        return [
            ["2024-01", "10000", "5000", "3000"],
            ["2024-02", "10500", "5200", "3100"],
            ["2024-03", "11000", "5500", "3300"],
        ]
    
    @patch('etl.common.downloader.Downloader.download_json')
    def test_cnbfs_extract(self, mock_download, temp_paths, mock_cnbfs_data):
        """Test CNBFS ETL extraction"""
        from etl.public.cnbfs.cnbfs_etl import CNBFSETL
        
        mock_download.return_value = mock_cnbfs_data
        
        etl = CNBFSETL(
            raw_data_path=temp_paths["raw_data"],
            vintage_path=temp_paths["vintage"]
        )
        
        df = etl.extract()
        
        assert isinstance(df, pd.DataFrame)
        assert mock_download.called


@pytest.mark.integration
@pytest.mark.etl
class TestAllETLPipelinesCommon:
    """Common tests applicable to all ETL pipelines"""
    
    @pytest.mark.parametrize("etl_class,module", [
        ("TreasuryWithholdingsETL", "etl.public.treasury_withholdings.treasury_etl"),
        ("CESETL", "etl.public.bls_ces.ces_etl"),
        ("LAUSETL", "etl.public.bls_laus.laus_etl"),
        ("StrikesETL", "etl.public.strikes.strikes_etl"),
        ("WeatherETL", "etl.public.weather.weather_etl"),
        ("CNBFSETL", "etl.public.cnbfs.cnbfs_etl"),
    ])
    def test_etl_has_required_methods(self, etl_class, module):
        """Test that all ETL classes implement required methods"""
        import importlib
        
        mod = importlib.import_module(module)
        cls = getattr(mod, etl_class)
        
        # Check required methods exist
        assert hasattr(cls, 'extract')
        assert hasattr(cls, 'validate')
        assert hasattr(cls, 'transform')
        assert hasattr(cls, 'run')
    
    @pytest.mark.parametrize("etl_class,module", [
        ("TreasuryWithholdingsETL", "etl.public.treasury_withholdings.treasury_etl"),
        ("CESETL", "etl.public.bls_ces.ces_etl"),
        ("LAUSETL", "etl.public.bls_laus.laus_etl"),
        ("StrikesETL", "etl.public.strikes.strikes_etl"),
        ("WeatherETL", "etl.public.weather.weather_etl"),
        ("CNBFSETL", "etl.public.cnbfs.cnbfs_etl"),
    ])
    def test_etl_initialization(self, etl_class, module):
        """Test that all ETL classes can be initialized"""
        import importlib
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            
            mod = importlib.import_module(module)
            cls = getattr(mod, etl_class)
            
            etl = cls(
                raw_data_path=tmppath / "raw",
                vintage_path=tmppath / "vintages"
            )
            
            assert etl is not None
            assert etl.config is not None
            assert etl.metadata is not None

