import json
import hashlib
from copy import deepcopy
from types import SimpleNamespace

import pytest

from scripts.build_reference_expansion import ROOT, compile_expansion


def health_pack():
    return json.loads((ROOT / "data/health-reference-expansion.json").read_text(encoding="utf-8"))


def test_health_passages_remain_review_blocked_and_country_labelled():
    records, _, report = compile_expansion(health_pack(), [], {"sources": []})
    assert len(records) == 18
    assert report["clinical_review_required"] is True
    assert all(p["clinical_review_required"] is True for p in records)
    assert all(p["release_status"] == "blocked_pending_health_review" for p in records)
    assert all(p["country"] in (None, "KE") for p in records)
    kenya = [p for p in records if p["country"] == "KE"]
    assert len(kenya) == 1
    assert "not a complete current schedule" in kenya[0]["text"]


def test_health_content_cannot_drop_its_review_gate():
    pack = health_pack()
    pack["clinical_review_required"] = False
    with pytest.raises(ValueError, match="clinical review gate"):
        compile_expansion(pack, [], {"sources": []})


def test_health_source_must_identify_country_scope():
    pack = deepcopy(health_pack())
    del pack["sources"][0]["country"]
    with pytest.raises(ValueError, match="explicit supported country"):
        compile_expansion(pack, [], {"sources": []})


@pytest.fixture
def pdf_pack(tmp_path, monkeypatch):
    raw = b"%PDF-controlled-test-bytes"
    (tmp_path / "reference.pdf").write_bytes(raw)
    page = SimpleNamespace(extract_text=lambda: "Selected section with source evidence.")
    monkeypatch.setattr("scripts.build_reference_expansion.PdfReader", lambda _: SimpleNamespace(pages=[page]))
    pack = health_pack()
    pack["sources"] = [{
        "source_id": "pdf-test", "source_format": "pdf_summary", "filename": "reference.pdf",
        "title": "Reference", "publisher": "NHS", "source_url": "https://www.nhs.uk/reference.pdf",
        "sha256": hashlib.sha256(raw).hexdigest(), "expected_pages": 1, "country": None, "age": [0, 25],
        "passages": [{"section": "Selected section", "pdf_page": 1, "source_anchor": "Selected section",
                      "domain": "common_concerns", "routines": [],
                      "text": "Contact a qualified professional when concerned about a baby's health."}],
    }]
    return pack, tmp_path


def test_pdf_candidate_retains_file_hash_page_and_section(pdf_pack):
    pack, directory = pdf_pack
    records, manifest, _ = compile_expansion(pack, [], {"sources": []}, pdf_dir=directory)
    assert records[0]["pdf_page"] == 1
    assert records[0]["source_sha256"] == pack["sources"][0]["sha256"]
    assert records[0]["normalized_page_sha256"]
    assert manifest["sources"][0]["fingerprint_basis"] == "original_pdf_bytes"


@pytest.mark.parametrize("change", ["hash", "page", "anchor", "filename"])
def test_pdf_candidate_rejects_changed_or_untraceable_evidence(pdf_pack, change):
    pack, directory = pdf_pack
    source = pack["sources"][0]
    if change == "hash":
        source["sha256"] = "0" * 64
    elif change == "page":
        source["passages"][0]["pdf_page"] = 2
    elif change == "anchor":
        source["passages"][0]["source_anchor"] = "Missing section"
    else:
        source["filename"] = "../reference.pdf"
    with pytest.raises(ValueError):
        compile_expansion(pack, [], {"sources": []}, pdf_dir=directory)


