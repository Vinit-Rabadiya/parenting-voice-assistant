# evaluates retrieval quality against the live qdrant index using labelled caregiver questions.
# run after indexing: python -m scripts.evaluate_retrieval
import json
import platform
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

from backend.core.config import PROJECT_ROOT, settings
from backend.services.age import age_details, within_project_scope
from backend.services.retrieval import RetrievalService


def query_age_context(query: dict) -> dict:
    """Derive reproducible retrieval ages from dates, never a supplied month value."""
    dates = {}
    for field in ("date_of_birth", "evaluation_date"):
        value = query.get(field)
        try:
            if not isinstance(value, str):
                raise ValueError
            parsed = date.fromisoformat(value)
            if parsed.isoformat() != value:
                raise ValueError
        except ValueError:
            raise ValueError(f"{field} must be a valid YYYY-MM-DD date.") from None
        dates[field] = parsed
    if not within_project_scope(dates["date_of_birth"], dates["evaluation_date"]):
        raise ValueError("Evaluation age must be from birth through the second birthday.")
    if any(field in query for field in ("child_age_months", "child_age_days", "completed_months")):
        raise ValueError("Supply birth and evaluation dates, not precomputed child ages.")
    days, completed_months, display_months = age_details(
        dates["date_of_birth"], dates["evaluation_date"],
    )
    return {
        "date_of_birth": dates["date_of_birth"].isoformat(),
        "evaluation_date": dates["evaluation_date"].isoformat(),
        "child_age_days": days,
        "completed_months": completed_months,
        "child_age_months": round(display_months, 1),
    }


def load_queries(path: Path) -> list[dict]:
    queries = []
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            try:
                query = json.loads(line)
                if not isinstance(query, dict):
                    raise ValueError("Each query must be an object.")
                query_age_context(query)
            except ValueError as exc:
                raise ValueError(f"Query line {line_number}: {exc}") from None
            queries.append(query)
    if not queries:
        raise ValueError("The query file contains no evaluation cases.")
    return queries


def evaluate_query(
    service: RetrievalService,
    query: dict,
) -> dict:
    """Run one query against the live index and measure results + timing."""
    age = query_age_context(query)
    start = time.perf_counter()
    results = service.retrieve(
        query=query["query"],
        child_age_months=age["completed_months"],
        child_age_days=age["child_age_days"],
        routine=query.get("routine"),
        limit=query["limit"],
    )
    elapsed_ms = (time.perf_counter() - start) * 1000

    retrieved_ids = [r.passage_id for r in results]
    expected_ids = query.get("expected_passage_ids", [])
    forbidden_ids = query.get("forbidden_passage_ids", [])

    # hit@k: did at least one expected passage appear in the top-k results?
    retrieved_set = set(retrieved_ids)
    expected_set = set(expected_ids)
    forbidden_set = set(forbidden_ids)

    hits = retrieved_set & expected_set
    leakages = retrieved_set & forbidden_set

    if expected_ids:
        hit_at_k = 1.0 if hits else 0.0
        recall_at_k = len(hits) / len(expected_ids)
    else:
        hit_at_k = None
        recall_at_k = None

    # age filtering is verified via forbidden_passage_ids checks above.

    return {
        "id": query["id"],
        "category": query["category"],
        "query": query["query"],
        **age,
        "routine": query.get("routine"),
        "limit": query["limit"],
        "notes": query.get("notes", ""),
        "expected_passage_ids": expected_ids,
        "forbidden_passage_ids": forbidden_ids,
        "retrieved": [
            {
                "passage_id": r.passage_id,
                "title": r.title,
                "score": round(r.score, 4),
                "source_age_label": r.source_age_label,
                "source_title": r.source_title,
                "routines": r.routines,
            }
            for r in results
        ],
        "retrieved_passage_ids": retrieved_ids,
        "hit_at_k": hit_at_k,
        "recall_at_k": round(recall_at_k, 4) if recall_at_k is not None else None,
        "age_leakage": sorted(leakages),
        "age_leakage_count": len(leakages),
        "latency_ms": round(elapsed_ms, 1),
    }


def build_report(queries: list[dict], results: list[dict]) -> dict:
    """Aggregate per-query results into a summary report."""
    # separate metrics by category.
    labelled = [r for r in results if r["hit_at_k"] is not None]
    boundary = [r for r in results if r["category"] == "age_boundary"]
    missing = [r for r in results if r["category"] == "missing_topic"]
    paraphrase = [r for r in results if r["category"] == "paraphrase"]

    latencies = [r["latency_ms"] for r in results]

    report = {
        "schema_version": 2,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "configuration": {
            "collection": settings.QDRANT_COLLECTION,
            "embedding_model": "sentence-transformers/all-minilm-l6-v2",
            "inference": "qdrant cloud",
            "corpus_path": str(PROJECT_ROOT / "data/processed/rag/passages.jsonl"),
            "query_count": len(queries),
            "age_policy": "Exact days and completed calendar months from fixed case dates",
        },
        "machine": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
        },
        "metrics": {
            "mean_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else 0,
            "min_latency_ms": min(latencies) if latencies else 0,
            "max_latency_ms": max(latencies) if latencies else 0,
            "hit_at_k_mean": (
                round(sum(r["hit_at_k"] for r in labelled) / len(labelled), 4)
                if labelled else None
            ),
            "recall_at_k_mean": (
                round(sum(r["recall_at_k"] for r in labelled) / len(labelled), 4)
                if labelled else None
            ),
            "age_leakage_total": sum(r["age_leakage_count"] for r in results),
            "age_boundary_queries": len(boundary),
            "age_boundary_passed": sum(1 for r in boundary if r["age_leakage_count"] == 0),
            "missing_topic_queries": len(missing),
            "missing_topic_returned_results": sum(1 for r in missing if r["retrieved_passage_ids"]),
            "paraphrase_queries": len(paraphrase),
            "paraphrase_hit_rate": (
                round(sum(r["hit_at_k"] for r in paraphrase) / len(paraphrase), 4)
                if paraphrase else None
            ),
        },
        "queries": results,
        "limitations": [
            "This report evaluates retrieval before the coaching evidence gate; returned "
            "passages do not necessarily become generated answers.",
            "Labels are editorial judgements based on passage content, not ECD expert validation.",
            "Labels come from the original development set and require review against the "
            "current corpus before calibration or held-out accuracy claims.",
            "Qdrant applies age filters before candidate selection, with Python validation "
            "as a safeguard. Leakage counts check listed forbidden IDs only, not every passage.",
            "Case birth dates are synthetic evaluation inputs, not caregiver records.",
        ],
    }
    return report


def main() -> None:
    queries_path = PROJECT_ROOT / "data/evaluation/retrieval-queries.jsonl"
    output_path = PROJECT_ROOT / "data/evaluation/retrieval-results.json"

    if not queries_path.exists():
        raise SystemExit(f"Queries file not found: {queries_path}")

    try:
        queries = load_queries(queries_path)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Invalid evaluation cases: {exc}") from None
    print(f"Loaded {len(queries)} evaluation queries from {queries_path.name}")

    # connect to the live qdrant index.
    service = RetrievalService()

    results = []
    for query in queries:
        result = evaluate_query(service, query)
        results.append(result)

        # print a compact per-query line for immediate feedback.
        status = "PASS" if result["age_leakage_count"] == 0 else "LEAK"
        if result["hit_at_k"] is not None:
            status += f" hit={result['hit_at_k']:.0f} recall={result['recall_at_k']:.2f}"
        elif result["category"] == "missing_topic" and result["retrieved_passage_ids"]:
            status += " false-positive"
        print(
            f"  {query['id']} [{query['category']:14s}] {status:20s} "
            f"{result['latency_ms']:6.1f}ms  "
            f"retrieved={len(result['retrieved_passage_ids'])}  "
            f"{query['query'][:55]}"
        )

    report = build_report(queries, results)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # print summary.
    m = report["metrics"]
    print()
    print("=" * 70)
    print("Retrieval Evaluation Summary")
    print(f"  Collection:      {report['configuration']['collection']}")
    print(f"  Model:           {report['configuration']['embedding_model']}")
    print(f"  Queries:         {report['configuration']['query_count']}")
    print(f"  Mean latency:    {m['mean_latency_ms']}ms")
    print(f"  Hit@k mean:      {m['hit_at_k_mean']}")
    print(f"  Recall@k mean:   {m['recall_at_k_mean']}")
    print(f"  Age leakage:     {m['age_leakage_total']} across {m['age_boundary_queries']} boundary queries")
    print(f"  Age boundary:    {m['age_boundary_passed']}/{m['age_boundary_queries']} passed")
    print(f"  Missing topics:  {m['missing_topic_returned_results']}/{m['missing_topic_queries']} returned false positives")
    print(f"  Paraphrase hit:  {m['paraphrase_hit_rate']}")
    print(f"  Results saved:   {output_path}")
    print("=" * 70)


if __name__ == "__main__":
    main()
