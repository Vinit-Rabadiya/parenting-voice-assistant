import hashlib
import json

import pytest
from pypdf import PdfWriter

from scripts.build_rag_passages import ROOT, build_passages, normalize, select_span
from scripts.prepare_rag_data import extract_sources
from scripts.index_rag import build_point, load_passages, validate_age_metadata


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


@pytest.mark.parametrize("contents,message", [
    ("\n  \n", "contains no records"),
    ('\n{broken json}\n', "Invalid JSON on line 2"),
    ('[]\n', "must contain a JSON object"),
    ('{"text": "Talk to baby"}\n', "nonempty passage_id"),
    ('{"passage_id": "a", "text": " "}\n', "nonempty text"),
    ('{"passage_id": 12, "text": "Talk to baby"}\n', "nonempty passage_id"),
    ('{"passage_id": "a", "text": null}\n', "nonempty text"),
])
def test_index_loader_rejects_invalid_corpus(tmp_path, contents, message):
    path = tmp_path / "passages.jsonl"
    path.write_text(contents, encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        load_passages(path)


def test_index_preparation_preserves_metadata_and_stable_identity(tmp_path):
    passage = {
        "passage_id": "feeding-activity", "text": "Talk with baby • respond to sounds.",
        "routines": ["feeding"],
        "source_id": "reference", "pdf_page": 41,
        "source_title": "Reference activities", "source_url": "https://example.org/reference",
        "source_age": {"label": "6-8 months", "min_months": 6, "max_months_exclusive": 9},
        "project_scope": {"min_months": 0, "max_months_inclusive": 24},
    }
    path = tmp_path / "passages.jsonl"
    path.write_text("\n" + json.dumps(passage) + "\n\n", encoding="utf-8")
    loaded = load_passages(path)
    assert loaded == [passage]
    point = build_point(loaded[0])
    assert point.payload == passage
    assert point.vector.text == passage["text"]
    assert point.vector.model == "sentence-transformers/all-minilm-l6-v2"
    updated = {**passage, "text": "Updated guidance"}
    assert build_point(updated).id == point.id
    assert build_point({**passage, "passage_id": "other-activity"}).id != point.id


def test_index_loader_rejects_duplicate_ids_with_valid_metadata(tmp_path):
    passage = {
        "passage_id": "a", "text": "Talk to baby", "source_id": "reference",
        "source_title": "Reference activities", "source_url": "https://example.org/reference",
        "pdf_page": 1,
        "routines": [],
        "source_age": {"label": "6-8 months", "min_months": 6, "max_months_exclusive": 9},
        "project_scope": {"min_months": 0, "max_months_inclusive": 24},
    }
    path = tmp_path / "passages.jsonl"
    path.write_text(json.dumps(passage) + "\n" + json.dumps({**passage, "text": "Other advice"}), encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate passage ID on line 2"):
        load_passages(path)


@pytest.mark.parametrize("field,value", [
    ("source_id", None),
    ("source_title", "  "),
    ("source_url", 123),
    ("pdf_page", None),
    ("pdf_page", 0),
    ("pdf_page", -1),
    ("pdf_page", True),
    ("pdf_page", 1.5),
    ("pdf_page", "1"),
])
def test_index_loader_reports_invalid_source_field_and_line(tmp_path, field, value):
    passage = {
        "passage_id": "a", "text": "Talk to baby", "source_id": "reference",
        "source_title": "Reference activities", "source_url": "https://example.org/reference",
        "pdf_page": 1,
    }
    if value is None:
        passage.pop(field)
    else:
        passage[field] = value
    path = tmp_path / "passages.jsonl"
    path.write_text("\n" + json.dumps(passage), encoding="utf-8")
    with pytest.raises(ValueError, match=f"Line 2: {field}"):
        load_passages(path)


@pytest.mark.parametrize("age", [
    {"label": "birth to one week", "min_days": 0, "max_days_exclusive": 7},
    {"label": "one week to six months", "min_days": 7, "max_months_exclusive": 6},
    {"label": "6-8 months", "min_months": 6, "max_months_exclusive": 9},
    {"label": "24-26 months", "min_months": 24, "max_months_exclusive": 27},
    {"label": "two years and older", "min_months": 24, "max_months_exclusive": None},
])
def test_age_validation_preserves_source_ranges(age):
    # wider source ranges remain intact; retrieval will intersect them with project scope.
    passage = {
        "source_age": age,
        "project_scope": {"min_months": 0, "max_months_inclusive": 24},
    }
    original = json.loads(json.dumps(passage))
    validate_age_metadata(passage)
    assert passage == original


@pytest.mark.parametrize("age", [
    None,
    [],
    {"min_months": 6, "max_months_exclusive": 9},
    {"label": " ", "min_months": 6, "max_months_exclusive": 9},
    {"label": "age", "min_months": 6},
    {"label": "age", "min_weeks": 1, "max_weeks_exclusive": 4},
    {"label": "age", "min_months": -1, "max_months_exclusive": 9},
    {"label": "age", "min_months": True, "max_months_exclusive": 9},
    {"label": "age", "min_months": "6", "max_months_exclusive": 9},
    {"label": "age", "min_months": 6, "max_months_exclusive": 9.5},
    {"label": "age", "min_months": 6, "max_months_exclusive": 6},
    {"label": "age", "min_days": 7, "max_days_exclusive": 0},
    {"label": "age", "min_days": 8, "max_months_exclusive": 6},
    {"label": "age", "min_days": 7, "max_months_exclusive": None},
])
def test_index_loader_reports_invalid_age_with_line_number(tmp_path, age):
    passage = {
        "passage_id": "a", "text": "Talk to baby", "source_id": "reference",
        "source_title": "Reference", "source_url": "https://example.org", "pdf_page": 1,
        "source_age": age, "project_scope": {"min_months": 0, "max_months_inclusive": 24},
    }
    path = tmp_path / "passages.jsonl"
    path.write_text("\n" + json.dumps(passage), encoding="utf-8")
    with pytest.raises(ValueError, match="Line 2:"):
        load_passages(path)


@pytest.mark.parametrize("scope", [
    None,
    {},
    {"min_months": 0, "max_months_exclusive": 25},
    {"min_months": False, "max_months_inclusive": 24},
    {"min_months": 0, "max_months_inclusive": 24.0},
    {"min_months": 0, "max_months_inclusive": 25},
])
def test_age_validation_rejects_inconsistent_project_scope(scope):
    passage = {
        "source_age": {"label": "6-8 months", "min_months": 6, "max_months_exclusive": 9},
        "project_scope": scope,
    }
    with pytest.raises(ValueError, match="project_scope"):
        validate_age_metadata(passage)


@pytest.mark.parametrize("routines", [[], ["feeding"], ["feeding", "bathing"]])
def test_index_loader_preserves_valid_routines(tmp_path, routines):
    passage = {
        "passage_id": "a", "text": "Talk to baby", "source_id": "reference",
        "source_title": "Reference", "source_url": "https://example.org", "pdf_page": 1,
        "source_age": {"label": "6-8 months", "min_months": 6, "max_months_exclusive": 9},
        "project_scope": {"min_months": 0, "max_months_inclusive": 24},
        "routines": routines,
    }
    path = tmp_path / "passages.jsonl"
    path.write_text(json.dumps(passage), encoding="utf-8")
    assert load_passages(path) == [passage]


@pytest.mark.parametrize("routines,message", [
    (None, "routines must be a list"),
    ("feeding", "routines must be a list"),
    ([None], "Each routine must be nonempty text"),
    ([12], "Each routine must be nonempty text"),
    ([[]], "Each routine must be nonempty text"),
    (["  "], "Each routine must be nonempty text"),
    (["Feeding"], "Routine labels must be lowercase"),
    ([" feeding "], "Routine labels must be lowercase"),
    (["feeding", "feeding"], "Routine labels must not repeat"),
])
def test_index_loader_reports_invalid_routines_with_line_number(tmp_path, routines, message):
    passage = {
        "passage_id": "a", "text": "Talk to baby", "source_id": "reference",
        "source_title": "Reference", "source_url": "https://example.org", "pdf_page": 1,
        "source_age": {"label": "6-8 months", "min_months": 6, "max_months_exclusive": 9},
        "project_scope": {"min_months": 0, "max_months_inclusive": 24},
    }
    if routines is not None:
        passage["routines"] = routines
    path = tmp_path / "passages.jsonl"
    path.write_text("\n" + json.dumps(passage), encoding="utf-8")
    with pytest.raises(ValueError, match=f"Line 2: {message}"):
        load_passages(path)
