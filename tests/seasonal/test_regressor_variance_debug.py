"""
Test Regressor Variance and Pipeline Flow
Phase 6.2.0: Debug user regressor pipeline to verify regressors are non-zero and applied correctly

TDD Approach:
1. Write tests to verify regressor variance properties
2. Run tests to document current state
3. Debug issues if tests fail
4. Verify fixes with tests
"""

from datetime import date

import pytest
import pandas as pd
import numpy as np

from seasonal.regressors.holiday_regressors import HolidayRegressors
from seasonal.regressors.strike_regressors import StrikeRegressors
from seasonal.regressors.weather_regressors import WeatherRegressors
from seasonal.pipeline import SeasonalAdjustmentPipeline
from seasonal.spec_builder import SpecBuilder, X13Spec
from etl.common.storage import StorageClient


class TestHolidayRegressorVariance:
    """
    Test that HolidayRegressors.build() returns non-zero variance data

    Critical property: Holiday timing varies year-to-year, so regressors must have variance
    """

    def test_holiday_regressors_returns_non_zero_variance(self):
        """
        Test: HolidayRegressors.build() must return non-zero variance for all regressors

        Rationale: Easter timing varies (March vs April), Thanksgiving varies (early vs late Nov),
        Labor Day varies (Sept 1-7). This variance is ESSENTIAL for X-13 regression.
        """
        # Arrange: Build regressors over 10 years (sufficient for variance)
        builder = HolidayRegressors()
        start_date = date(2014, 1, 1)
        end_date = date(2023, 12, 31)

        # Act: Build regressors
        regressors = builder.build(start_date, end_date)

        # Assert: All regressors must have non-zero variance
        for col in regressors.columns:
            variance = regressors[col].var()
            assert variance > 0, (
                f"Regressor '{col}' has zero variance! "
                f"Holiday timing should vary year-to-year. "
                f"Actual variance: {variance}"
            )

    def test_easter_regressor_has_expected_variance_pattern(self):
        """
        Test: Easter regressor must have variance because Easter shifts between March/April

        Easter algorithm (Meeus/Jones/Butcher) produces dates ranging from ~March 22 to ~April 25.
        This creates -1 (early), 0 (mid), 1 (late) patterns that must vary.
        """
        builder = HolidayRegressors()
        start_date = date(2014, 1, 1)
        end_date = date(2023, 12, 31)

        regressors = builder.build(start_date, end_date)
        easter = regressors["easter_timing"]

        # Verify variance
        assert easter.var() > 0, "Easter timing must have variance"

        # Verify range of values (should see -1, 0, 1)
        unique_values = set(easter.unique())
        assert len(unique_values) > 1, (
            f"Easter timing should have multiple values (-1, 0, 1). " f"Found only: {unique_values}"
        )

        # Easter should vary between -1 (early), 0 (mid), 1 (late)
        assert all(
            val in [-1, 0, 1] for val in unique_values
        ), f"Easter timing should be -1, 0, or 1. Found: {unique_values}"

    def test_thanksgiving_regressor_has_expected_variance_pattern(self):
        """
        Test: Thanksgiving regressor must vary because 4th Thursday shifts

        4th Thursday of November ranges from Nov 22-28, creating early/late pattern.
        """
        builder = HolidayRegressors()
        start_date = date(2014, 1, 1)
        end_date = date(2023, 12, 31)

        regressors = builder.build(start_date, end_date)
        thanksgiving = regressors["thanksgiving_timing"]

        # Verify variance
        assert thanksgiving.var() > 0, "Thanksgiving timing must have variance"

        # Verify range of values
        unique_values = set(thanksgiving.unique())
        assert (
            len(unique_values) > 1
        ), f"Thanksgiving timing should vary. Found only: {unique_values}"

    def test_labor_day_regressor_has_expected_variance_pattern(self):
        """
        Test: Labor Day regressor must vary because 1st Monday shifts

        1st Monday of September ranges from Sept 1-7, creating timing variation.
        """
        builder = HolidayRegressors()
        start_date = date(2014, 1, 1)
        end_date = date(2023, 12, 31)

        regressors = builder.build(start_date, end_date)
        labor_day = regressors["labor_day_timing"]

        # Verify variance
        assert labor_day.var() > 0, "Labor Day timing must have variance"

        # Verify range of values
        unique_values = set(labor_day.unique())
        assert len(unique_values) > 1, f"Labor Day timing should vary. Found only: {unique_values}"

    def test_regressors_not_all_zeros(self):
        """
        Test: Regressors must not be all zeros

        This is the critical check - if regressors are all zeros, X-13 has nothing to regress.
        """
        builder = HolidayRegressors()
        start_date = date(2014, 1, 1)
        end_date = date(2023, 12, 31)

        regressors = builder.build(start_date, end_date)

        for col in regressors.columns:
            non_zero_count = (regressors[col] != 0).sum()
            assert non_zero_count > 0, (
                f"Regressor '{col}' is all zeros! "
                f"This indicates holiday timing is not being detected. "
                f"Total observations: {len(regressors)}, Non-zero: {non_zero_count}"
            )

    def test_regressors_have_reasonable_distribution(self):
        """
        Test: Regressors should have reasonable distribution (not mostly zeros)

        For monthly data over 10 years (120 months), Easter/Thanksgiving/Labor Day
        only affect specific months (12 months per year), so ~12 non-zero values expected.
        """
        builder = HolidayRegressors()
        start_date = date(2014, 1, 1)
        end_date = date(2023, 12, 31)

        regressors = builder.build(start_date, end_date)

        for col in regressors.columns:
            non_zero_count = (regressors[col] != 0).sum()
            total_count = len(regressors)
            non_zero_pct = (non_zero_count / total_count) * 100

            # Expect at least 5% non-zero (6/120 = 5%)
            assert non_zero_pct >= 5, (
                f"Regressor '{col}' has too many zeros ({non_zero_pct:.1f}% non-zero). "
                f"Expected at least 5% non-zero for holiday timing regressors."
            )


class TestRegressorPipelineFlow:
    """
    Test that regressors flow correctly through: builder → pipeline → spec → X-13

    This verifies the full integration, not just unit-level regressor construction.
    """

    def test_pipeline_preserves_regressor_variance(self):
        """
        Test: Regressor variance must be preserved through pipeline flow

        Failure modes:
        - Regressors accidentally zeroed during transformation
        - Regressors filtered out before reaching X-13
        - DataFrame operations causing data loss
        """
        # Arrange: Create sample series
        dates = pd.date_range("2014-01-01", "2023-12-31", freq="MS")
        pd.Series(
            140000
            + 2000 * np.sin(2 * np.pi * np.arange(len(dates)) / 12)
            + np.random.normal(0, 500, len(dates)),
            index=dates,
            name="test_series",
        )

        # Act: Build regressors through pipeline
        pipeline = SeasonalAdjustmentPipeline()
        regressors = pipeline._build_regressors(
            start_date=dates[0].date(),
            end_date=dates[-1].date() + pd.DateOffset(months=24),  # Extended for X-13 forecast
            config={
                "use_holiday_regressors": True,
                "use_strike_regressors": False,
                "use_weather_regressors": False,
            },
        )

        # Assert: Regressors must have non-zero variance after pipeline processing
        assert len(regressors.columns) > 0, "Pipeline returned no regressors!"

        for col in regressors.columns:
            variance = regressors[col].var()
            assert variance > 0, (
                f"Regressor '{col}' has zero variance after pipeline processing! "
                f"This suggests data was lost or zeroed during transformation."
            )

    def test_spec_builder_includes_user_regressors(self):
        """
        Test: SpecBuilder must include user regressors in generated spec

        Critical check: Spec must contain 'user = (easter_timing thanksgiving_timing labor_day_timing)'
        """
        # Arrange: Build regressors
        builder = HolidayRegressors()
        regressors = builder.build(date(2014, 1, 1), date(2023, 12, 31))

        # Act: Generate spec
        spec_builder = SpecBuilder()
        config = X13Spec(
            series_name="test_series",
            title="Test Series",
            start_year=2014,
            start_month=1,
            mode="mult",
            user_regressors=list(regressors.columns),
            regressor_data=regressors,
        )
        spec_content = spec_builder.build_spec(config)

        # Assert: Spec must contain user regressor declaration
        assert "user =" in spec_content, (
            "Spec does not contain 'user =' declaration! "
            "User regressors will not be used by X-13."
        )

        # Verify each regressor name is in spec
        for regressor_name in regressors.columns:
            assert regressor_name in spec_content, (
                f"Regressor '{regressor_name}' not found in spec! "
                f"X-13 will not use this regressor."
            )

    def test_spec_has_file_directive_for_regressors(self):
        """
        Test: Spec must include 'file =' directive for external regressor file

        X-13 expects regressor data in external .dat file, referenced via file directive.
        """
        # Arrange: Build regressors
        builder = HolidayRegressors()
        regressors = builder.build(date(2014, 1, 1), date(2023, 12, 31))

        # Act: Generate spec
        spec_builder = SpecBuilder()
        config = X13Spec(
            series_name="test_series",
            title="Test Series",
            start_year=2014,
            start_month=1,
            mode="mult",
            user_regressors=list(regressors.columns),
            regressor_data=regressors,
        )
        spec_content = spec_builder.build_spec(config)

        # Assert: Spec must contain file directive in regression block
        assert 'file = "test_series_regressors.dat"' in spec_content, (
            "Spec does not contain file directive for regressors! "
            "X-13 will not find regressor data."
        )

    def test_spec_does_not_duplicate_user_regressors_in_variables(self):
        """
        Test: User regressors must ONLY be in user=(), NOT in variables=()

        This was a bug fixed in Phase 6.1.2. Ensure it doesn't regress.
        """
        # Arrange: Build regressors
        builder = HolidayRegressors()
        regressors = builder.build(date(2014, 1, 1), date(2023, 12, 31))

        # Act: Generate spec
        spec_builder = SpecBuilder()
        config = X13Spec(
            series_name="test_series",
            title="Test Series",
            start_year=2014,
            start_month=1,
            mode="mult",
            easter=True,  # Built-in regressor
            trading_day=True,  # Built-in regressor
            user_regressors=list(regressors.columns),
            regressor_data=regressors,
        )
        spec_content = spec_builder.build_spec(config)

        # Extract variables line
        variables_line = None
        for line in spec_content.split("\n"):
            if "variables =" in line:
                variables_line = line
                break

        # Assert: User regressors should NOT be in variables=()
        if variables_line:
            for regressor_name in regressors.columns:
                assert regressor_name not in variables_line, (
                    f"User regressor '{regressor_name}' found in variables=() declaration! "
                    f"This causes duplicate declaration error in X-13. "
                    f"User regressors should ONLY be in user=(), not variables=()."
                )


class TestRegressorActualValues:
    """
    Test actual regressor values to ensure they match expected holiday timing

    This validates the MATHEMATICAL CORRECTNESS, not just variance properties.
    """

    def test_easter_2020_timing_is_correct(self):
        """
        Test: Easter 2020 was April 12 (mid-month) → regressor should be 0

        This verifies the Easter algorithm is working correctly.
        """
        builder = HolidayRegressors()
        regressors = builder.build(date(2020, 1, 1), date(2020, 12, 31))

        # April 2020 (Easter on April 12, mid-month)
        april_2020 = pd.Period("2020-04", freq="M")
        april_value = regressors.loc[
            regressors.index.to_period("M") == april_2020, "easter_timing"
        ].iloc[0]

        # Easter April 12 = mid-month → expect 0
        assert (
            april_value == 0
        ), f"Easter 2020 was April 12 (mid-month), expected regressor value 0. Got: {april_value}"

    def test_easter_2024_timing_is_correct(self):
        """
        Test: Easter 2024 was March 31 (late March) → regressor should be 1

        This verifies late Easter detection.
        """
        builder = HolidayRegressors()
        regressors = builder.build(date(2024, 1, 1), date(2024, 12, 31))

        # March 2024 (Easter on March 31, late in month)
        march_2024 = pd.Period("2024-03", freq="M")
        march_value = regressors.loc[
            regressors.index.to_period("M") == march_2024, "easter_timing"
        ].iloc[0]

        # Easter March 31 = late in month → expect 1
        assert (
            march_value == 1
        ), f"Easter 2024 was March 31 (late), expected regressor value 1. Got: {march_value}"

    def test_thanksgiving_2023_timing_is_correct(self):
        """
        Test: Thanksgiving 2023 was November 23 (early) → regressor should be -1

        Thanksgiving is 4th Thursday of November, ranging from Nov 22-28.
        """
        builder = HolidayRegressors()
        regressors = builder.build(date(2023, 1, 1), date(2023, 12, 31))

        # November 2023 (Thanksgiving Nov 23, early)
        nov_2023 = pd.Period("2023-11", freq="M")
        nov_value = regressors.loc[
            regressors.index.to_period("M") == nov_2023, "thanksgiving_timing"
        ].iloc[0]

        # Thanksgiving Nov 23 (≤ 24) = early → expect -1
        assert (
            nov_value == -1
        ), f"Thanksgiving 2023 was November 23 (early), expected regressor value -1. Got: {nov_value}"

    def test_labor_day_2023_timing_is_correct(self):
        """
        Test: Labor Day 2023 was September 4 (mid-range) → regressor should be 0

        Labor Day is 1st Monday of September, ranging from Sept 1-7.
        """
        builder = HolidayRegressors()
        regressors = builder.build(date(2023, 1, 1), date(2023, 12, 31))

        # September 2023 (Labor Day Sept 4, mid-range)
        sept_2023 = pd.Period("2023-09", freq="M")
        sept_value = regressors.loc[
            regressors.index.to_period("M") == sept_2023, "labor_day_timing"
        ].iloc[0]

        # Labor Day Sept 4 (4-5 range) = mid → expect 0
        assert (
            sept_value == 0
        ), f"Labor Day 2023 was September 4 (mid), expected regressor value 0. Got: {sept_value}"


class TestStrikeAndWeatherRegressors:
    """
    Test strike and weather regressors

    NOTE: These may return zero-variance if vintage data is not available.
    That's acceptable - the pipeline filters out zero-variance regressors.
    """

    def test_strike_regressors_handle_missing_data_gracefully(self):
        """
        Test: StrikeRegressors.build() should return empty or zero-filled regressors if no data

        This is acceptable behavior - pipeline filters out zero-variance regressors.
        """
        storage = StorageClient()
        builder = StrikeRegressors(storage)

        # Build regressors (may not have vintage data)
        regressors = builder.build(date(2023, 1, 1), date(2023, 12, 31))

        # Should return DataFrame (even if empty or zeros)
        assert isinstance(
            regressors, pd.DataFrame
        ), "StrikeRegressors.build() must return DataFrame (even if empty)"

    def test_weather_regressors_handle_missing_data_gracefully(self):
        """
        Test: WeatherRegressors.build() should return empty or zero-filled regressors if no data

        This is acceptable behavior - pipeline filters out zero-variance regressors.
        """
        storage = StorageClient()
        builder = WeatherRegressors(storage)

        # Build regressors (may not have vintage data)
        regressors = builder.build(date(2023, 1, 1), date(2023, 12, 31))

        # Should return DataFrame (even if empty or zeros)
        assert isinstance(
            regressors, pd.DataFrame
        ), "WeatherRegressors.build() must return DataFrame (even if empty)"

    def test_pipeline_filters_out_zero_variance_regressors(self):
        """
        Test: Pipeline must filter out zero-variance regressors

        Critical for X-13: Zero-variance regressors cause singular regression matrix.
        """
        # Arrange: Create sample series
        dates = pd.date_range("2014-01-01", "2023-12-31", freq="MS")
        pd.Series(
            140000
            + 2000 * np.sin(2 * np.pi * np.arange(len(dates)) / 12)
            + np.random.normal(0, 500, len(dates)),
            index=dates,
            name="test_series",
        )

        # Act: Build regressors (strike/weather may be zero-variance)
        pipeline = SeasonalAdjustmentPipeline()
        regressors = pipeline._build_regressors(
            start_date=dates[0].date(),
            end_date=dates[-1].date() + pd.DateOffset(months=24),
            config={
                "use_holiday_regressors": True,
                "use_strike_regressors": True,
                "use_weather_regressors": True,
            },
        )

        # Assert: All returned regressors must have non-zero variance
        for col in regressors.columns:
            variance = regressors[col].var()
            assert variance > 0, (
                f"Pipeline returned zero-variance regressor '{col}'! "
                f"Pipeline must filter out zero-variance regressors."
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
