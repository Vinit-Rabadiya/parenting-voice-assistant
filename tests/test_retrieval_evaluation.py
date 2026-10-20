import json
from datetime import date
from unittest.mock import MagicMock

import pytest

from backend.core.config import PROJECT_ROOT
from scripts.evaluate_retrieval import build_report, evaluate_query, load_queries, query_age_context


@pytest.fixture
def evaluation_case():
    return {
        "id": "date-case", "category": "age_boundary", "query": "Play ideas",
        "date_of_birth": "2026-04-20", "evaluation_date": "2026-10-20",
        "routine": None, "limit": 4, "expected_passage_ids": [], "forbidden_passage_ids": [],
    }


@pytest.mark.parametrize("birth,evaluated,months", [
    ("2026-10-14", "2026-10-20", 0),
    ("2026-10-13", "2026-10-20", 0),
    ("2026-04-21", "2026-10-20", 5),
    ("2026-04-20", "2026-10-20", 6),
    ("2026-01-31", "2026-02-28", 1),
    ("2024-02-29", "2026-02-28", 24),
])
def test_evaluation_forwards_exact_age_and_records_dates(evaluation_case, birth, evaluated, months):
    evaluation_case.update(date_of_birth=birth, evaluation_date=evaluated)
    service = MagicMock()
    service.retrieve.return_value = []
    result = evaluate_query(service, evaluation_case)
    days = (date.fromisoformat(evaluated) - date.fromisoformat(birth)).days
    service.retrieve.assert_called_once_with(
        query="Play ideas", child_age_months=months, child_age_days=days, routine=None, limit=4,
    )
    assert result["date_of_birth"] == birth
    assert result["evaluation_date"] == evaluated
    assert result["child_age_days"] == days
    assert result["completed_months"] == months


def test_rounded_display_age_never_controls_retrieval(evaluation_case):
    evaluation_case["date_of_birth"] = "2026-04-21"
    service = MagicMock()
    service.retrieve.return_value = []
    result = evaluate_query(service, evaluation_case)
    assert result["child_age_months"] == 6.0  # Rounded display only, as in profiles.
    assert service.retrieve.call_args.kwargs["child_age_months"] == 5


@pytest.mark.parametrize("changes", [
    {"date_of_birth": None}, {"evaluation_date": None},
    {"date_of_birth": "2026-02-30"}, {"evaluation_date": "today"},
    {"date_of_birth": "20260420"},
    {"date_of_birth": "2026-10-21"},
    {"date_of_birth": "2024-10-19"},
    {"child_age_months": 6}, {"child_age_days": 183}, {"completed_months": 6},
])
def test_invalid_or_precomputed_age_fails_before_retrieval(evaluation_case, changes):
    evaluation_case.update(changes)
    service = MagicMock()
    with pytest.raises(ValueError):
        evaluate_query(service, evaluation_case)
    service.retrieve.assert_not_called()


def test_legacy_months_only_case_is_rejected(evaluation_case):
    del evaluation_case["date_of_birth"]
    del evaluation_case["evaluation_date"]
    evaluation_case["child_age_months"] = 6
    with pytest.raises(ValueError, match="date_of_birth"):
        query_age_context(evaluation_case)


def test_loader_validates_every_case_with_line_number(tmp_path, evaluation_case):
    path = tmp_path / "queries.jsonl"
    path.write_text(json.dumps(evaluation_case) + '\n{"id":"missing-dates"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="Query line 2: date_of_birth"):
        load_queries(path)


@pytest.mark.parametrize("contents", ["", "\n", "[]\n", "{broken\n"])
def test_loader_rejects_empty_or_malformed_cases(tmp_path, contents):
    path = tmp_path / "queries.jsonl"
    path.write_text(contents, encoding="utf-8")
    with pytest.raises(ValueError):
        load_queries(path)


def test_versioned_cases_have_explicit_valid_dates():
    cases = load_queries(PROJECT_ROOT / "data/evaluation/retrieval-queries.jsonl")
    assert len(cases) == 12
    assert all(case["evaluation_date"] == "2026-10-20" for case in cases)
    assert query_age_context(cases[0])["child_age_days"] == 3
    assert query_age_context(cases[1])["completed_months"] == 6


def test_report_identifies_exact_age_schema(evaluation_case):
    service = MagicMock()
    service.retrieve.return_value = []
    result = evaluate_query(service, evaluation_case)
    report = build_report([evaluation_case], [result])
    assert report["schema_version"] == 2
    assert "fixed case dates" in report["configuration"]["age_policy"]
    assert report["queries"][0]["child_age_days"] == 183
