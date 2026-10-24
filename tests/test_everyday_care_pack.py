from copy import deepcopy
import json

import pytest

from scripts.build_reference_expansion import ROOT, compile_expansion


def pack():
    return json.loads((ROOT / "data/everyday-care-reference-expansion.json").read_text(encoding="utf-8"))


def test_everyday_care_preserves_source_dates_and_health_review_gate():
    records, manifest, report = compile_expansion(pack(), [], {"sources": []})
    assert len(records) == 24
    assert len(manifest["sources"]) == 7
    assert all(p["release_status"] == "blocked_pending_health_review" for p in records)
    assert all(p["source_format"] == "web_summary" and p["pdf_page"] is None for p in records)
    assert set(report["sources_past_stated_review_due"]) == {
        "nhs-formula-preparation-principles", "nhs-toddler-sleep-routines"}
    crying = next(p for p in records if p["source_id"] == "nhs-crying-patterns-and-support")
    assert crying["source_reviewed_on"] == "2026-04-22"
    assert crying["source_freshness"] == "within_stated_review_window"


def test_age_ranges_do_not_apply_toddler_sleep_to_newborns_or_formula_to_toddlers():
    from backend.services.retrieval import is_age_eligible
    records, _, _ = compile_expansion(pack(), [], {"sources": []})
    sleep = next(p for p in records if p["source_id"] == "nhs-toddler-sleep-routines")
    formula = next(p for p in records if p["source_id"] == "nhs-formula-preparation-principles")
    assert not is_age_eligible(sleep["source_age"], 0, child_age_days=11)
    assert is_age_eligible(sleep["source_age"], 24, child_age_days=730)
    assert not is_age_eligible(formula["source_age"], 12)


@pytest.mark.parametrize("field,value", [("source_reviewed_on", "20261022"),
                                        ("source_reviewed_on", "2027-01-01"),
                                        ("source_next_review_due", "not-a-date"),
                                        ("applicability_note", "")])
def test_invalid_source_review_metadata_is_rejected(field, value):
    changed = deepcopy(pack())
    changed["sources"][0][field] = value
    with pytest.raises(ValueError):
        compile_expansion(changed, [], {"sources": []})
