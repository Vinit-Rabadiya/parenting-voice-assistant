"""Report arithmetic and CI thresholds, without external services."""

import json
from types import SimpleNamespace

import pytest

from scripts.evaluate_safety import evaluate, load_cases, meets_gate


def test_shared_dataset_has_thirty_cases_in_each_class():
    cases = load_cases()
    assert len(cases) == 60
    assert sum(c["should_escalate"] for c in cases) == 30
    assert len({c["id"] for c in cases}) == 60


def test_metrics_count_misses_and_false_alarms_separately():
    cases = [{"id": str(i), "question": str(i), "completed_months": 6,
              "should_escalate": i < 2} for i in range(4)]

    def inspector(question, months):
        return SimpleNamespace(escalate=question in ("0", "2"), reasons=())

    report = evaluate(cases, inspector)
    assert report["counts"] == {"true_positive": 1, "false_negative": 1,
                                "false_positive": 1, "true_negative": 1}
    assert report["recall"] == 0.5
    assert report["false_alarm_rate"] == 0.5
    assert not meets_gate(report)
    assert meets_gate({"recall": 1.0, "false_alarm_rate": 0.0})
    assert not meets_gate({"recall": 1.0, "false_alarm_rate": 0.1})


@pytest.mark.parametrize("change", ["duplicate", "label", "age", "class"])
def test_invalid_data_cannot_produce_a_passing_report(tmp_path, change):
    cases = load_cases()
    if change == "duplicate":
        cases[1] = cases[0]
    elif change == "label":
        cases[0]["should_escalate"] = "true"
    elif change == "age":
        cases[0]["completed_months"] = True
    else:
        cases = [case for case in cases if case["should_escalate"]]
    path = tmp_path / "cases.jsonl"
    path.write_text("\n".join(json.dumps(case) for case in cases), encoding="utf-8")
    with pytest.raises(ValueError):
        load_cases(path)
