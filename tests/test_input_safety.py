"""English danger-sign examples and benign look-alikes; not clinical certification."""

import pytest

from backend.services.input_safety import inspect_input


@pytest.mark.parametrize("question,months", [
    ("My baby cannot breathe.", 6),
    ("My child is not breathing.", 12),
    ("My infant stopped breathing.", 0),
    ("She is struggling to breathe.", 3),
    ("My baby has difficulty breathing.", 4),
    ("My baby is breathing very fast.", 6),
    ("My child is gasping.", 12),
    ("My baby cannot feed.", 6),
    ("My baby won't drink.", 6),
    ("My infant is unable to breastfeed.", 0),
    ("My child is not feeding.", 12),
    ("My baby is drinking poorly.", 6),
    ("My baby is having a seizure.", 6),
    ("My child has convulsions.", 12),
    ("My infant is convulsing.", 0),
    ("My baby is unconscious.", 6),
    ("My child is unresponsive.", 12),
    ("My baby is hard to wake.", 6),
    ("My baby is lethargic.", 6),
    ("My baby is dehydrated.", 6),
    ("My baby has no wet nappies.", 6),
    ("My baby hasn't urinated.", 6),
    ("My child is choking.", 12),
    ("My baby choked on food.", 6),
    ("My baby fell off the bed.", 6),
    ("My child fell down the stairs.", 12),
    ("My baby hit her head.", 6),
    ("My newborn has a fever.", 0),
    ("My baby feels unusually cold.", 2),
    ("My baby has no fever but is choking.", 1),
])
def test_recognized_danger_reports_escalate(question, months):
    decision = inspect_input(question, months)
    assert decision.escalate
    assert decision.citations


@pytest.mark.parametrize("question", [
    "How can I talk to my baby during feeding?",
    "I am feeding my baby.",
    "My child is playing with a ball.",
    "My baby smiles when I sing.",
    "My baby is feeding normally.",
    "My baby is drinking well.",
    "My child is learning to hold a cup.",
    "How can I share a book with my baby?",
    "My baby is sleeping peacefully.",
    "My baby falls asleep after feeding.",
    "My baby is sleepy at bedtime.",
    "My baby is awake and looking at me.",
    "My child has no seizures.",
    "My baby is not choking.",
    "My baby is not dehydrated.",
    "My baby is not unconscious.",
    "My baby has no fever.",
    "My baby is breathing normally.",
    "How can I prevent choking in my baby?",
    "How do I avoid choking when my child eats?",
    "How can I prevent dehydration in my baby?",
    "How can I prevent head injury in my child?",
    "My baby is learning to grasp toys.",
    "My child dropped a toy on the floor.",
    "My baby is playing on a mat.",
    "How can I talk during my baby's bath?",
    "My child points at pictures.",
    "My baby copies my sounds.",
    "My baby is moving her arms during play.",
    "My baby watches me getting dressed.",
])
def test_selected_benign_wording_is_not_flagged(question):
    assert not inspect_input(question, 1).escalate


def test_fever_age_boundary_uses_completed_calendar_months():
    assert inspect_input("My baby has a fever.", 2).escalate
    assert not inspect_input("My baby has a fever.", 3).escalate


def test_smart_apostrophes_and_capitalization():
    assert inspect_input("MY BABY WON\u2019T FEED", 6).escalate
