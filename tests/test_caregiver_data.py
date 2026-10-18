from datetime import date

import pytest

from backend.services.caregiver_data import baseline_milestones, calculate_age


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
