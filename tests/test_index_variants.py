from copy import deepcopy
import json
from pathlib import Path

import pytest

from scripts.index_rag import build_point


def passage():
    return {"passage_id": "p1", "source_id": "source", "title": "Chat with baby",
            "text": "Talk during changing, feeding and bath time.",
            "developmental_domain": "language", "routines": ["changing", "feeding", "bathing"]}


def correction():
    return {"passage_id": "p1", "source_id": "source",
            "routines": ["changing", "feeding", "bathing", "dressing"],
            "reason": "Clothing-change conversation reviewed in source."}


def test_default_point_preserves_original_embedding_and_payload():
    source = passage()
    point = build_point(source)
    assert point.payload == source
    assert point.vector.text == source["text"]


def test_context_changes_search_vector_input_not_source_text_or_id():
    source = passage()
    original = deepcopy(source)
    point = build_point(source, embedding_context=True, routine_correction=correction())
    assert point.id == build_point(source).id
    assert point.payload["text"] == source["text"]
    assert "Chat with baby" in point.vector.text
    assert "dressing" in point.vector.text
    assert "dressing" in point.payload["routines"]
    assert source == original


def test_reviewed_routine_does_not_rewrite_ambiguous_changing_globally():
    source = passage()
    point = build_point(source, routine_correction=correction())
    assert "changing" in point.payload["routines"]
    assert "dressing" in point.payload["routines"]
    assert point.vector.text == source["text"]
    assert "dressing" not in build_point(source).payload["routines"]


def test_correction_cannot_be_applied_to_another_source():
    reviewed = correction()
    reviewed["source_id"] = "unrelated-source"
    with pytest.raises(ValueError, match="source does not match"):
        build_point(passage(), routine_correction=reviewed)


def test_canonical_chat_selection_preserves_reviewed_routine_correction():
    root = Path(__file__).resolve().parents[1]
    selections = json.loads((root / "data/passage-selections.json").read_text(encoding="utf-8"))
    # The selection file groups source documents; inspect its leaf selections.
    def matching_rows(value):
        if isinstance(value, dict):
            if value.get("page") == 37 and value.get("start") == "Chat with baby":
                yield value
            for child in value.values():
                yield from matching_rows(child)
        elif isinstance(value, list):
            for child in value:
                yield from matching_rows(child)
    rows = list(matching_rows(selections))
    assert len(rows) == 1
    assert set(rows[0]["routines"]) == {"feeding", "bathing", "changing", "dressing"}
