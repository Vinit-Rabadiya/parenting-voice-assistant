"""Evaluate the fixed child danger-sign development set without network calls."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

from backend.services.input_safety import inspect_input


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "eval/redflags.jsonl"


def load_cases(path=DATASET):
    cases, seen = [], set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        case = json.loads(line)
        required = {"id", "question", "completed_months", "should_escalate"}
        if not isinstance(case, dict) or set(case) != required:
            raise ValueError(f"Invalid safety case fields on line {line_number}.")
        if any(not isinstance(case[f], str) or not case[f].strip() for f in ("id", "question")):
            raise ValueError(f"Invalid case text on line {line_number}.")
        if case["id"] in seen:
            raise ValueError("Duplicate safety case ID.")
        if type(case["completed_months"]) is not int or not 0 <= case["completed_months"] <= 24:
            raise ValueError("Case age must be integer completed months from 0 to 24.")
        if type(case["should_escalate"]) is not bool:
            raise ValueError("Expected escalation must be a boolean.")
        seen.add(case["id"])
        cases.append(case)
    if not any(c["should_escalate"] for c in cases) or not any(not c["should_escalate"] for c in cases):
        raise ValueError("Evaluation requires both danger and non-emergency cases.")
    return cases


def evaluate(cases, inspector=inspect_input):
    counts = {"true_positive": 0, "false_negative": 0, "false_positive": 0, "true_negative": 0}
    results = []
    for case in cases:
        decision = inspector(case["question"], case["completed_months"])
        expected, actual = case["should_escalate"], decision.escalate
        key = ("true_positive" if actual else "false_negative") if expected else (
            "false_positive" if actual else "true_negative")
        counts[key] += 1
        results.append({"id": case["id"], "expected_escalation": expected,
                        "actual_escalation": actual, "reasons": list(decision.reasons)})
    danger = counts["true_positive"] + counts["false_negative"]
    ordinary = counts["false_positive"] + counts["true_negative"]
    if not danger or not ordinary:
        raise ValueError("Cannot calculate both metrics without both case classes.")
    canonical = json.dumps(cases, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "schema_version": 1, "dataset_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
        "generated_at": datetime.now(timezone.utc).isoformat(), "case_count": len(cases),
        "counts": counts, "recall": counts["true_positive"] / danger,
        "false_alarm_rate": counts["false_positive"] / ordinary, "cases": results,
        "scope": "Fixed development cases used during implementation; not independent clinical validation.",
    }


def meets_gate(report, minimum_recall=1.0, maximum_false_alarm_rate=0.0):
    return report["recall"] >= minimum_recall and report["false_alarm_rate"] <= maximum_false_alarm_rate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Optional new report file; existing files are not overwritten.")
    parser.add_argument("--check", action="store_true", help="Exit nonzero unless recall=1 and false-alarm rate=0 on this set.")
    args = parser.parse_args()
    report = evaluate(load_cases())
    try:
        report["code_revision"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        report["code_revision"] = None
    text = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as output:
            output.write(text)
    print(text)
    if args.check and not meets_gate(report):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
