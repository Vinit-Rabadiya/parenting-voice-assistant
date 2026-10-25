from datetime import date
import hashlib
import json
from pathlib import Path

import pytest

from scripts.prepare_coverage_review import apply_domain_review, audit_findings, coverage_markdown, prepare_review


def domain_review_fixture():
    source = {**passage(), "text": "Talk softly with your baby."}
    raw = json.dumps(source).encode()
    review = {"schema_version": 1, "status": "editorial_classification_not_expert_validation",
              "base_corpus_sha256": hashlib.sha256(raw).hexdigest(),
              "annotations": [["p1", ["language", "responsive_caregiving"], "Talk softly"]]}
    return source, raw, review


def test_domain_classification_is_an_audit_copy_not_a_source_edit():
    source, raw, review = domain_review_fixture()
    result = apply_domain_review([source], review, raw)
    assert result[0]["developmental_domains"] == ["language", "responsive_caregiving"]
    assert "developmental_domains" not in source
    assert result[0]["text"] == source["text"]


@pytest.mark.parametrize("change", ["fingerprint", "anchor", "missing", "duplicate", "domain", "text"])
def test_domain_review_rejects_stale_or_incomplete_annotations(change):
    source, raw, review = domain_review_fixture()
    if change == "fingerprint":
        review["base_corpus_sha256"] = "old"
    elif change == "anchor":
        review["annotations"][0][2] = "Not in the source"
    elif change == "missing":
        review["annotations"] = []
    elif change == "duplicate":
        review["annotations"] *= 2
    elif change == "domain":
        review["annotations"][0][1] = ["made_up"]
    else:
        source = {**source, "text": "Changed source text."}
    with pytest.raises(ValueError):
        apply_domain_review([source], review, raw)


def test_original_domain_review_covers_the_actual_prepared_corpus():
    root = Path(__file__).resolve().parents[1]
    path = root / "data/processed/rag/passages.jsonl"
    if not path.exists():
        pytest.skip("Prepared source corpus is required for editorial anchor verification.")
    raw = path.read_bytes()
    sources = [json.loads(line) for line in raw.splitlines()]
    review = json.loads((root / "data/passage-domain-review.json").read_text())
    result = apply_domain_review(sources, review, raw)
    assert len(result) == 106
    assert all(item["developmental_domains"] for item in result)


def test_audit_flags_containment_and_source_dates_without_removing_content():
    text = "Share a picture book together and talk about the pictures while following the baby's interest."
    first = {**passage(), "text": text, "source_next_review_due": "2026-01-01",
             "release_status": "blocked_pending_health_review"}
    second = {**first, "passage_id": "p2", "text": text + " Let the baby turn a page."}
    third = {**second, "passage_id": "p3", "source_id": "another-source"}
    findings = audit_findings([first, second, third], date(2026, 10, 24))
    assert findings["contained_pairs"] == [["p1", "p2"]]
    assert findings["health_review_blocked"] == 3
    assert findings["sources_past_review_due"] == ["another-source", "source"]


def passage():
    return {"passage_id": "p1", "source_id": "source", "source_age": {
        "min_months": 6, "max_months_exclusive": 12}, "routines": ["feeding"],
        "developmental_domain": "nutrition", "text": "Follow your baby's cues during feeding."}


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
