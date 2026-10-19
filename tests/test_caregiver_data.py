from datetime import date

import pytest

from backend.services.caregiver_data import baseline_milestones, calculate_age
from backend.services.age import add_months, age_details


def test_calculate_age_returns_server_calculated_display_values():
    age_days, age_months, age_label = calculate_age(date(2026, 1, 18), today=date(2026, 10, 18))

    assert age_days == 273
    assert age_months == 9.0
    assert age_label == "9 months"


def test_calculate_age_rejects_future_date_of_birth():
    with pytest.raises(ValueError, match="future"):
        calculate_age(date(2026, 10, 19), today=date(2026, 10, 18))


def test_baseline_milestones_follow_the_calculated_age_band():
    milestones = baseline_milestones(6.0)

    assert "Sits without support" in milestones


def test_calendar_age_does_not_round_into_next_retrieval_band():
    days, months, display = age_details(date(2026, 1, 20), date(2026, 7, 19))
    assert days == 180
    assert months == 5
    assert display < 6
    assert age_details(date(2026, 1, 20), date(2026, 7, 20))[:2] == (181, 6)


def test_month_end_and_leap_year_birthdays():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2024, 2, 29), 12) == date(2025, 2, 28)
    assert age_details(date(2026, 1, 31), date(2026, 2, 28))[1] == 1
