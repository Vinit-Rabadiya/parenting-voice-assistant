"""Evaluate selected English, unsupported and mixed-language development inputs."""

import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path

from backend.services.language_safety import supports_english


DATASET = Path(__file__).resolve().parents[1] / "eval/language-safety.jsonl"


def load_cases(path=DATASET):
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    seen = set()
    for case in cases:
        if (not isinstance(case, dict) or set(case) != {"id", "question", "should_allow"}
                or not isinstance(case["id"], str) or not case["id"].strip()
                or not isinstance(case["question"], str) or not case["question"].strip()
                or type(case["should_allow"]) is not bool or case["id"] in seen):
            raise ValueError("Invalid or duplicate language-safety case.")
        seen.add(case["id"])
    if {case["should_allow"] for case in cases} != {True, False}:
        raise ValueError("Language evaluation requires English and unsupported cases.")
    return cases


def evaluate(cases, inspector=supports_english):
    canonical = json.dumps(cases, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    results = [{"id": case["id"], "expected_allow": case["should_allow"],
                "actual_allow": inspector(case["question"])} for case in cases]
    return {
        "schema_version": 1,
        "dataset_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
        "detector": f"lingua-language-detector=={version('lingua-language-detector')}",
        "case_count": len(results),
        "unsupported_allowed": sum(not row["expected_allow"] and row["actual_allow"] for row in results),
        "english_refused": sum(row["expected_allow"] and not row["actual_allow"] for row in results),
        "cases": results,
        "scope": "Project-authored development examples; not comprehensive language or clinical validation.",
    }


def meets_gate(report):
    return report["case_count"] > 0 and report["unsupported_allowed"] == 0 and report["english_refused"] == 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, help="New report file; existing files are not overwritten.")
    args = parser.parse_args()
    report = evaluate(load_cases())
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
