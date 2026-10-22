from copy import deepcopy
import json
from unittest.mock import MagicMock

import pytest

from scripts.build_reference_expansion import ROOT, compile_expansion
from scripts.index_rag import load_passages, validate_source_references
from scripts.index_rag import main as index_main


@pytest.fixture
def pack():
    return json.loads((ROOT / "data/reference-expansion.json").read_text(encoding="utf-8"))


def test_candidate_build_is_repeatable_and_preserves_base(pack, tmp_path):
    records, manifest, report = compile_expansion(pack, [], {"sources": []})
    assert (records, manifest, report) == compile_expansion(pack, [], {"sources": []})
    assert len(records) == 47
    assert report["index_built"] is False
    assert all(p["pdf_page"] is None for p in records)
    assert all(p["review_status"] == "candidate_not_expert_validated" for p in records)
    path = tmp_path / "passages.jsonl"
    path.write_text("".join(json.dumps(p) + "\n" for p in records), encoding="utf-8")
    manifest_path = tmp_path / "sources.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert load_passages(path) == records
    validate_source_references(records, manifest_path)
    # A changed section must not pass a manifest check merely because the URL matches.
    records[0]["source_section"] = "invented section"
    with pytest.raises(ValueError, match="unknown source section"):
        validate_source_references(records, manifest_path)


def test_pack_does_not_enable_immunisation_or_invent_pdf_pages(pack):
    records, _, _ = compile_expansion(pack, [], {"sources": []})
    assert not any(p["source_id"].startswith(("who-vaccine", "kenya-vaccine")) for p in records)
    assert len(pack["pending_sources"]) >= 2
    assert all(p["source_format"] == "web_summary" and p["pdf_page"] is None for p in records)


def test_activity_precautions_preserve_sources_and_feeding_age_limit():
    pack = json.loads((ROOT / "data/activity-safety-reference-expansion.json").read_text(encoding="utf-8"))
    records, _, _ = compile_expansion(pack, [], {"sources": []})
    assert len(records) == 5
    assert all(record["developmental_domain"] == "safety" for record in records)
    assert all(record["source_url"].startswith("https://") for record in records)
    assert all(record["pdf_page"] is None for record in records)
    feeding = next(record for record in records if record["routines"] == ["feeding"])
    assert feeding["source_age"]["min_months"] == 6


@pytest.mark.parametrize("mutation", ["duplicate", "http", "publisher", "age", "domain", "oversized"])
def test_invalid_candidate_metadata_is_rejected(pack, mutation):
    changed = deepcopy(pack)
    source = changed["sources"][0]
    if mutation == "duplicate":
        changed["sources"].append(deepcopy(source))
    elif mutation == "http":
        source["source_url"] = "http://example.test/reference"
    elif mutation == "publisher":
        source["publisher"] = ""
    elif mutation == "age":
        source["passages"][0]["age"] = [1, 5]
    elif mutation == "domain":
        source["passages"][0]["domain"] = "invented"
    else:
        source["passages"][0]["text"] = "x" * 1201
    with pytest.raises(ValueError):
        compile_expansion(changed, [], {"sources": []})


def test_question_inventory_is_a_draft_not_a_scored_evaluation():
    inventory = json.loads((ROOT / "data/evaluation/coverage-questions.json").read_text(encoding="utf-8"))
    assert inventory["status"] == "draft_questions_labels_and_split_pending"
    cases = inventory["cases"]
    assert len(cases) == len({case["id"] for case in cases}) == 64
    assert all("expected_passage_ids" not in case for case in cases)
    assert any(case.get("category") == "immunisation_pending" for case in cases)


@pytest.mark.parametrize("allow", [False, True])
def test_candidate_upload_cannot_replace_configured_collection(pack, tmp_path, monkeypatch, allow):
    from backend.core.config import settings

    records, manifest, _ = compile_expansion(pack, [], {"sources": []})
    path, manifest_path = tmp_path / "passages.jsonl", tmp_path / "sources.json"
    path.write_text("".join(json.dumps(p) + "\n" for p in records), encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    args = ["index_rag", "--upload", "--passages", str(path), "--manifest", str(manifest_path),
            "--collection", settings.QDRANT_COLLECTION]
    if allow:
        args.append("--allow-candidate-upload")
    monkeypatch.setattr("sys.argv", args)
    upload = MagicMock()
    monkeypatch.setattr("scripts.index_rag.upload_points", upload)
    with pytest.raises(SystemExit, match="separate staging collection"):
        index_main()
    upload.assert_not_called()
