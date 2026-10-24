from datetime import date

import pytest

from scripts.prepare_coverage_review import coverage_markdown, prepare_review


def passage():
    return {"passage_id": "p1", "source_id": "source", "source_age": {
        "min_months": 6, "max_months_exclusive": 12}, "routines": ["feeding"],
        "developmental_domain": "nutrition"}


def test_review_does_not_treat_age_eligibility_as_relevance():
    inventory = {"evaluation_date": "2026-10-22", "cases": [
        {"id": "q1", "date_of_birth": "2026-04-22", "query": "Feeding ideas"},
        {"id": "q2", "date_of_birth": "2026-08-22", "query": "Feeding ideas"}]}
    cases = prepare_review([passage()], inventory)
    assert cases[0]["age_eligible_passage_ids"] == ["p1"]
    assert cases[1]["age_eligible_passage_ids"] == []
    assert all(case["expected_passage_ids"] is None for case in cases)
    assert all(case["review_status"] == "pending" for case in cases)


def test_out_of_scope_case_is_not_sent_through_retrieval_age_validation():
    inventory = {"evaluation_date": "2026-10-22", "cases": [
        {"id": "q1", "date_of_birth": "2024-10-21", "category": "out_of_scope", "query": "Play"}]}
    case = prepare_review([passage()], inventory)[0]
    assert case["age_context"] is None
    assert case["age_eligible_passage_ids"] == []


def test_coverage_includes_missing_routines_without_claiming_accuracy():
    report = coverage_markdown([passage()], date(2026, 10, 24))
    assert "| 6 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |" in report
    assert "not semantic relevance" in report
    assert "not classified" not in report


@pytest.mark.parametrize("evaluated,expected_days", [
    (date(2025, 10, 24), 731), (date(2026, 10, 24), 730),
])
def test_coverage_uses_exact_calendar_days_at_second_birthday(monkeypatch, evaluated, expected_days):
    from scripts import prepare_coverage_review as review

    ages = []
    original = review.is_age_eligible

    def observe(source_age, months, *, child_age_days):
        ages.append((months, child_age_days))
        return original(source_age, months, child_age_days=child_age_days)

    monkeypatch.setattr(review, "is_age_eligible", observe)
    report = review.coverage_markdown([passage()], evaluated)
    assert (24, expected_days) in ages
    assert (0, 11) in ages
    assert f"Evaluation date: {evaluated.isoformat()}" in report


def test_coverage_rejects_leap_day_without_an_exact_second_birthday_profile():
    with pytest.raises(ValueError, match="exact age checkpoint"):
        coverage_markdown([passage()], date(2024, 2, 29))
