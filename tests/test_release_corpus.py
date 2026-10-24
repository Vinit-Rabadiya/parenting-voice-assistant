"""Everyday release selection must not publish blocked clinical candidates."""
from copy import deepcopy
from datetime import date

import pytest

from scripts.prepare_release_corpus import select_release_passages
from scripts.prepare_release_corpus import revise_source
from scripts.build_reference_expansion import compile_expansion, fingerprint


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


def source_revision_fixture():
    pack = {"schema_version": 1, "status": "candidate_not_expert_validated", "checked_on": "2026-10-24",
            "sources": [{"source_id": "checked", "title": "Bathing", "publisher": "NHS",
                         "source_url": "https://www.nhs.uk/baby/bathing", "age": [0, 12],
                         "passages": [{"section": "Washing", "domain": "responsive_caregiving",
                                       "routines": ["bathing"], "text": "Talk gently during washing so your baby hears your familiar voice."}]}]}
    records, manifest, _ = compile_expansion(pack, [], {"sources": []})
    updated = deepcopy(pack)
    updated["sources"][0]["passages"][0]["text"] += " Wash selected areas outside the bath."
    revision = {"source_id": "checked", "pack_sha256": fingerprint(updated)}
    return pack, records, manifest, updated, revision


def test_source_revision_updates_text_and_provenance_without_mutating_input():
    _, records, manifest, pack, revision = source_revision_fixture()
    before = deepcopy(records)
    revised, revised_manifest = revise_source(records, manifest, pack, revision, set())
    assert records == before
    assert revised[0]["passage_id"] == records[0]["passage_id"]
    assert revised[0]["source_age"] == records[0]["source_age"]
    assert revised[0]["text"] != records[0]["text"]
    assert revised[0]["source_sha256"] == revised_manifest["sources"][0]["sha256"]
    assert revised[0]["source_sha256"] != manifest["sources"][0]["sha256"]
    assert revise_source(revised, revised_manifest, pack, revision, set())[0] == revised


@pytest.mark.parametrize("mutation", ["fingerprint", "age", "conditions", "baseline", "clinical"])
def test_source_revision_rejects_unreviewed_content_or_scope_changes(mutation):
    _, records, manifest, pack, revision = source_revision_fixture()
    original_ids = set()
    if mutation == "fingerprint":
        revision["pack_sha256"] = "0" * 64
    elif mutation == "baseline":
        original_ids.add(records[0]["passage_id"])
    elif mutation == "clinical":
        records[0]["clinical_review_required"] = True
    else:
        item = pack["sources"][0]["passages"][0]
        item.update({"age": [0, 6]} if mutation == "age" else {"applicability_conditions": ["A new condition"]})
        revision["pack_sha256"] = fingerprint(pack)
    with pytest.raises(ValueError):
        revise_source(records, manifest, pack, revision, original_ids)
