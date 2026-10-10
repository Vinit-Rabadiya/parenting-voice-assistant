import hashlib
import json

import pytest
from pypdf import PdfWriter

from scripts.build_rag_passages import ROOT, build_passages, normalize, select_span
from scripts.prepare_rag_data import extract_sources


def write_json(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def test_extraction_keeps_empty_pages_and_flags_them(tmp_path):
    pdf_path = tmp_path / "blank.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(pdf_path)
    digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    manifest = tmp_path / "sources.json"
    write_json(manifest, {"schema_version": 1, "sources": [{
        "source_id": "blank", "filename": "blank.pdf", "expected_pages": 1, "sha256": digest,
    }]})
    output = tmp_path / "extracted"
    report = extract_sources(manifest, tmp_path, output)
    assert report["sources"][0]["low_text_pages"] == [1]
    page = json.loads((output / "blank/page-001.json").read_text(encoding="utf-8"))
    assert page["text"] == ""
    assert page["source_sha256"] == digest
    assert page["pdf_page"] == 1
    assert page["review_status"] == "unreviewed"


def test_changed_pdf_is_rejected_before_output(tmp_path):
    (tmp_path / "changed.pdf").write_bytes(b"changed source")
    manifest = tmp_path / "sources.json"
    write_json(manifest, {"schema_version": 1, "sources": [{
        "source_id": "changed", "filename": "changed.pdf", "expected_pages": 1, "sha256": "wrong",
    }]})
    output = tmp_path / "extracted"
    with pytest.raises(ValueError, match="source hash changed"):
        extract_sources(manifest, tmp_path, output)
    assert not output.exists()


@pytest.mark.parametrize("text,start,end", [
    ("Heading advice Heading other End", "Heading", "End"),
    ("End precedes Heading", "Heading", "End"),
    ("Heading advice", "Heading", "Missing"),
])
def test_ambiguous_or_missing_boundaries_fail(text, start, end):
    with pytest.raises(ValueError):
        select_span(text, start, end)


def test_selected_passage_excludes_neighbouring_age_content(tmp_path):
    source_id = "reach-up-parent-manual-2020"
    source = {
        "source_id": source_id, "sha256": "known-pdf", "title": "Test source",
        "publisher": "Test", "source_url": "https://example.org", "reuse_status": "test",
    }
    manifest = tmp_path / "sources.json"
    write_json(manifest, {"schema_version": 1, "sources": [source]})
    selections = tmp_path / "selections.json"
    write_json(selections, {"schema_version": 1, "reach_up": [{
        "page": 1, "age": [6, 9], "start": "Talk with baby", "end": "Next activity",
        "topic": "communication", "routines": ["feeding"],
    }]})
    source_dir = tmp_path / source_id
    source_dir.mkdir()
    selected_text = "Talk with baby • Name the food and respond when your baby makes sounds. "
    page = {
        "source_id": source_id, "source_sha256": "known-pdf", "pdf_page": 1,
        "pdf_page_label": "7", "text": "wrong reading order",
        "layout_text": "FOR CHILDREN AGES 6-8 MONTHS " + selected_text + "Next activity for older children",
    }
    write_json(source_dir / "page-001.json", page)
    records = build_passages(manifest, selections, tmp_path)
    assert len(records) == 1
    assert records[0]["text"] == selected_text.strip()
    assert records[0]["source_age"]["max_months_exclusive"] == 9
    assert records[0]["pdf_page_label"] == "7"
    page["source_sha256"] = "different-pdf"
    write_json(source_dir / "page-001.json", page)
    with pytest.raises(ValueError, match="provenance mismatch"):
        build_passages(manifest, selections, tmp_path)


def test_local_passages_are_reproducible_and_traceable():
    extracted = ROOT / "data/processed/extracted"
    if not (extracted / "extraction-report.json").exists():
        pytest.skip("local reference PDFs have not been extracted")
    args = (ROOT / "data/sources.json", ROOT / "data/passage-selections.json", extracted)
    records = build_passages(*args)
    assert records == build_passages(*args)
    for record in records:
        page = json.loads((extracted / record["source_id"] / f"page-{record['pdf_page']:03d}.json").read_text(encoding="utf-8"))
        first, last = record["normalized_page_span"]
        original = normalize(page[record["extraction_field"]])[first:last].strip()
        for correction in record["corrections"]:
            original = original.replace(correction["from"], correction["to"])
        assert original == record["text"]
    ccd = [r for r in records if r["source_id"] == "who-unicef-ccd-cards"]
    assert len(ccd) == 12
    assert ccd[0]["source_age"]["max_days_exclusive"] == 7
    assert ccd[2]["source_age"]["min_days"] == 7
    assert ccd[-1]["source_age"]["min_months"] == 24
    assert all(r["project_scope"]["max_months_inclusive"] == 24 for r in records)
