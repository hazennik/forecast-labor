"""
Tests for frequency transformations.

Tests frequency conversion, calendar adjustments, scaling, and winsorization.
All transformations must be deterministic and vintage-aware.
"""

import numpy as np
import pandas as pd
import pytest
from datetime import datetime, timedelta


class TestFrequencyConverter:
    """Test frequency conversion (daily → weekly → monthly)."""

    @pytest.fixture
    def daily_series(self) -> pd.Series:
        """Create daily time series."""
        dates = pd.date_range("2024-01-01", periods=90, freq="D")
        values = np.arange(90, dtype=float) + np.random.RandomState(42).randn(90) * 0.1
        return pd.Series(values, index=dates, name="daily_data")

    @pytest.fixture
    def weekly_series(self) -> pd.Series:
        """Create weekly time series."""
        dates = pd.date_range("2024-01-01", periods=12, freq="W")
        values = np.arange(12, dtype=float) + np.random.RandomState(42).randn(12) * 0.1
        return pd.Series(values, index=dates, name="weekly_data")

    def test_converter_initialization(self):
        """Test FrequencyConverter initialization."""
        from features.transforms.frequency import FrequencyConverter

        converter = FrequencyConverter(source_freq="D", target_freq="W")
        assert converter.source_freq == "D"
        assert converter.target_freq == "W"

    def test_daily_to_weekly_mean(self, daily_series):
        """Test daily to weekly conversion with mean aggregation."""
        from features.transforms.frequency import FrequencyConverter

        converter = FrequencyConverter(
            source_freq="D", target_freq="W", agg_method="mean"
        )
        result = converter.convert(daily_series)

        # Should have fewer observations
        assert len(result) <= len(daily_series)
        # Should have weekly frequency
        assert result.index.freq is not None or pd.infer_freq(result.index) in [
            "W",
            "W-SUN",
        ]

    def test_daily_to_weekly_sum(self, daily_series):
        """Test daily to weekly conversion with sum aggregation."""
        from features.transforms.frequency import FrequencyConverter

        converter = FrequencyConverter(
            source_freq="D", target_freq="W", agg_method="sum"
        )
        result = converter.convert(daily_series)

        # Sums should be larger than individual values
        assert len(result) > 0
        assert result.mean() > daily_series.mean()

    def test_daily_to_weekly_last(self, daily_series):
        """Test daily to weekly conversion with last-value method."""
        from features.transforms.frequency import FrequencyConverter

        converter = FrequencyConverter(
            source_freq="D", target_freq="W", agg_method="last"
        )
        result = converter.convert(daily_series)

        assert len(result) > 0
        # Last values should be from original series
        for val in result.values:
            assert val in daily_series.values or np.isnan(val)

    def test_daily_to_monthly_mean(self, daily_series):
        """Test daily to monthly conversion."""
        from features.transforms.frequency import FrequencyConverter

        converter = FrequencyConverter(
            source_freq="D", target_freq="M", agg_method="mean"
        )
        result = converter.convert(daily_series)

        # Should have ~3 monthly observations for 90 days
        assert 2 <= len(result) <= 4
        # Check monthly frequency
        inferred = pd.infer_freq(result.index)
        assert inferred is None or inferred.startswith("M")

    def test_weekly_to_monthly_mean(self, weekly_series):
        """Test weekly to monthly conversion."""
        from features.transforms.frequency import FrequencyConverter

        converter = FrequencyConverter(
            source_freq="W", target_freq="M", agg_method="mean"
        )
        result = converter.convert(weekly_series)

        # Should have ~3 monthly observations for 12 weeks
        assert 2 <= len(result) <= 4

    def test_invalid_frequency_combination_raises_error(self):
        """Test that invalid frequency combinations raise errors."""
        from features.transforms.frequency import FrequencyConverter

        # Cannot go from lower to higher frequency
        with pytest.raises(ValueError, match="Cannot convert from lower to higher"):
            FrequencyConverter(source_freq="M", target_freq="D")

    def test_deterministic_output(self, daily_series):
        """Test that conversion is deterministic."""
        from features.transforms.frequency import FrequencyConverter

        converter = FrequencyConverter(source_freq="D", target_freq="W")

        result1 = converter.convert(daily_series)
        result2 = converter.convert(daily_series)

        pd.testing.assert_series_equal(result1, result2)

    def test_business_day_aware_conversion(self):
        """Test conversion respecting business days only."""
        from features.transforms.frequency import FrequencyConverter

        # Create series with business days only
        dates = pd.bdate_range("2024-01-01", periods=60)
        values = np.arange(60, dtype=float)
        series = pd.Series(values, index=dates)

        converter = FrequencyConverter(
            source_freq="B",  # Business days
            target_freq="M",
            agg_method="mean",
        )
        result = converter.convert(series)

        assert len(result) > 0


class TestCalendarAdjustment:
    """Test calendar-aware adjustments."""

    def test_pay_period_identifier_initialization(self):
        """Test PayPeriodIdentifier initialization."""
        from features.transforms.calendar import PayPeriodIdentifier

        identifier = PayPeriodIdentifier()
        assert identifier is not None

    def test_identify_pay_period_type(self):
        """Test identification of bi-weekly vs semi-monthly patterns."""
        from features.transforms.calendar import PayPeriodIdentifier

        identifier = PayPeriodIdentifier()

        # Create dates for bi-weekly pattern (every 14 days)
        biweekly_dates = pd.date_range("2024-01-05", periods=26, freq="14D")

        period_type = identifier.identify_period_type(biweekly_dates)
        assert period_type == "bi-weekly"

    def test_five_friday_month_detection(self):
        """Test detection of months with 5 Fridays."""
        from features.transforms.calendar import identify_five_friday_months

        # March 2024 has 5 Fridays
        result = identify_five_friday_months(year=2024, month=3)
        assert result is True

        # Check for a year
        five_friday_months = identify_five_friday_months(year=2024)
        assert isinstance(five_friday_months, list)
        assert 3 in five_friday_months  # March 2024

    def test_business_day_count_per_month(self):
        """Test counting business days per month."""
        from features.transforms.calendar import count_business_days

        # January 2024
        bday_count = count_business_days(year=2024, month=1)
        assert 20 <= bday_count <= 23  # Typical range

    def test_calendar_adjustment_factor(self):
        """Test calendar adjustment factors (normalize for month length)."""
        from features.transforms.calendar import compute_calendar_adjustment

        # February (shorter) should have adjustment factor > 1
        # (to normalize to standard month)
        feb_adjustment = compute_calendar_adjustment(year=2024, month=2)
        assert feb_adjustment > 1.0

        # January (31 days) should have adjustment factor < 1
        jan_adjustment = compute_calendar_adjustment(year=2024, month=1)
        assert jan_adjustment < 1.05

    def test_holiday_calendar_creation(self):
        """Test creation of holiday calendar."""
        from features.transforms.calendar import get_holiday_calendar

        holidays = get_holiday_calendar(year=2024)
        assert isinstance(holidays, list)
        assert len(holidays) > 0
        # Check for major holidays
        holiday_dates = pd.DatetimeIndex(holidays)
        # Christmas should be there
        assert any(h.month == 12 and h.day == 25 for h in holiday_dates)


class TestScaling:
    """Test scaling and normalization transformations."""

    @pytest.fixture
    def sample_series(self) -> pd.Series:
        """Create sample series for scaling tests."""
        np.random.seed(42)
        values = np.random.randn(100) * 10 + 50
        dates = pd.date_range("2024-01-01", periods=100, freq="D")
        return pd.Series(values, index=dates, name="test_data")

    def test_standardizer_initialization(self):
        """Test StandardScaler initialization."""
        from features.transforms.scaling import StandardScaler

        scaler = StandardScaler()
        assert scaler is not None

    def test_standardization(self, sample_series):
        """Test z-score standardization."""
        from features.transforms.scaling import StandardScaler

        scaler = StandardScaler()
        scaled = scaler.fit_transform(sample_series)

        # Mean should be ~0, std should be ~1
        assert np.abs(scaled.mean()) < 0.1
        assert np.abs(scaled.std() - 1.0) < 0.1

    def test_min_max_scaling(self, sample_series):
        """Test min-max scaling to [0, 1]."""
        from features.transforms.scaling import MinMaxScaler

        scaler = MinMaxScaler()
        scaled = scaler.fit_transform(sample_series)

        # Should be in [0, 1]
        assert scaled.min() >= 0.0
        assert scaled.max() <= 1.0
        assert np.abs(scaled.min() - 0.0) < 0.01
        assert np.abs(scaled.max() - 1.0) < 0.01

    def test_robust_scaling(self, sample_series):
        """Test robust scaling (median/IQR)."""
        from features.transforms.scaling import RobustScaler

        scaler = RobustScaler()
        scaled = scaler.fit_transform(sample_series)

        # Median should be ~0
        assert np.abs(scaled.median()) < 0.1

    def test_scaler_inverse_transform(self, sample_series):
        """Test inverse transformation recovers original data."""
        from features.transforms.scaling import StandardScaler

        scaler = StandardScaler()
        scaled = scaler.fit_transform(sample_series)
        recovered = scaler.inverse_transform(scaled)

        # Should recover original (within numerical precision)
        np.testing.assert_allclose(recovered.values, sample_series.values, rtol=1e-10)


class TestWinsorization:
    """Test winsorization (outlier capping)."""

    @pytest.fixture
    def series_with_outliers(self) -> pd.Series:
        """Create series with outliers."""
        np.random.seed(42)
        values = np.random.randn(100)
        # Add outliers
        values[0] = 100
        values[1] = -100
        dates = pd.date_range("2024-01-01", periods=100, freq="D")
        return pd.Series(values, index=dates, name="data_with_outliers")

    def test_winsorizer_initialization(self):
        """Test Winsorizer initialization."""
        from features.transforms.scaling import Winsorizer

        winsorizer = Winsorizer(lower=0.05, upper=0.95)
        assert winsorizer.lower == 0.05
        assert winsorizer.upper == 0.95

    def test_winsorization_caps_outliers(self, series_with_outliers):
        """Test that winsorization caps extreme values."""
        from features.transforms.scaling import Winsorizer

        winsorizer = Winsorizer(lower=0.01, upper=0.99)
        winsorized = winsorizer.fit_transform(series_with_outliers)

        # Extreme values should be capped
        assert winsorized.max() < series_with_outliers.max()
        assert winsorized.min() > series_with_outliers.min()

        # Length preserved
        assert len(winsorized) == len(series_with_outliers)

    def test_symmetric_winsorization(self, series_with_outliers):
        """Test symmetric winsorization."""
        from features.transforms.scaling import Winsorizer

        winsorizer = Winsorizer(lower=0.05, upper=0.95)
        winsorized = winsorizer.fit_transform(series_with_outliers)

        # Check that extreme values are clipped
        p05 = series_with_outliers.quantile(0.05)
        p95 = series_with_outliers.quantile(0.95)

        assert winsorized.min() >= p05
        assert winsorized.max() <= p95

    def test_deterministic_winsorization(self, series_with_outliers):
        """Test that winsorization is deterministic."""
        from features.transforms.scaling import Winsorizer

        winsorizer = Winsorizer(lower=0.05, upper=0.95)

        result1 = winsorizer.fit_transform(series_with_outliers)
        result2 = winsorizer.fit_transform(series_with_outliers)

        pd.testing.assert_series_equal(result1, result2)


class TestTransformPipeline:
    """Test chaining multiple transformations."""

    def test_pipeline_creation(self):
        """Test creating transformation pipeline."""
        from features.transforms.pipeline import TransformPipeline
        from features.transforms.scaling import StandardScaler, Winsorizer

        pipeline = TransformPipeline(
            steps=[
                ("winsorize", Winsorizer(lower=0.05, upper=0.95)),
                ("standardize", StandardScaler()),
            ]
        )

        assert len(pipeline.steps) == 2

    def test_pipeline_fit_transform(self):
        """Test pipeline fit and transform."""
        from features.transforms.pipeline import TransformPipeline
        from features.transforms.scaling import StandardScaler, Winsorizer

        np.random.seed(42)
        values = np.random.randn(100) * 10 + 50
        values[0] = 1000  # Outlier
        dates = pd.date_range("2024-01-01", periods=100, freq="D")
        series = pd.Series(values, index=dates)

        pipeline = TransformPipeline(
            steps=[
                ("winsorize", Winsorizer(lower=0.01, upper=0.99)),
                ("standardize", StandardScaler()),
            ]
        )

        result = pipeline.fit_transform(series)

        # Should be standardized (mean ~0, std ~1)
        assert np.abs(result.mean()) < 0.2
        assert np.abs(result.std() - 1.0) < 0.2

    def test_pipeline_deterministic(self):
        """Test that pipeline is deterministic."""
        from features.transforms.pipeline import TransformPipeline
        from features.transforms.scaling import StandardScaler

        np.random.seed(42)
        values = np.random.randn(50)
        dates = pd.date_range("2024-01-01", periods=50, freq="D")
        series = pd.Series(values, index=dates)

        pipeline = TransformPipeline(steps=[("standardize", StandardScaler())])

        result1 = pipeline.fit_transform(series)
        result2 = pipeline.fit_transform(series)

        pd.testing.assert_series_equal(result1, result2)

