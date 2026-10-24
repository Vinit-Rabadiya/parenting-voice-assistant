"""Offline reference preparation checks, not clinical or answer-quality approval."""
from copy import deepcopy
import json

import pytest

from backend.services.retrieval import is_age_eligible
from scripts.build_reference_expansion import ROOT, compile_expansion, replace_source_revisions


def pack():
    return json.loads((ROOT / "data/practical-care-reference-expansion.json").read_text(encoding="utf-8"))


def test_practical_pack_preserves_sections_conditions_and_health_gate():
    records, manifest, report = compile_expansion(pack(), [], {"sources": []})
    assert len(records) == 77
    assert len(manifest["sources"]) == 25
    assert report["index_built"] is False
    assert all(p["source_heading"] and p["pdf_page"] is None for p in records)
    assert all(p["release_status"] == "blocked_pending_health_review" for p in records)
    assert {p["guidance_kind"] for p in records} == {"explanation", "practical_action", "precaution", "referral"}
    assert any(p.get("applicability_conditions") for p in records)


@pytest.mark.parametrize("source_id,months,eligible", [
    ("nhs-first-foods-practical", 5, False), ("nhs-first-foods-practical", 6, True),
    ("nhs-toddler-food-refusal", 6, False), ("nhs-toddler-food-refusal", 12, True),
    ("nhs-baby-reflux", 12, False), ("nhs-newborn-jaundice-education", 1, False),
    ("unicef-childcare-separation-support", 3, False),
    ("nhs-toddler-food-refusal", 24, True),
])
def test_selected_age_boundaries(source_id, months, eligible):
    records, _, _ = compile_expansion(pack(), [], {"sources": []})
    record = next(p for p in records if p["source_id"] == source_id)
    assert is_age_eligible(record["source_age"], months) is eligible


def test_shade_passage_does_not_apply_its_under_six_month_condition_to_older_children():
    records, _, _ = compile_expansion(pack(), [], {"sources": []})
    shade = next(p for p in records if p["title"] == "Shade for a young baby outside")
    assert is_age_eligible(shade["source_age"], 0, child_age_days=11)
    assert not is_age_eligible(shade["source_age"], 6)


def old_inputs():
    health = json.loads((ROOT / "data/health-reference-expansion.json").read_text(encoding="utf-8"))
    earlier = json.loads((ROOT / "data/reference-expansion.json").read_text(encoding="utf-8"))
    earlier["sources"] = [s for s in earlier["sources"] if s["source_id"] in {"unicef-feeding-12-24-months", "unicef-development-24-months"}]
    records, manifest, _ = compile_expansion(earlier, [], {"sources": []})
    records, manifest, _ = compile_expansion(health, records, manifest)
    return records, manifest


def test_explicit_replacement_removes_only_named_sources_without_mutating_input():
    base, manifest = old_inputs()
    original = deepcopy((base, manifest))
    retained, revised, removed = replace_source_revisions(pack(), base, manifest)
    assert removed == 15
    assert (base, manifest) == original
    records, new_manifest, _ = compile_expansion(pack(), retained, revised)
    assert len(records) == 87
    assert len(new_manifest["sources"]) == 31
    assert len({p["passage_id"] for p in records}) == len(records)
    assert {p["source_id"] for p in retained}.isdisjoint(pack()["replacement_sources"])


@pytest.mark.parametrize("mutation", ["unknown", "different_url", "duplicate", "missing_passages"])
def test_replacement_requires_known_unique_ids_and_unchanged_source_url(mutation):
    candidate = pack()
    base, manifest = old_inputs()
    if mutation == "unknown":
        candidate["replacement_sources"].append("missing-source")
    elif mutation == "different_url":
        source = next(s for s in candidate["sources"] if s["source_id"] == candidate["replacement_sources"][0])
        source["source_url"] += "?different-resource"
    elif mutation == "duplicate":
        candidate["replacement_sources"].append(candidate["replacement_sources"][0])
    else:
        base = [p for p in base if p["source_id"] != candidate["replacement_sources"][0]]
    with pytest.raises(ValueError):
        replace_source_revisions(candidate, base, manifest)


@pytest.mark.parametrize("field,value", [("source_heading", ""), ("guidance_kind", "diagnosis"),
                                        ("applicability_conditions", [""])])
def test_invalid_selection_metadata_is_rejected(field, value):
    candidate = pack()
    candidate["sources"][0]["passages"][0][field] = value
    with pytest.raises(ValueError):
        compile_expansion(candidate, [], {"sources": []})


def test_revised_food_refusal_selection_omits_incomplete_food_reuse_instruction():
    records, _, _ = compile_expansion(pack(), [], {"sources": []})
    revised = [p for p in records if p["source_id"] == "unicef-feeding-12-24-months"]
    assert len(revised) == 3
    assert all("cover refused food" not in p["text"].lower() for p in revised)


@pytest.mark.parametrize("source_id,months,eligible", [
    ("nhs-talk-0-6-months", 3, True), ("nhs-talk-0-6-months", 6, False),
    ("nhs-talk-6-12-months", 6, True), ("nhs-talk-6-12-months", 12, False),
    ("nhs-talk-12-24-months", 12, True), ("nhs-talk-12-24-months", 24, False),
    ("nhs-talk-24-months", 23, False), ("nhs-talk-24-months", 24, True),
])
def test_communication_passages_preserve_source_age_bands(source_id, months, eligible):
    records, _, _ = compile_expansion(pack(), [], {"sources": []})
    passage = next(p for p in records if p["source_id"] == source_id)
    assert is_age_eligible(passage["source_age"], months) is eligible
