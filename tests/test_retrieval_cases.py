from copy import deepcopy
import json

import pytest

from scripts.prepare_retrieval_cases import ROOT, compile_cases


def inputs():
    inventory = {"evaluation_date": "2026-10-22", "cases": [
        {"id": "q1", "date_of_birth": "2026-04-22", "query": "Play ideas"}]}
    labels = {"status": "editorial_first_pass_not_expert_validated", "cases": [
        {"id": "q1", "outcome": "answer", "passages": ["p1"], "reason": "Relevant play"}]}
    passages = [{"passage_id": "p1", "source_age": {"min_months": 6, "max_months_exclusive": 9}},
                {"passage_id": "p2", "source_age": {"min_months": 12, "max_months_exclusive": 24}}]
    return inventory, labels, passages


def test_export_preserves_labels_and_lists_all_age_ineligible_ids():
    inventory, labels, passages = inputs()
    original = deepcopy(inventory)
    cases, workflow = compile_cases(inventory, labels, passages)
    assert workflow == []
    assert cases[0]["expected_passage_ids"] == ["p1"]
    assert cases[0]["forbidden_passage_ids"] == ["p2"]
    assert cases[0]["limit"] == 4
    assert inventory == original
    assert (cases, workflow) == compile_cases(inventory, labels, passages)


@pytest.mark.parametrize("mutation", ["missing_id", "unknown_passage", "wrong_age", "empty_answer"])
def test_invalid_relevance_labels_fail_before_retrieval(mutation):
    inventory, labels, passages = inputs()
    if mutation == "missing_id":
        labels["cases"][0]["id"] = "other"
    elif mutation == "unknown_passage":
        labels["cases"][0]["passages"] = ["unknown"]
    elif mutation == "wrong_age":
        labels["cases"][0]["passages"] = ["p2"]
    else:
        labels["cases"][0]["passages"] = []
    with pytest.raises(ValueError):
        compile_cases(inventory, labels, passages)


def test_health_cases_are_kept_out_of_ordinary_retrieval_scoring():
    inventory, labels, passages = inputs()
    labels["cases"][0]["outcome"] = "health_release_blocked"
    cases, workflow = compile_cases(inventory, labels, passages)
    assert cases == []
    assert workflow[0]["expected_outcome"] == "health_release_blocked"


def test_every_inventory_case_has_a_reasoned_first_pass_label():
    inventory = json.loads((ROOT / "data/evaluation/coverage-questions.json").read_text(encoding="utf-8"))
    labels = json.loads((ROOT / "data/evaluation/coverage-labels.json").read_text(encoding="utf-8"))
    assert {case["id"] for case in inventory["cases"]} == {case["id"] for case in labels["cases"]}
    assert all(case["reason"].strip() for case in labels["cases"])
    assert "not an exhaustive gold standard" in labels["label_policy"]
