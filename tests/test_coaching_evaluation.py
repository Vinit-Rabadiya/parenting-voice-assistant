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
from scripts.evaluate_coaching import load_retrieval_capture_cases
from scripts.evaluate_coaching import keyword_search_text
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


def test_capture_records_provider_block_without_retry_or_invented_answer():
    case, _, retrieval, coaching, models = setup_case()
    models.generate_content.return_value = SimpleNamespace(
        text=None, candidates=[],
        prompt_feedback=SimpleNamespace(block_reason="PROHIBITED_CONTENT"),
    )
    record = capture_case(case, profile_dates(date(2026, 10, 20), 0), retrieval, coaching)
    assert record["outcome"] == "error"
    assert record["error_stage"] == "generation"
    assert record["answer"] is None
    assert record["attempts"][0]["prompt_block_reason"] == "PROHIBITED_CONTENT"
    assert record["attempts"][0]["has_text"] is False
    assert record["attempts"][0]["finish_reasons"] == []
    models.generate_content.assert_called_once()


def test_capture_records_general_vaccine_source_without_model_call(monkeypatch):
    monkeypatch.setattr("backend.services.vaccination.current_date", lambda: date(2026, 10, 24))
    case, _, retrieval, coaching, models = setup_case()
    case["question"] = "How do vaccines work?"
    record = capture_case(case, profile_dates(date(2026, 10, 24), 0), retrieval, coaching)
    assert record["outcome"] == "vaccination_notice"
    assert "who.int" in record["reference_sources"][0]["url"]
    assert record["answer"]
    retrieval.retrieve.assert_not_called()
    models.generate_content.assert_not_called()


def test_no_evidence_does_not_generate():
    case, _, retrieval, coaching, models = setup_case(score=0.0)
    record = capture_case(case, profile_dates(date(2026, 10, 20), 6), retrieval, coaching)
    assert record["outcome"] == "no_evidence"
    assert record["supplied_evidence"] == []
    assert record["selected_model"] is None
    models.generate_content.assert_not_called()


@pytest.mark.parametrize("question,outcome", [
    ("Which vaccines are due in Kenya?", "vaccination_notice"),
    ("How do I repair my car?", "no_evidence"),
    ("What else can I try?", "no_evidence"),
    ("Can you diagnose why my child is not talking?", "no_evidence"),
])
def test_capture_reuses_vaccination_and_unrelated_boundaries(question, outcome):
    case, _, retrieval, coaching, models = setup_case()
    case["question"] = question
    record = capture_case(case, profile_dates(date(2026, 10, 20), 6), retrieval, coaching)
    assert record["outcome"] == outcome
    retrieval.retrieve.assert_not_called()
    models.generate_content.assert_not_called()


def test_capture_uses_context_aware_missing_evidence_wording():
    case, _, retrieval, coaching, models = setup_case(score=0)
    case["question"] = "I am feeding my baby"
    record = capture_case(case, profile_dates(date(2026, 10, 20), 6), retrieval, coaching)
    assert record["response_kind"] == "insufficient_references"
    assert "baby-care topic" in record["answer"]
    models.generate_content.assert_not_called()


def test_no_evidence_follow_up_retains_the_permitted_caregiver_topic():
    case, _, retrieval, coaching, models = setup_case(score=0)
    case["question"] = "What else can I try?"
    messages = [{"role": "user", "text": "I am feeding my baby"},
                {"role": "assistant", "text": "Talk softly.", "status": "answered"}]
    record = capture_case(case, profile_dates(date(2026, 10, 24), 6), retrieval, coaching,
                          messages=messages)
    assert record["response_kind"] == "insufficient_references"
    assert "I am feeding my baby" in record["search_query"]
    assert "Talk softly." not in record["search_query"]
    assert record["supplied_evidence"] == []
    models.generate_content.assert_not_called()


def test_development_capture_reuses_pinned_dates_and_excludes_held_out(tmp_path):
    path = tmp_path / "queries.jsonl"
    base = {"date_of_birth": "2026-04-23", "evaluation_date": "2026-10-23",
            "query": "Feeding ideas", "corpus_sha256": "a" * 64}
    path.write_text("\n".join(json.dumps({**base, "id": key, "split": split})
                              for key, split in [("dev", "development"), ("final", "held_out")]), encoding="utf-8")
    selected, digest = load_retrieval_capture_cases(path)
    assert len(selected) == 1
    case, profile = selected[0]
    assert case["id"] == "dev"
    assert profile["completed_months"] == 6
    assert profile["date_of_birth"] == "2026-04-23"
    assert len(digest) == 64
    with pytest.raises(ValueError, match="development split"):
        load_retrieval_capture_cases(path, ["final"])


def test_development_capture_requires_fingerprint(tmp_path):
    path = tmp_path / "queries.jsonl"
    path.write_text(json.dumps({"id": "dev", "split": "development", "query": "Feeding",
                                "date_of_birth": "2026-04-23", "evaluation_date": "2026-10-23"}), encoding="utf-8")
    with pytest.raises(ValueError, match="fingerprint"):
        load_retrieval_capture_cases(path)


def test_capture_food_retention_concern_does_not_generate_routine_feeding_advice():
    case, _, retrieval, coaching, models = setup_case()
    case["question"] = "the child cant keep any food"
    record = capture_case(case, profile_dates(date(2026, 10, 20), 6), retrieval, coaching)
    assert record["response_kind"] == "professional_referral"
    retrieval.retrieve.assert_not_called()
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


def test_capture_caregiver_crisis_without_model_or_retrieval_calls():
    case, _, retrieval, coaching, models = setup_case()
    case["question"] = "I want to die."
    record = capture_case(case, profile_dates(date(2026, 10, 20), 6), retrieval, coaching)
    assert record["outcome"] == "crisis_support"
    assert record["caregiver_safety"]["kind"] == "crisis_support"
    retrieval.retrieve.assert_not_called()
    models.generate_content.assert_not_called()


def test_capture_follow_up_uses_bounded_context_and_caregiver_search_anchor():
    case, _, retrieval, coaching, models = setup_case()
    case["question"] = "What else can I try?"
    messages = [{"role": "user", "text": "How can I talk during feeding?"},
                {"role": "assistant", "text": "Talk softly.", "status": "answered"}]
    record = capture_case(case, profile_dates(date(2026, 10, 20), 6), retrieval, coaching,
                          messages=messages)
    assert record["outcome"] == "answered"
    assert "How can I talk during feeding?" in retrieval.retrieve.call_args.args[0]
    assert "Talk softly." not in retrieval.retrieve.call_args.args[0]
    assert "Recent conversation" in models.generate_content.call_args.kwargs["contents"]
    assert record["answer_word_count"] == 2
    assert record["within_requested_word_limit"] is True


def test_capture_does_not_reuse_context_across_safety_boundary():
    case, _, retrieval, coaching, models = setup_case()
    case["question"] = "What else can I try?"
    messages = [{"role": "user", "text": "My baby is choking."},
                {"role": "assistant", "text": "Seek urgent care.", "status": "escalated"}]
    record = capture_case(case, profile_dates(date(2026, 10, 20), 6), retrieval, coaching,
                          messages=messages)
    assert record["response_kind"] == "clarification"
    assert record["conversation_context"] == []
    retrieval.retrieve.assert_not_called()
    models.generate_content.assert_not_called()


def test_retrieval_only_records_matches_without_generation_or_an_answer():
    case, passage, retrieval, coaching, models = setup_case()
    record = capture_case(case, profile_dates(date(2026, 10, 23), 6), retrieval, coaching,
                          retrieval_only=True)
    assert record["outcome"] == "evidence_available"
    assert record["answer"] is None
    assert record["supplied_evidence"][0]["passage_id"] == passage.passage_id
    assert record["attempts"] == []
    models.generate_content.assert_not_called()


def test_keyword_baseline_preserves_negation_and_explicit_numbers():
    assert keyword_search_text("My baby isn't feeding at 38.2C") == "baby isn't feeding 38.2c"
    assert keyword_search_text("Picture-book time") == "picture book time"


def test_keyword_baseline_changes_search_but_not_the_generation_message():
    case, _, retrieval, coaching, models = setup_case()
    case["question"] = "How can I share a picture-book?"
    record = capture_case(case, profile_dates(date(2026, 10, 23), 6), retrieval, coaching,
                          keyword_search=True)
    assert retrieval.retrieve.call_args.args[0] == "share picture book"
    assert "Caregiver question: How can I share a picture-book?" in record["attempts"][0]["prompt"]
    assert record["search_query"] == "share picture book"
