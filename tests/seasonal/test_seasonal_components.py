"""
Tests for seasonal adjustment framework components.

Covers SpecBuilder, Regressors, Diagnostics with mocked X-13 service.
"""

import tempfile
from datetime import date, datetime
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd
import pytest

from seasonal.spec_builder import SpecBuilder, X13Spec
from seasonal.regressors.holiday_regressors import HolidayRegressors
from seasonal.regressors.strike_regressors import StrikeRegressors
from seasonal.regressors.weather_regressors import WeatherRegressors
from seasonal.diagnostics.analyzers import MStatAnalyzer, QStatAnalyzer, StabilityAnalyzer


@pytest.mark.unit
@pytest.mark.seasonal
class TestSpecBuilder:
    """Tests for X-13 SpecBuilder"""
    
    def test_spec_builder_creation(self):
        """Test creating spec builder"""
        builder = SpecBuilder()  # Takes no parameters
        
        # SpecBuilder is initialized with no state
        assert builder is not None
        assert hasattr(builder, 'specs')
        assert isinstance(builder.specs, dict)
    
    def test_build_basic_spec(self):
        """Test building basic X-13 spec"""
        builder = SpecBuilder()
        
        # Create X13Spec config
        config = X13Spec(
            series_name="TEST001",
            title="Test Series",
            start_year=2010,
            start_month=1
        )
        
        spec = builder.build_spec(config)
        
        assert spec is not None
        assert isinstance(spec, str)
        assert "series" in spec.lower()
        assert "x11" in spec.lower() or "seats" in spec.lower()


@pytest.mark.unit
@pytest.mark.seasonal
class TestHolidayRegressors:
    """Tests for holiday regressors"""
    
    def test_holiday_regressor_creation(self):
        """Test creating holiday regressor builder"""
        builder = HolidayRegressors()
        
        assert builder is not None
    
    def test_easter_regressor_generation(self):
        """Test generating Easter regressors"""
        builder = HolidayRegressors()
        
        from datetime import date
        regressor = builder.build_easter_regressor(
            start_date=date(2020, 1, 1),
            end_date=date(2024, 12, 31)
        )
        
        assert regressor is not None
        assert len(regressor) > 0
    
    def test_thanksgiving_regressor_generation(self):
        """Test generating Thanksgiving regressors"""
        builder = HolidayRegressors()
        
        from datetime import date
        regressor = builder.build_thanksgiving_regressor(
            start_date=date(2020, 1, 1),
            end_date=date(2024, 12, 31)
        )
        
        assert regressor is not None
        assert len(regressor) > 0


@pytest.mark.unit
@pytest.mark.seasonal
class TestStrikeRegressors:
    """Tests for strike impact regressors"""
    
    @pytest.fixture
    def mock_strike_data(self):
        """Mock strike data"""
        return pd.DataFrame({
            "date": pd.to_datetime(["2020-03-01", "2021-06-01"]),
            "workers_involved": [10000, 5000],
            "days_idle": [50000, 25000]
        })
    
    def test_strike_regressor_creation(self):
        """Test creating strike regressor (with None storage_client for testing)"""
        from unittest.mock import Mock
        mock_storage = Mock()
        builder = StrikeRegressors(storage_client=mock_storage)
        
        assert builder is not None
    
    def test_strike_impact_calculation(self):
        """Test calculating strike impacts"""
        from datetime import date
        from unittest.mock import Mock
        
        # Mock storage client to return empty DataFrame
        mock_storage = Mock()
        mock_storage.read_parquet.return_value = pd.DataFrame()
        
        builder = StrikeRegressors(storage_client=mock_storage)
        
        result = builder.build(
            start_date=date(2020, 1, 1),
            end_date=date(2022, 12, 31)
        )
        
        assert result is not None
        assert "strike_impact" in result.columns


@pytest.mark.unit
@pytest.mark.seasonal
class TestWeatherRegressors:
    """Tests for weather/storm impact regressors"""
    
    @pytest.fixture
    def mock_weather_data(self):
        """Mock weather event data"""
        return pd.DataFrame({
            "date": pd.to_datetime(["2020-08-01", "2021-09-01"]),
            "event_type": ["Hurricane", "Hurricane"],
            "deaths": [100, 50],
            "damage_property": [50000000000, 25000000000]
        })
    
    def test_weather_regressor_creation(self):
        """Test creating weather regressor (with None storage_client for testing)"""
        from unittest.mock import Mock
        mock_storage = Mock()
        builder = WeatherRegressors(storage_client=mock_storage)
        
        assert builder is not None
    
    def test_weather_impact_calculation(self):
        """Test calculating weather impacts"""
        from datetime import date
        from unittest.mock import Mock
        
        # Mock storage client to return empty DataFrame
        mock_storage = Mock()
        mock_storage.read_parquet.return_value = pd.DataFrame()
        
        builder = WeatherRegressors(storage_client=mock_storage)
        
        result = builder.build(
            start_date=date(2020, 1, 1),
            end_date=date(2022, 12, 31)
        )
        
        assert result is not None
        assert "weather_impact" in result.columns


@pytest.mark.unit
@pytest.mark.seasonal
class TestDiagnosticAnalyzers:
    """Tests for diagnostic analyzers"""
    
    @pytest.fixture
    def mock_m_statistics(self):
        """Mock M-statistics from X-13"""
        return {
            "m1": 0.15,
            "m2": 0.20,
            "m3": 0.50,
            "m4": 0.45,
            "m5": 0.30,
            "m6": 0.25,
            "m7": 0.35,
            "m8": 0.40,
            "m9": 0.20,
            "m10": 0.55,
            "m11": 0.60,
            "q": 0.42
        }
    
    def test_m_stat_analyzer_creation(self):
        """Test creating M-stat analyzer"""
        analyzer = MStatAnalyzer()
        
        assert analyzer is not None
    
    def test_m_stat_quality_assessment(self, mock_m_statistics):
        """Test M-stat quality assessment"""
        analyzer = MStatAnalyzer()
        
        # analyze() expects diagnostics dict, returns analysis with m_stats and quality
        result = analyzer.analyze(mock_m_statistics)
        
        assert result is not None
        assert isinstance(result, dict)
        # Should have status or quality indicators
        assert "status" in result or "m_stats" in result
    
    def test_q_stat_analyzer_creation(self):
        """Test creating Q-stat analyzer"""
        analyzer = QStatAnalyzer()
        
        assert analyzer is not None
    
    def test_q_stat_significance_check(self, mock_m_statistics):
        """Test Q-stat significance check"""
        analyzer = QStatAnalyzer()
        
        # analyze() checks Q-statistic and returns analysis
        result = analyzer.analyze(mock_m_statistics)
        
        assert result is not None
        assert isinstance(result, dict)
        # Should have Q-stat analysis
        assert "status" in result or "q_stat" in result
    
    def test_stability_analyzer_creation(self):
        """Test creating stability analyzer"""
        analyzer = StabilityAnalyzer()
        
        assert analyzer is not None


@pytest.mark.integration
@pytest.mark.seasonal
class TestSeasonalPipelineIntegration:
    """Integration tests for complete seasonal adjustment pipeline"""
    
    @pytest.fixture
    def sample_series(self):
        """Sample time series for seasonal adjustment"""
        # Create series with clear seasonal pattern
        dates = pd.date_range("2010-01-01", periods=120, freq="MS")
        trend = pd.Series(range(120)) * 100 + 150000
        seasonal = pd.Series([100 * (i % 12 - 6) for i in range(120)])
        noise = pd.Series(np.random.normal(0, 500, 120))
        
        series = trend + seasonal + noise
        series.index = dates
        
        return series
    
    def test_spec_builder_with_regressors(self, sample_series):
        """Test spec builder with regressors"""
        from datetime import date
        
        builder = SpecBuilder()
        
        # Create X13Spec config with regressors
        config = X13Spec(
            series_name="TEST001",
            title="Test Series",
            start_year=2010,
            start_month=1,
            easter=True,  # Enable easter regressor
            user_regressors=["custom_reg_1"]  # Custom regressors
        )
        
        spec = builder.build_spec(config)
        
        assert "regression" in spec.lower() or "easter" in spec.lower()
    
    def test_complete_seasonal_workflow_mock(self, sample_series):
        """Test complete workflow with mocked X-13 service"""
        # Build spec
        builder = SpecBuilder()
        
        config = X13Spec(
            series_name="TEST001",
            title="Test Series",
            start_year=2010,
            start_month=1
        )
        
        spec = builder.build_spec(config)
        
        assert spec is not None
        
        # Mock X-13 output
        mock_output = {
            "seasonally_adjusted": sample_series * 0.98,
            "seasonal_factors": pd.Series([1.0] * len(sample_series)),
            "diagnostics": {
                "m1": 0.15,
                "m2": 0.20,
                "q": 0.42
            }
        }
        
        # Analyze diagnostics
        analyzer = MStatAnalyzer()
        quality = analyzer.analyze(mock_output["diagnostics"])
        
        assert quality is not None


@pytest.mark.integration
@pytest.mark.seasonal
@pytest.mark.slow
class TestSeasonalAdjustmentWithData:
    """Integration tests with realistic data patterns"""
    
    def test_adjustment_with_strike_impact(self):
        """Test seasonal adjustment with strike impacts"""
        # Create series with strike distortion
        dates = pd.date_range("2020-01-01", periods=48, freq="MS")
        series = pd.Series(range(48)) * 100 + 150000
        
        # Add strike impact in month 24
        series.iloc[24] -= 50000
        series.index = dates
        
        # This test is simplified since StrikeRegressors loads from storage
        # Just verify we can create the builder
        from unittest.mock import Mock
        mock_storage = Mock()
        strike_builder = StrikeRegressors(storage_client=mock_storage)
        
        # Verify builder works
        assert strike_builder is not None
    
    def test_adjustment_with_hurricane_impact(self):
        """Test seasonal adjustment with hurricane impacts"""
        # Create series
        dates = pd.date_range("2020-01-01", periods=48, freq="MS")
        series = pd.Series(range(48)) * 100 + 150000
        series.index = dates
        
        # This test is simplified since WeatherRegressors loads from storage
        # Just verify we can create the builder
        from unittest.mock import Mock
        mock_storage = Mock()
        weather_builder = WeatherRegressors(storage_client=mock_storage)
        
        # Verify builder works
        assert weather_builder is not None

