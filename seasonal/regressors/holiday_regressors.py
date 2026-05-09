"""
Holiday Regressors
Builds regressors for holiday timing effects on employment data
"""

from datetime import date, timedelta

import pandas as pd
from loguru import logger

try:
    import holidays
except ImportError:
    holidays = None
    logger.warning("holidays package not installed - some features limited")

from .regressor_builder import RegressorBuilder, create_date_range


class HolidayRegressors(RegressorBuilder):
    """
    Builder for holiday timing regressors

    Key holidays affecting employment data:
    - Easter (shifts between months)
    - Thanksgiving (shifts between months)
    - Labor Day (timing)
    - Memorial Day (timing)
    """

    def __init__(self):
        """Initialize holiday regressors builder"""
        super().__init__("holidays")

    def build(self, start_date: date, end_date: date, frequency: str = "monthly") -> pd.DataFrame:
        """
        Build holiday regressors

        Args:
            start_date: Start date
            end_date: End date
            frequency: Time frequency

        Returns:
            DataFrame with holiday regressors
        """
        logger.info(f"Building holiday regressors from {start_date} to {end_date}")

        dates = create_date_range(start_date, end_date, frequency)

        regressors = pd.DataFrame(index=dates)

        # Build individual holiday regressors
        regressors["easter_timing"] = self.build_easter_regressor(start_date, end_date)
        regressors["thanksgiving_timing"] = self.build_thanksgiving_regressor(start_date, end_date)
        regressors["labor_day_timing"] = self.build_labor_day_regressor(start_date, end_date)

        logger.info(f"Created {len(regressors.columns)} holiday regressors")

        return regressors

    def build_easter_regressor(self, start_date: date, end_date: date) -> pd.Series:
        """
        Build Easter timing regressor

        Easter moves between late March and late April,
        affecting seasonal patterns in retail and other sectors
        """
        dates = create_date_range(start_date, end_date, "monthly")
        regressor = pd.Series(0, index=dates)

        # Get Easter dates for each year
        for year in range(start_date.year, end_date.year + 1):
            easter_date = self._calculate_easter(year)

            # Mark the month containing Easter
            easter_period = pd.Period(easter_date, freq="M")
            mask = dates.to_period("M") == easter_period

            # Value based on position in month (early/mid/late)
            day_of_month = easter_date.day
            if day_of_month <= 10:
                regressor[mask] = -1  # Early Easter
            elif day_of_month >= 20:
                regressor[mask] = 1  # Late Easter
            else:
                regressor[mask] = 0  # Mid Easter (neutral)

        return regressor

    def build_thanksgiving_regressor(self, start_date: date, end_date: date) -> pd.Series:
        """
        Build Thanksgiving timing regressor

        Thanksgiving is 4th Thursday of November,
        but the exact week affects retail hiring patterns
        """
        dates = create_date_range(start_date, end_date, "monthly")
        regressor = pd.Series(0, index=dates)

        for year in range(start_date.year, end_date.year + 1):
            # Thanksgiving is 4th Thursday of November
            thanksgiving = self._calculate_thanksgiving(year)

            # Mark November
            nov_period = pd.Period(f"{year}-11", freq="M")
            mask = dates.to_period("M") == nov_period

            # Value based on whether it's early or late November
            if thanksgiving.day <= 24:
                regressor[mask] = -1  # Early Thanksgiving
            else:
                regressor[mask] = 1  # Late Thanksgiving

        return regressor

    def build_labor_day_regressor(self, start_date: date, end_date: date) -> pd.Series:
        """
        Build Labor Day timing regressor

        Labor Day is first Monday of September,
        affects timing of back-to-school and seasonal transitions
        """
        dates = create_date_range(start_date, end_date, "monthly")
        regressor = pd.Series(0, index=dates)

        for year in range(start_date.year, end_date.year + 1):
            # Labor Day is first Monday of September
            labor_day = self._calculate_labor_day(year)

            # Mark September
            sep_period = pd.Period(f"{year}-09", freq="M")
            mask = dates.to_period("M") == sep_period

            # Value based on position in month
            if labor_day.day <= 3:
                regressor[mask] = -1  # Very early Labor Day
            elif labor_day.day >= 6:
                regressor[mask] = 1  # Late Labor Day

        return regressor

    def _calculate_easter(self, year: int) -> date:
        """
        Calculate Easter date for a given year
        Using Meeus/Jones/Butcher algorithm
        """
        a = year % 19
        b = year // 100
        c = year % 100
        d = b // 4
        e = b % 4
        f = (b + 8) // 25
        g = (b - f + 1) // 3
        h = (19 * a + b - d - g + 15) % 30
        i = c // 4
        k = c % 4
        offset = (32 + 2 * e + 2 * i - h - k) % 7
        m = (a + 11 * h + 22 * offset) // 451
        month = (h + offset - 7 * m + 114) // 31
        day = ((h + offset - 7 * m + 114) % 31) + 1

        return date(year, month, day)

    def _calculate_thanksgiving(self, year: int) -> date:
        """Calculate Thanksgiving date (4th Thursday of November)"""
        # Find first day of November
        nov_1 = date(year, 11, 1)

        # Find first Thursday
        days_until_thursday = (3 - nov_1.weekday()) % 7
        first_thursday = nov_1 + timedelta(days=days_until_thursday)

        # Fourth Thursday
        thanksgiving = first_thursday + timedelta(weeks=3)

        return thanksgiving

    def _calculate_labor_day(self, year: int) -> date:
        """Calculate Labor Day (first Monday of September)"""
        # Find first day of September
        sep_1 = date(year, 9, 1)

        # Find first Monday
        days_until_monday = (7 - sep_1.weekday()) % 7
        labor_day = sep_1 + timedelta(days=days_until_monday)

        return labor_day


# Example usage
if __name__ == "__main__":
    builder = HolidayRegressors()

    regressors = builder.build(start_date=date(2020, 1, 1), end_date=date(2023, 12, 31))

    print(regressors.head(20))
