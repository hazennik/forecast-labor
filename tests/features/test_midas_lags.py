"""
Tests for MIDAS lag constructor.

MIDAS (Mixed Data Sampling) is a regression approach for mixing frequencies.
Key features to test:
- Frequency alignment (daily → weekly, daily → monthly, weekly → monthly)
- Exponential Almon lag polynomial weighting
- Ragged-edge handling (missing recent high-freq data)
- Deterministic output (same input → same output)
"""

import numpy as np
import pandas as pd
import pytest


class TestMIDASLagConstructor:
    """Test MIDAS lag constructor functionality."""

    @pytest.fixture
    def daily_series(self) -> pd.Series:
        """Create a daily time series for testing."""
        dates = pd.date_range("2024-01-01", periods=90, freq="D")
        values = np.arange(90) + np.random.RandomState(42).randn(90) * 0.1
        return pd.Series(values, index=dates, name="daily_data")

    @pytest.fixture
    def weekly_series(self) -> pd.Series:
        """Create a weekly time series for testing."""
        dates = pd.date_range("2024-01-01", periods=12, freq="W")
        values = np.arange(12) + np.random.RandomState(42).randn(12) * 0.1
        return pd.Series(values, index=dates, name="weekly_data")

    @pytest.fixture
    def monthly_dates(self) -> pd.DatetimeIndex:
        """Create monthly target dates."""
        return pd.date_range("2024-01-01", periods=3, freq="MS")

    def test_constructor_initialization(self):
        """Test MIDASLagConstructor can be initialized with valid parameters."""
        from features.midas.lag_constructor import MIDASLagConstructor

        constructor = MIDASLagConstructor(
            source_freq="D",
            target_freq="M",
            n_lags=20,
            almon_poly_degree=2,
        )
        assert constructor.source_freq == "D"
        assert constructor.target_freq == "M"
        assert constructor.n_lags == 20
        assert constructor.almon_poly_degree == 2

    def test_invalid_frequency_raises_error(self):
        """Test that invalid frequency combinations raise errors."""
        from features.midas.lag_constructor import MIDASLagConstructor

        # Invalid source frequency
        with pytest.raises(ValueError, match="source_freq must be"):
            MIDASLagConstructor(source_freq="M", target_freq="D", n_lags=10)

        # Invalid target frequency
        with pytest.raises(ValueError, match="target_freq must be"):
            MIDASLagConstructor(source_freq="D", target_freq="Q", n_lags=10)

    def test_daily_to_monthly_alignment(self, daily_series, monthly_dates):
        """Test alignment of daily data to monthly frequency."""
        from features.midas.lag_constructor import MIDASLagConstructor

        constructor = MIDASLagConstructor(source_freq="D", target_freq="M", n_lags=20)
        result = constructor.construct_lags(daily_series, monthly_dates)

        # Check output shape: (n_months, n_lags)
        assert result.shape == (len(monthly_dates), 20)
        # Check no NaN values (except for edge cases)
        assert not result.isna().all().any()
        # Check output is DataFrame
        assert isinstance(result, pd.DataFrame)

    def test_weekly_to_monthly_alignment(self, weekly_series, monthly_dates):
        """Test alignment of weekly data to monthly frequency."""
        from features.midas.lag_constructor import MIDASLagConstructor

        constructor = MIDASLagConstructor(source_freq="W", target_freq="M", n_lags=4)
        result = constructor.construct_lags(weekly_series, monthly_dates)

        # Check output shape: (n_months, n_lags)
        assert result.shape == (len(monthly_dates), 4)
        assert isinstance(result, pd.DataFrame)

    def test_almon_polynomial_weights(self):
        """Test that Almon polynomial weights are computed correctly."""
        from features.midas.lag_constructor import MIDASLagConstructor

        constructor = MIDASLagConstructor(
            source_freq="D",
            target_freq="M",
            n_lags=10,
            almon_poly_degree=2,
        )
        weights = constructor._compute_almon_weights(n_lags=10, degree=2)

        # Weights should sum to 1 (normalized)
        assert np.isclose(weights.sum(), 1.0, atol=1e-6)
        # Weights should be positive
        assert (weights >= 0).all()
        # Weights should decay (exponential Almon)
        assert weights[0] > weights[-1]  # Recent more important

    def test_equal_weights_when_almon_disabled(self):
        """Test equal weighting when Almon polynomial is disabled (degree=0)."""
        from features.midas.lag_constructor import MIDASLagConstructor

        constructor = MIDASLagConstructor(
            source_freq="D",
            target_freq="M",
            n_lags=10,
            almon_poly_degree=0,  # Disable Almon, use equal weights
        )
        weights = constructor._compute_almon_weights(n_lags=10, degree=0)

        # All weights should be equal
        assert np.allclose(weights, 1.0 / 10)

    def test_deterministic_output(self, daily_series, monthly_dates):
        """Test that same input produces identical output (determinism)."""
        from features.midas.lag_constructor import MIDASLagConstructor

        constructor = MIDASLagConstructor(
            source_freq="D", target_freq="M", n_lags=20, almon_poly_degree=2
        )

        # Run twice with same input
        result1 = constructor.construct_lags(daily_series, monthly_dates)
        result2 = constructor.construct_lags(daily_series, monthly_dates)

        # Results must be identical
        pd.testing.assert_frame_equal(result1, result2)

    def test_ragged_edge_handling(self):
        """Test handling of ragged edges (missing recent high-frequency data)."""
        from features.midas.lag_constructor import MIDASLagConstructor

        # Create series with missing recent data
        dates = pd.date_range("2024-01-01", periods=85, freq="D")  # 5 days short
        values = np.arange(85)
        series = pd.Series(values, index=dates)

        monthly_dates = pd.date_range("2024-01-01", periods=3, freq="MS")

        constructor = MIDASLagConstructor(source_freq="D", target_freq="M", n_lags=20)
        result = constructor.construct_lags(series, monthly_dates)

        # Should handle gracefully (fill with last available value or NaN)
        assert result.shape == (3, 20)
        # First row will have NaN for lags that go beyond data start
        # Second month should have complete data
        assert not result.iloc[1].isna().any()
        # Function should complete without errors even with ragged edges
        assert result is not None

    def test_weighted_lags_with_almon(self, daily_series, monthly_dates):
        """Test that weighted lags are computed correctly with Almon polynomial."""
        from features.midas.lag_constructor import MIDASLagConstructor

        constructor = MIDASLagConstructor(
            source_freq="D",
            target_freq="M",
            n_lags=10,
            almon_poly_degree=2,
            apply_weights=True,
        )
        result = constructor.construct_lags(daily_series, monthly_dates)

        # With weights applied, recent lags should have higher values
        # (if original series is increasing)
        assert result.shape == (len(monthly_dates), 10)

    def test_unweighted_lags(self, daily_series, monthly_dates):
        """Test unweighted lags (just raw lag values)."""
        from features.midas.lag_constructor import MIDASLagConstructor

        constructor = MIDASLagConstructor(
            source_freq="D",
            target_freq="M",
            n_lags=10,
            apply_weights=False,  # No weights, just raw lags
        )
        result = constructor.construct_lags(daily_series, monthly_dates)

        # Should return raw lag values
        assert result.shape == (len(monthly_dates), 10)

    def test_column_naming(self, daily_series, monthly_dates):
        """Test that lag columns are named appropriately."""
        from features.midas.lag_constructor import MIDASLagConstructor

        constructor = MIDASLagConstructor(source_freq="D", target_freq="M", n_lags=5)
        result = constructor.construct_lags(daily_series, monthly_dates)

        # Columns are named with default prefix "lag" + "_lag_0", etc.
        expected_cols = [f"lag_lag_{i}" for i in range(5)]
        assert list(result.columns) == expected_cols

    def test_custom_column_prefix(self, daily_series, monthly_dates):
        """Test custom column prefix for lag names."""
        from features.midas.lag_constructor import MIDASLagConstructor

        constructor = MIDASLagConstructor(
            source_freq="D",
            target_freq="M",
            n_lags=5,
            column_prefix="daily_data",
        )
        result = constructor.construct_lags(daily_series, monthly_dates)

        # Columns should use custom prefix
        expected_cols = [f"daily_data_lag_{i}" for i in range(5)]
        assert list(result.columns) == expected_cols

    def test_empty_series_raises_error(self, monthly_dates):
        """Test that empty series raises appropriate error."""
        from features.midas.lag_constructor import MIDASLagConstructor

        empty_series = pd.Series([], dtype=float)
        constructor = MIDASLagConstructor(source_freq="D", target_freq="M", n_lags=10)

        with pytest.raises(ValueError, match="Series cannot be empty"):
            constructor.construct_lags(empty_series, monthly_dates)

    def test_mismatched_frequency_raises_error(self, daily_series, monthly_dates):
        """Test that mismatched series frequency raises error."""
        from features.midas.lag_constructor import MIDASLagConstructor

        # Constructor expects weekly, but series is daily
        constructor = MIDASLagConstructor(source_freq="W", target_freq="M", n_lags=4)

        with pytest.raises(ValueError, match="Series frequency does not match"):
            constructor.construct_lags(daily_series, monthly_dates)

    def test_insufficient_lags_warning(self, monthly_dates):
        """Test warning when insufficient data for requested lags."""
        from features.midas.lag_constructor import MIDASLagConstructor

        # Very short series
        short_series = pd.Series([1, 2, 3], index=pd.date_range("2024-01-01", periods=3, freq="D"))
        constructor = MIDASLagConstructor(source_freq="D", target_freq="M", n_lags=20)

        # Should handle gracefully (fill with NaN or raise warning)
        result = constructor.construct_lags(short_series, monthly_dates)
        assert result.shape == (len(monthly_dates), 20)
        # Some lags will be NaN
        assert result.isna().any().any()


class TestMIDASUtilities:
    """Test MIDAS utility functions."""

    def test_frequency_ratio_calculation(self):
        """Test calculation of frequency ratios."""
        from features.midas.lag_constructor import get_frequency_ratio

        # Daily to monthly: ~30
        ratio_dm = get_frequency_ratio("D", "M")
        assert 28 <= ratio_dm <= 31

        # Weekly to monthly: ~4
        ratio_wm = get_frequency_ratio("W", "M")
        assert 4 <= ratio_wm <= 5

        # Daily to weekly: ~7
        ratio_dw = get_frequency_ratio("D", "W")
        assert 7 == ratio_dw

    def test_infer_series_frequency(self):
        """Test automatic frequency inference from series."""
        from features.midas.lag_constructor import infer_series_frequency

        # Daily series
        daily = pd.Series(range(30), index=pd.date_range("2024-01-01", periods=30, freq="D"))
        assert infer_series_frequency(daily) == "D"

        # Weekly series
        weekly = pd.Series(range(4), index=pd.date_range("2024-01-01", periods=4, freq="W"))
        assert infer_series_frequency(weekly) == "W"

        # Monthly series
        monthly = pd.Series(range(12), index=pd.date_range("2024-01-01", periods=12, freq="MS"))
        assert infer_series_frequency(monthly) in ["M", "MS"]

    def test_align_to_target_dates(self):
        """Test alignment of high-freq series to target dates."""
        from features.midas.lag_constructor import align_series_to_dates

        # Daily series
        daily = pd.Series(range(90), index=pd.date_range("2024-01-01", periods=90, freq="D"))
        target_dates = pd.date_range("2024-01-01", periods=3, freq="MS")

        aligned = align_series_to_dates(daily, target_dates, method="last")

        # Should return last value before or on each target date
        assert len(aligned) == len(target_dates)
        assert isinstance(aligned, pd.Series)


class TestMIDASIntegration:
    """Integration tests for MIDAS lag construction with real-world scenarios."""

    def test_treasury_withholdings_to_monthly_nfp(self):
        """Test constructing MIDAS lags from daily Treasury to monthly NFP."""
        from features.midas.lag_constructor import MIDASLagConstructor

        # Simulate daily Treasury withholdings (60 days)
        dates = pd.date_range("2024-01-01", periods=60, freq="D")
        treasury_data = pd.Series(
            100 + np.random.RandomState(42).randn(60) * 5,
            index=dates,
            name="treasury_withholdings",
        )

        # Target: monthly NFP release dates (first Friday of month)
        nfp_dates = pd.DatetimeIndex(["2024-02-02", "2024-03-01"])

        constructor = MIDASLagConstructor(
            source_freq="D",
            target_freq="M",
            n_lags=20,
            almon_poly_degree=2,
            column_prefix="treasury",
        )

        result = constructor.construct_lags(treasury_data, nfp_dates)

        # Check shape
        assert result.shape == (2, 20)
        # Check column names
        assert result.columns[0] == "treasury_lag_0"
        # Check no missing values
        assert not result.isna().any().any()

    def test_ui_claims_to_monthly_nfp(self):
        """Test constructing MIDAS lags from weekly UI claims to monthly NFP."""
        from features.midas.lag_constructor import MIDASLagConstructor

        # Simulate weekly UI claims (12 weeks)
        dates = pd.date_range("2024-01-01", periods=12, freq="W")
        claims_data = pd.Series(
            200 + np.random.RandomState(42).randn(12) * 10,
            index=dates,
            name="ui_claims",
        )

        # Target: monthly NFP release dates
        nfp_dates = pd.DatetimeIndex(["2024-02-02", "2024-03-01"])

        constructor = MIDASLagConstructor(
            source_freq="W",
            target_freq="M",
            n_lags=8,
            almon_poly_degree=2,
            column_prefix="claims",
        )

        result = constructor.construct_lags(claims_data, nfp_dates)

        # Check shape
        assert result.shape == (2, 8)
        # Check column names
        assert result.columns[0] == "claims_lag_0"
