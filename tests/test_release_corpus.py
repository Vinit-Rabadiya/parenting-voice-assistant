"""Everyday release selection must not publish blocked clinical candidates."""
from copy import deepcopy
from datetime import date

import pytest

from scripts.prepare_release_corpus import select_release_passages


def fixture():
    original = [{"passage_id": "old", "source_id": "original", "text": "Existing reference."}]
    new = {"passage_id": "new", "source_id": "checked", "source_url": "https://example.test/care",
           "text": "Talk together during everyday care.", "developmental_domain": "language",
           "review_status": "candidate_not_expert_validated"}
    plan = {"schema_version": 1, "review_kind": "editorial_source_check_not_clinical_validation",
            "country": "KE", "language": "English", "checked_on": "2026-10-24",
            "review_interval_days": 90, "expected_additions": 1,
            "source_checks": [{"source_id": "checked", "url": new["source_url"], "finding": "Checked section."}]}
    return original, new, plan


def test_release_preserves_baseline_and_source_text_without_mutating_candidates():
    original, new, plan = fixture()
    candidate = original + [new]
    before = deepcopy(candidate)
    selected = select_release_passages(candidate, original, plan, evaluated=date(2026, 10, 24))
    assert selected[0] == original[0]
    assert selected[1]["text"] == new["text"]
    assert selected[1]["review_status"] == "editorially_selected_not_expert_validated"
    assert candidate == before


@pytest.mark.parametrize("change", [
    {"clinical_review_required": True}, {"clinical_review_required": "false"},
    {"release_status": "blocked_pending_health_review"},
    {"developmental_domain": "immunisation"}, {"developmental_domain": "common_concerns"},
])
def test_release_rejects_health_candidates_even_under_a_checked_source(change):
    original, new, plan = fixture()
    with pytest.raises(ValueError, match="Health-review"):
        select_release_passages(original + [{**new, **change}], original, plan, evaluated=date(2026, 10, 24))


@pytest.mark.parametrize("change", ["missing_base", "changed_base", "source_url", "count", "duplicate_source"])
def test_release_rejects_changes_outside_the_pinned_inventory(change):
    original, new, plan = fixture()
    candidate = deepcopy(original) + [new]
    if change == "missing_base":
        candidate = [new]
    elif change == "changed_base":
        candidate[0]["text"] = "Changed reference."
    elif change == "source_url":
        new["source_url"] = "https://example.test/different"
    elif change == "count":
        plan["expected_additions"] = 2
    else:
        plan["source_checks"] *= 2
    with pytest.raises(ValueError):
        select_release_passages(candidate, original, plan, evaluated=date(2026, 10, 24))


@pytest.mark.parametrize("evaluated", [date(2026, 10, 23), date(2027, 2, 1)])
def test_release_rejects_future_or_expired_source_checks(evaluated):
    original, new, plan = fixture()
    with pytest.raises(ValueError, match="refresh"):
        select_release_passages(original + [new], original, plan, evaluated=evaluated)


def test_explicit_nonclinical_scope_correction_preserves_its_audit_trail():
    original, new, plan = fixture()
    new.update(clinical_review_required=True, release_status="blocked_pending_health_review")
    plan["nonclinical_scope_corrections"] = [{"source_id": "checked", "passage_ids": ["new"],
                                             "reason": "Book-sharing activity, not clinical advice."}]
    selected = select_release_passages(original + [new], original, plan, evaluated=date(2026, 10, 24))
    assert selected[1]["clinical_review_required"] is False
    assert selected[1]["original_release_status"] == "blocked_pending_health_review"
    assert new["clinical_review_required"] is True


@pytest.mark.parametrize("domain", ["immunisation", "common_concerns", "nutrition", "safety"])
def test_scope_correction_cannot_publish_clinical_or_other_unreviewed_domains(domain):
    original, new, plan = fixture()
    new.update(developmental_domain=domain, clinical_review_required=True)
    plan["nonclinical_scope_corrections"] = [{"source_id": "checked", "passage_ids": ["new"], "reason": "Attempted correction."}]
    with pytest.raises(ValueError, match="nonclinical development"):
        select_release_passages(original + [new], original, plan, evaluated=date(2026, 10, 24))
