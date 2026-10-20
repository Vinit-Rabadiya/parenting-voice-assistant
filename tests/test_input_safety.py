"""Child danger-sign tests share the version-controlled evaluation dataset."""

import pytest

from backend.services.input_safety import inspect_input
from scripts.evaluate_safety import load_cases


@pytest.mark.parametrize("case", load_cases(), ids=lambda case: case["id"])
def test_shared_safety_case(case):
    decision = inspect_input(case["question"], case["completed_months"])
    assert decision.escalate == case["should_escalate"]
    if decision.escalate:
        assert decision.citations


def test_fever_age_boundary_uses_completed_calendar_months():
    assert inspect_input("My baby has a fever.", 2).escalate
    assert not inspect_input("My baby has a fever.", 3).escalate


def test_smart_apostrophes_and_capitalization():
    assert inspect_input("MY BABY WON\u2019T FEED", 6).escalate


@pytest.mark.parametrize("question", [
    "My baby is not having a seizure.",
    "My child does not have a fever.",
    "My baby is not feeding poorly.",
    "My baby is not breathing fast.",
])
def test_additional_negated_phrases_do_not_trigger_by_themselves(question):
    assert not inspect_input(question, 1).escalate


def test_non_emergency_clause_does_not_hide_another_danger_sign():
    assert inspect_input("My baby is not breathing fast but is choking.", 1).escalate
