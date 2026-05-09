"""
Calendar adjustments for labor market forecasting.

Features:
- Pay-period identification (bi-weekly vs semi-monthly)
- Five-Friday month detection
- Business day counting
- Calendar adjustment factors
- Holiday calendars
"""

from typing import List, Literal, Union, Optional
import pandas as pd
from datetime import datetime
import calendar
from loguru import logger


class PayPeriodIdentifier:
    """
    Identify pay-period patterns in time series data.

    Detects bi-weekly (every 14 days) vs semi-monthly (15th and end of month)
    payment patterns for Treasury withholding data alignment.
    """

    def __init__(self):
        """Initialize pay period identifier."""
        logger.info("pay_period_identifier_initialized")

    def identify_period_type(
        self, dates: pd.DatetimeIndex
    ) -> Literal["bi-weekly", "semi-monthly", "unknown"]:
        """
        Identify pay period type from date patterns.

        Args:
            dates: DatetimeIndex of payment dates

        Returns:
            Pay period type: 'bi-weekly', 'semi-monthly', or 'unknown'
        """
        if len(dates) < 4:
            logger.warning("insufficient_dates_for_identification", date_count=len(dates))
            return "unknown"

        # Calculate differences between consecutive dates
        diffs = dates.to_series().diff().dt.days.dropna()

        # Bi-weekly: ~14 days between payments
        biweekly_score = (diffs >= 12) & (diffs <= 16)

        # Semi-monthly: ~15 days between payments (but irregular)
        semimonthly_score = (diffs >= 13) & (diffs <= 18)

        if biweekly_score.sum() / len(diffs) > 0.7:
            return "bi-weekly"
        elif semimonthly_score.sum() / len(diffs) > 0.6:
            return "semi-monthly"
        else:
            return "unknown"


def identify_five_friday_months(
    year: Optional[int] = None, month: Optional[int] = None
) -> Union[bool, List[int]]:
    """
    Identify months with 5 Fridays (affects payroll calculations).

    Args:
        year: Year to check
        month: Specific month to check (1-12), or None for all months

    Returns:
        If month specified: bool (True if has 5 Fridays)
        If month None: List of months (1-12) with 5 Fridays

    Example:
        >>> identify_five_friday_months(year=2024, month=3)
        True
        >>> identify_five_friday_months(year=2024)
        [3, 5, 8, 11]
    """
    if year is None:
        year = datetime.now().year

    if month is not None:
        # Check specific month
        fridays = []
        for day in range(1, calendar.monthrange(year, month)[1] + 1):
            date = datetime(year, month, day)
            if date.weekday() == 4:  # Friday
                fridays.append(day)

        return len(fridays) == 5
    else:
        # Check all months
        five_friday_months = []
        for m in range(1, 13):
            if identify_five_friday_months(year=year, month=m):
                five_friday_months.append(m)

        return five_friday_months


def count_business_days(year: int, month: int) -> int:
    """
    Count business days in a month.

    Args:
        year: Year
        month: Month (1-12)

    Returns:
        Number of business days (excluding weekends)

    Example:
        >>> count_business_days(2024, 1)
        23
    """
    start_date = datetime(year, month, 1)
    if month == 12:
        end_date = datetime(year + 1, 1, 1)
    else:
        end_date = datetime(year, month + 1, 1)

    # Generate business day range
    bdays = pd.bdate_range(start=start_date, end=end_date, freq="B")

    # Filter to only include days in the target month
    bdays_in_month = bdays[bdays.month == month]

    return len(bdays_in_month)


def compute_calendar_adjustment(
    year: int, month: int, method: Literal["days", "business_days"] = "business_days"
) -> float:
    """
    Compute calendar adjustment factor to normalize month lengths.

    Adjusts for the fact that months have different numbers of days/business days.
    Factor multiplied by raw data gives "average month" equivalent.

    Args:
        year: Year
        month: Month (1-12)
        method: Adjustment method ('days' or 'business_days')

    Returns:
        Adjustment factor (ratio to average month)

    Example:
        >>> # February (short month) gets factor > 1 to normalize upward
        >>> compute_calendar_adjustment(2024, 2, method='days')
        1.034  # (30 / 29)
    """
    if method == "days":
        # Count calendar days
        days_in_month = calendar.monthrange(year, month)[1]
        avg_days = 30.437  # Average days per month (365.25 / 12)

        return avg_days / days_in_month

    elif method == "business_days":
        # Count business days
        bdays_in_month = count_business_days(year, month)
        avg_bdays = 21.7  # Average business days per month (~260 / 12)

        return avg_bdays / bdays_in_month

    else:
        raise ValueError(f"method must be 'days' or 'business_days', got {method}")


def get_holiday_calendar(year: int) -> List[datetime]:
    """
    Get U.S. federal holiday calendar.

    Args:
        year: Year for holiday calendar

    Returns:
        List of federal holiday dates

    Example:
        >>> holidays = get_holiday_calendar(2024)
        >>> len(holidays) >= 10  # At least 10 federal holidays
        True
    """
    holidays = []

    # New Year's Day (Jan 1)
    holidays.append(datetime(year, 1, 1))

    # Martin Luther King Jr. Day (3rd Monday in January)
    holidays.append(_nth_weekday(year, 1, 0, 3))  # 0 = Monday

    # Presidents' Day (3rd Monday in February)
    holidays.append(_nth_weekday(year, 2, 0, 3))

    # Memorial Day (last Monday in May)
    holidays.append(_last_weekday(year, 5, 0))

    # Juneteenth (June 19)
    holidays.append(datetime(year, 6, 19))

    # Independence Day (July 4)
    holidays.append(datetime(year, 7, 4))

    # Labor Day (1st Monday in September)
    holidays.append(_nth_weekday(year, 9, 0, 1))

    # Columbus Day (2nd Monday in October)
    holidays.append(_nth_weekday(year, 10, 0, 2))

    # Veterans Day (November 11)
    holidays.append(datetime(year, 11, 11))

    # Thanksgiving (4th Thursday in November)
    holidays.append(_nth_weekday(year, 11, 3, 4))  # 3 = Thursday

    # Christmas Day (December 25)
    holidays.append(datetime(year, 12, 25))

    logger.info("holiday_calendar_generated", year=year, holiday_count=len(holidays))

    return holidays


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> datetime:
    """
    Find the nth occurrence of a weekday in a month.

    Args:
        year: Year
        month: Month (1-12)
        weekday: Weekday (0=Monday, 6=Sunday)
        n: Occurrence number (1=first, 2=second, etc.)

    Returns:
        Date of nth weekday
    """
    # First day of month
    first_day = datetime(year, month, 1)
    first_weekday = first_day.weekday()

    # Days until target weekday
    days_ahead = (weekday - first_weekday) % 7

    # Date of first occurrence
    first_occurrence = first_day + pd.Timedelta(days=days_ahead)

    # Date of nth occurrence
    nth_occurrence = first_occurrence + pd.Timedelta(weeks=n - 1)

    return nth_occurrence


def _last_weekday(year: int, month: int, weekday: int) -> datetime:
    """
    Find the last occurrence of a weekday in a month.

    Args:
        year: Year
        month: Month (1-12)
        weekday: Weekday (0=Monday, 6=Sunday)

    Returns:
        Date of last weekday
    """
    # Last day of month
    last_day = datetime(year, month, calendar.monthrange(year, month)[1])

    # Work backwards to find last occurrence of weekday
    days_back = (last_day.weekday() - weekday) % 7
    last_occurrence = last_day - pd.Timedelta(days=days_back)

    return last_occurrence


def apply_calendar_adjustment(
    series: pd.Series, method: Literal["days", "business_days"] = "business_days"
) -> pd.Series:
    """
    Apply calendar adjustment to time series.

    Args:
        series: Monthly time series with datetime index
        method: Adjustment method

    Returns:
        Calendar-adjusted series

    Example:
        >>> adjusted = apply_calendar_adjustment(monthly_employment, method='business_days')
    """
    if not isinstance(series.index, pd.DatetimeIndex):
        raise ValueError("Series must have DatetimeIndex")

    adjusted_values = []

    for date in series.index:
        value = series.loc[date]
        adjustment = compute_calendar_adjustment(date.year, date.month, method=method)
        adjusted_values.append(value * adjustment)

    result = pd.Series(adjusted_values, index=series.index, name=series.name)

    logger.info(
        "calendar_adjustment_applied",
        series_name=series.name or "unnamed",
        method=method,
        length=len(result),
    )

    return result
