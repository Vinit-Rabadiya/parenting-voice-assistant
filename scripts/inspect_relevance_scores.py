"""Inspect an existing retrieval-results file offline; no cloud calls or file writes."""

import argparse
import json
from math import isfinite
from pathlib import Path


def summarize(report: dict, threshold: float) -> dict:
    if isinstance(threshold, bool) or not isfinite(threshold) or not 0 <= threshold <= 1:
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


def compare_thresholds(report: dict, thresholds: list[float]) -> dict:
    """Compare recorded development rankings without treating any match as relevant."""
    if report.get("configuration", {}).get("split") != "development":
        raise ValueError("Threshold comparison requires an explicitly development-only report.")
    if not thresholds or len(set(thresholds)) != len(thresholds):
        raise ValueError("Provide distinct threshold candidates.")
    comparisons = []
    for threshold in thresholds:
        if isinstance(threshold, bool) or not isfinite(threshold) or not 0 <= threshold <= 1:
            raise ValueError("Threshold must be finite and between 0 and 1.")
        counts = {key: 0 for key in (
            "supported_with_labelled_evidence", "supported_rejected", "supported_without_labelled_evidence",
            "unsupported_accepted", "unsupported_rejected",
        )}
        rows = []
        for query in report["queries"]:
            expected = set(query.get("expected_passage_ids", []))
            outcome = query.get("expected_outcome")
            if outcome == "no_evidence" or query.get("category") == "missing_topic":
                if expected:
                    raise ValueError("No-evidence cases cannot contain positive passage labels.")
                supported = False
            elif expected and outcome in (None, "answer"):
                supported = True
            else:
                continue
            accepted = []
            for item in query["retrieved"]:
                score = item["score"]
                if isinstance(score, bool) or not isinstance(score, (int, float)) or not isfinite(score):
                    raise ValueError("Recorded scores must be finite numbers.")
                if score >= threshold:
                    accepted.append(item["passage_id"])
            hits = sorted(expected.intersection(accepted))
            key = ("supported_with_labelled_evidence" if hits else
                   "supported_without_labelled_evidence" if accepted else "supported_rejected") if supported else (
                   "unsupported_accepted" if accepted else "unsupported_rejected")
            counts[key] += 1
            rows.append({"id": query["id"], "outcome": key,
                         "accepted_passage_ids": accepted, "labelled_evidence_ids": hits})
        comparisons.append({"threshold": threshold, **counts, "queries": rows})
    return {"configuration": report["configuration"], "comparisons": comparisons,
            "interpretation": "Recorded development scores may be rounded. Positive labels are an incomplete editorial pool; unlabelled evidence is not automatically irrelevant. No threshold is selected and application settings are unchanged."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=Path(__file__).resolve().parents[1] / "data/evaluation/retrieval-results.json")
    parser.add_argument("--threshold", type=float, default=0.50)
    parser.add_argument("--compare", type=float, nargs="+", help="Compare cutoffs using a development-only report.")
    args = parser.parse_args()
    report = json.loads(args.results.read_text(encoding="utf-8"))
    try:
        result = compare_thresholds(report, args.compare) if args.compare else summarize(report, args.threshold)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))
    print("Development evidence only: this does not judge the actual relevance of accepted passages.")
    print("Recorded scores may be rounded or stale. Re-evaluate the current corpus before release.")


if __name__ == "__main__":
    main()
