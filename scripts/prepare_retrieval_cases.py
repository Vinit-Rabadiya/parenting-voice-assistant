"""Validate editorial labels and preserve a reproducible split before retrieval."""
import argparse
import hashlib
import json
from pathlib import Path

from scripts.evaluate_retrieval import query_age_context
from scripts.index_rag import load_passages, validate_source_references
from backend.services.retrieval import is_age_eligible

ROOT = Path(__file__).resolve().parents[1]


def compile_cases(inventory, labels, passages):
    questions = {q["id"]: q for q in inventory["cases"]}
    reviewed = {q["id"]: q for q in labels["cases"]}
    if (len(questions) != len(inventory["cases"]) or len(reviewed) != len(labels["cases"])
            or questions.keys() != reviewed.keys()):
        raise ValueError("Question and label IDs must be unique and match exactly.")
    corpus = {p["passage_id"]: p for p in passages}
    # Hash order is independent of retrieval scores; no scores are read here.
    ordered = sorted(questions, key=lambda key: hashlib.sha256(f"coverage-v1:{key}".encode()).hexdigest())
    held_out = set(ordered[:round(len(ordered) * 0.3)])
    retrieval, workflow = [], []
    for key, question in questions.items():
        label = reviewed[key]
        expected = label["passages"]
        if len(expected) != len(set(expected)) or any(pid not in corpus for pid in expected):
            raise ValueError(f"{key}: duplicate or unknown passage label.")
        case = {**question, "evaluation_date": inventory["evaluation_date"],
                "split": "held_out" if key in held_out else "development",
                "expected_outcome": label["outcome"], "expected_passage_ids": expected,
                "notes": label["reason"], "label_status": labels["status"], "limit": 4,
                "category": question.get("category", "coverage")}
        if label["outcome"] not in {"answer", "no_evidence"}:
            workflow.append(case)
            continue
        age = query_age_context(case)
        forbidden = [pid for pid, p in corpus.items() if not is_age_eligible(
            p["source_age"], age["completed_months"], child_age_days=age["child_age_days"])]
        if set(expected) & set(forbidden):
            raise ValueError(f"{key}: a positive label is outside the child's age range.")
        if label["outcome"] == "answer" and not expected:
            raise ValueError(f"{key}: answerable cases need positive labels.")
        if label["outcome"] == "no_evidence" and expected:
            raise ValueError(f"{key}: no-evidence cases cannot have positive labels.")
        case["forbidden_passage_ids"] = forbidden
        retrieval.append(case)
    return retrieval, workflow


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-dir", type=Path, default=ROOT / "data/processed/activity-safety-candidates")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "eval/coverage-v1")
    args = parser.parse_args()
    inventory_path = ROOT / "data/evaluation/coverage-questions.json"
    labels_path = ROOT / "data/evaluation/coverage-labels.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    corpus_path = args.corpus_dir / "passages.jsonl"
    digest = hashlib.sha256(corpus_path.read_bytes()).hexdigest()
    if digest != labels["corpus_sha256"]:
        parser.error("Corpus changed; review the labels before creating another split.")
    passages = load_passages(corpus_path)
    validate_source_references(passages, args.corpus_dir / "sources.json")
    cases, workflow = compile_cases(inventory, labels, passages)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    outputs = [args.output_dir / name for name in ("questions.jsonl", "workflow-cases.json", "manifest.json")]
    if any(path.exists() for path in outputs):
        parser.error("Output exists; preserve the previous split and choose a new output directory.")
    for case in cases:
        case["corpus_sha256"] = digest
    outputs[0].write_text("".join(json.dumps(case) + "\n" for case in cases), encoding="utf-8")
    outputs[1].write_text(json.dumps(workflow, indent=2) + "\n", encoding="utf-8")
    outputs[2].write_text(json.dumps({
        "corpus_sha256": digest, "labels_sha256": hashlib.sha256(labels_path.read_bytes()).hexdigest(),
        "questions_sha256": hashlib.sha256(inventory_path.read_bytes()).hexdigest(),
        "split_policy": "SHA256 coverage-v1:ID order; 30 percent rounded to nearest whole case",
        "retrieval_cases": len(cases), "workflow_cases": len(workflow),
        "label_status": labels["status"],
        "limitation": "Initial editorial positive pool, not exhaustive clinical or independent gold-standard validation.",
    }, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared {len(cases)} retrieval cases and {len(workflow)} separate workflow cases.")
    print("No retrieval performed. Keep held-out results out of tuning.")


if __name__ == "__main__":
    main()
