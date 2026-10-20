"""Offline capture checks; no Qdrant, Gemini or Firestore requests."""

from datetime import date
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from google.genai import errors

from backend.services.coaching import CoachingService
from backend.services.retrieval import RetrievedPassage
from scripts.evaluate_coaching import QUESTION_SET_PATH, capture_case, load_cases, profile_dates
from backend.core.config import PROJECT_ROOT
from backend.services.response_safety import SAFE_RESPONSE


def setup_case(score=0.9):
    case = {"id": "aq01", "question": "Talk while feeding?", "routine": "feeding"}
    reference = RetrievedPassage("p1", "Talk to your baby.", "Talk", "Source", 1,
                                 "https://example.test", score, "0-6 months", ["feeding"])
    retrieval = Mock()
    retrieval.retrieve.return_value = [reference]
    models = SimpleNamespace(generate_content=Mock(return_value=SimpleNamespace(text="Talk softly.")))
    coaching = CoachingService(model="primary", fallback_model="fallback",
                               client=SimpleNamespace(models=models))
    return case, reference, retrieval, coaching, models


def test_versioned_cases_and_calendar_profiles_without_git_history(monkeypatch):
    def no_git(*args):
        raise AssertionError("Loading evaluation cases must not call Git.")

    monkeypatch.setattr("scripts.evaluate_coaching.git_output", no_git)
    cases, digest = load_cases()
    assert len(cases) == 40
    assert len(digest) == 64
    assert cases["aq10"]["target_months"] == 3
    profile = profile_dates(date(2026, 10, 20), 24)
    assert profile["date_of_birth"] == "2024-10-20"
    assert profile["completed_months"] == 24


def test_question_set_hash_ignores_formatting_but_detects_content_changes(tmp_path):
    data = json.loads((PROJECT_ROOT / QUESTION_SET_PATH).read_text(encoding="utf-8"))
    path = tmp_path / "questions.json"
    path.write_text(json.dumps(data, indent=4) + "\r\n", encoding="utf-8")
    _, original = load_cases()
    assert load_cases(path)[1] == original
    data["cases"][0]["question"] = "A different evaluation input"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert load_cases(path)[1] != original


@pytest.mark.parametrize("change", ["duplicate", "missing", "age", "question", "version"])
def test_invalid_question_data_is_rejected(tmp_path, change):
    data = json.loads((PROJECT_ROOT / QUESTION_SET_PATH).read_text(encoding="utf-8"))
    if change == "duplicate":
        data["cases"][-1] = data["cases"][0]
    elif change == "missing":
        data["cases"].pop()
    elif change == "age":
        data["cases"][0]["target_months"] = True
    elif change == "question":
        data["cases"][0]["question"] = " "
    else:
        data["question_set_version"] = "unknown"
    path = tmp_path / "questions.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        load_cases(path)


def test_capture_preserves_exact_evidence_and_answer():
    case, passage, retrieval, coaching, models = setup_case()
    record = capture_case(case, profile_dates(date(2026, 10, 20), 0), retrieval, coaching)
    assert record["outcome"] == "answered"
    assert record["supplied_evidence"][0]["text"] == passage.text
    assert passage.text in record["attempts"][0]["prompt"]
    assert record["answer"] == "Talk softly."
    assert record["selected_model"] == "primary"
    assert record["ratings"] is None
    models.generate_content.assert_called_once()
    assert retrieval.retrieve.call_args.kwargs["child_age_days"] == 0


def test_no_evidence_does_not_generate():
    case, _, retrieval, coaching, models = setup_case(score=0.0)
    record = capture_case(case, profile_dates(date(2026, 10, 20), 6), retrieval, coaching)
    assert record["outcome"] == "no_evidence"
    assert record["supplied_evidence"] == []
    assert record["selected_model"] is None
    models.generate_content.assert_not_called()


def test_fallback_capture_uses_actual_model_and_identical_prompt():
    case, _, retrieval, coaching, models = setup_case()
    models.generate_content.side_effect = [
        errors.ClientError(429, {"error": {"message": "quota"}}),
        SimpleNamespace(text="Talk softly."),
    ]
    record = capture_case(case, profile_dates(date(2026, 10, 20), 6), retrieval, coaching)
    assert record["outcome"] == "answered"
    assert record["selected_model"] == "fallback"
    assert record["fallback_used"] is True
    assert record["attempts"][0]["prompt"] == record["attempts"][1]["prompt"]


def test_error_record_does_not_include_exception_description():
    case, _, retrieval, coaching, models = setup_case()
    models.generate_content.side_effect = RuntimeError("PRIVATE_DETAILS")
    record = capture_case(case, profile_dates(date(2026, 10, 20), 6), retrieval, coaching)
    assert record["outcome"] == "error"
    assert record["error_stage"] == "generation"
    assert record["error_type"] == "RuntimeError"
    assert "PRIVATE_DETAILS" not in str(record)


def test_capture_records_blocked_outcome_without_unsafe_generated_text():
    case, _, retrieval, coaching, models = setup_case()
    models.generate_content.return_value = SimpleNamespace(text="Give 5 mg of medicine.")
    record = capture_case(case, profile_dates(date(2026, 10, 20), 6), retrieval, coaching)
    assert record["outcome"] == "safety_blocked"
    assert record["answer"] == SAFE_RESPONSE
    assert record["safety"]["blocked"]
    assert "Give 5 mg of medicine." not in str(record)


def test_capture_danger_report_skips_all_external_requests():
    case, _, retrieval, coaching, models = setup_case()
    case["question"] = "My baby is choking."
    record = capture_case(case, profile_dates(date(2026, 10, 20), 6), retrieval, coaching)
    assert record["outcome"] == "escalated"
    assert record["input_safety"]["escalate"]
    assert record["referral_sources"]
    assert record["selected_model"] is None
    retrieval.retrieve.assert_not_called()
    models.generate_content.assert_not_called()
