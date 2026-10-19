"""Inspect an existing retrieval-results file offline; no cloud calls or file writes."""

import argparse
import json
from pathlib import Path


def summarize(report: dict, threshold: float) -> dict:
    if not 0 <= threshold <= 1:
        raise ValueError("Threshold must be between 0 and 1.")
    rows = []
    for query in report["queries"]:
        # Missing-topic labels explicitly mean no evidence; empty labels alone are not enough.
        if query["category"] == "missing_topic":
            should_answer = False
        elif query.get("expected_passage_ids"):
            should_answer = True
        else:
            continue
        best = max((item["score"] for item in query["retrieved"]), default=None)
        accepted = best is not None and best >= threshold
        rows.append({"id": query["id"], "should_answer": should_answer,
                     "best_score": best, "accepted": accepted})
    return {
        "threshold": threshold,
        "accepted_supported": sum(row["accepted"] and row["should_answer"] for row in rows),
        "rejected_supported": sum(not row["accepted"] and row["should_answer"] for row in rows),
        "accepted_unsupported": sum(row["accepted"] and not row["should_answer"] for row in rows),
        "rejected_unsupported": sum(not row["accepted"] and not row["should_answer"] for row in rows),
        "queries": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=Path(__file__).resolve().parents[1] / "data/evaluation/retrieval-results.json")
    parser.add_argument("--threshold", type=float, default=0.50)
    args = parser.parse_args()
    report = json.loads(args.results.read_text(encoding="utf-8"))
    print(json.dumps(summarize(report, args.threshold), indent=2))
    print("Development evidence only: this does not judge the actual relevance of accepted passages.")
    print("Recorded scores may be rounded or stale. Re-evaluate the current corpus before release.")


if __name__ == "__main__":
    main()
