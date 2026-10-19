"""Calendar-based child age calculations shared by profiles and retrieval."""

from calendar import monthrange
from datetime import date, datetime, timedelta, timezone


def current_date() -> date:
    return datetime.now(timezone(timedelta(hours=3))).date()


def add_months(birth_date: date, months: int) -> date:
    """Use the last day of a shorter month for birthdays such as January 31."""
    year, month_index = divmod(birth_date.year * 12 + birth_date.month - 1 + months, 12)
    month = month_index + 1
    return date(year, month, min(birth_date.day, monthrange(year, month)[1]))


def age_details(birth_date: date, today: date | None = None) -> tuple[int, int, float]:
    """Return exact days, completed calendar months, and a fractional display age."""
    today = today or current_date()
    if birth_date > today:
        raise ValueError("Date of birth cannot be in the future.")
    months = (today.year - birth_date.year) * 12 + today.month - birth_date.month
    if today < add_months(birth_date, months):
        months -= 1
    start, end = add_months(birth_date, months), add_months(birth_date, months + 1)
    fraction = (today - start).days / (end - start).days
    return (today - birth_date).days, months, months + fraction
