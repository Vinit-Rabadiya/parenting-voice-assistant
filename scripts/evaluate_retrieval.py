# evaluates retrieval quality against the live qdrant index using labelled caregiver questions.
# run after indexing: python -m scripts.evaluate_retrieval
import argparse
import hashlib
import json
import platform
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

from backend.core.config import PROJECT_ROOT, settings
from backend.services.age import age_details, within_project_scope
from backend.services.evidence import select_evidence
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
    evidence = select_evidence(results, settings.RETRIEVAL_MIN_SCORE)
    reranking = getattr(service, "last_timings", None)

    retrieved_ids = [r.passage_id for r in results]
    expected_ids = query.get("expected_passage_ids", [])
    forbidden_ids = query.get("forbidden_passage_ids", [])

    # hit@k: did at least one expected passage appear in the top-k results?
    retrieved_set = set(retrieved_ids)
    expected_set = set(expected_ids)
    forbidden_set = set(forbidden_ids)

    hits = retrieved_set & expected_set
    leakages = retrieved_set & forbidden_set
    reciprocal_rank = next((1 / rank for rank, pid in enumerate(retrieved_ids, 1)
                            if pid in expected_set), 0.0) if expected_ids else None

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
        "expected_outcome": query.get("expected_outcome"),
        "reranking": reranking if isinstance(reranking, dict) else None,
        "evidence_gate": {
            "minimum_score": settings.RETRIEVAL_MIN_SCORE,
            "accepted_passage_ids": [p.passage_id for p in evidence],
            "has_evidence": bool(evidence),
            "expected_rejection_met": (not evidence if query.get("expected_outcome") == "no_evidence" else None),
        },
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
        "reciprocal_rank": reciprocal_rank,
        "age_leakage": sorted(leakages),
        "age_leakage_count": len(leakages),
        "latency_ms": round(elapsed_ms, 1),
    }


def build_report(queries: list[dict], results: list[dict]) -> dict:
    """Aggregate per-query results into a summary report."""
    # separate metrics by category.
    labelled = [r for r in results if r["hit_at_k"] is not None]
    boundary = [r for r in results if r["category"] == "age_boundary"]
    missing = [r for r in results if r.get("expected_outcome") == "no_evidence"
               or r["category"] == "missing_topic"]
    gate_cases = [r for r in results if r.get("expected_outcome") == "no_evidence"]
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
            "mrr": (round(sum(r["reciprocal_rank"] for r in labelled) / len(labelled), 4)
                    if labelled else None),
            "age_boundary_queries": len(boundary),
            "age_boundary_passed": sum(1 for r in boundary if r["age_leakage_count"] == 0),
            "missing_topic_queries": len(missing),
            "missing_topic_returned_results": sum(1 for r in missing if r["retrieved_passage_ids"]),
            "expected_no_evidence_cases": len(gate_cases),
            "expected_no_evidence_rejected": sum(not r["evidence_gate"]["has_evidence"] for r in gate_cases),
            "expected_no_evidence_accepted": sum(r["evidence_gate"]["has_evidence"] for r in gate_cases),
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


def result_status(result: dict) -> str:
    """Describe each independent check without implying overall correctness."""
    parts = ["AGE_OK" if result["age_leakage_count"] == 0 else "AGE_LEAK"]
    if result["hit_at_k"] is not None:
        parts.append("HIT" if result["hit_at_k"] else "MISS")
        parts.append(f"recall={result['recall_at_k']:.2f}")
    if result.get("expected_outcome") == "no_evidence":
        parts.append("GATE_ACCEPTED_UNSUPPORTED" if result["evidence_gate"]["has_evidence"] else "GATE_REJECTED")
    return " ".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queries", type=Path, default=PROJECT_ROOT / "data/evaluation/retrieval-queries.jsonl")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "data/evaluation/retrieval-results.json")
    parser.add_argument("--collection", default=settings.QDRANT_COLLECTION)
    parser.add_argument("--corpus", type=Path, default=PROJECT_ROOT / "data/processed/rag/passages.jsonl")
    parser.add_argument("--split", choices=("development", "held_out"))
    parser.add_argument("--rerank", action="store_true", help="Compare an optional local CPU cross-encoder.")
    parser.add_argument("--allow-candidate-content", action="store_true",
                        help="Inspect unapproved references in a separate evaluation collection only.")
    args = parser.parse_args()
    if args.allow_candidate_content and args.collection == settings.QDRANT_COLLECTION:
        parser.error("Candidate content requires a separate evaluation collection.")
    queries_path, output_path = args.queries, args.output

    if not queries_path.exists():
        raise SystemExit(f"Queries file not found: {queries_path}")

    try:
        queries = load_queries(queries_path)
        if args.split:
            queries = [case for case in queries if case.get("split") == args.split]
            if not queries:
                raise ValueError("No cases match the selected split.")
        elif any("split" in case for case in queries):
            raise ValueError("Select --split explicitly for a split evaluation set.")
        if any("corpus_sha256" in case for case in queries):
            digest = hashlib.sha256(args.corpus.read_bytes()).hexdigest()
            if any(case.get("corpus_sha256") != digest for case in queries):
                raise ValueError("Corpus fingerprint differs from the labelled corpus.")
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Invalid evaluation cases: {exc}") from None
    print(f"Loaded {len(queries)} evaluation queries from {queries_path.name}")

    # connect to the live qdrant index.
    service = RetrievalService(collection_name=args.collection, allow_candidate_content=args.allow_candidate_content,
                               cache_ttl_seconds=0)
    if args.rerank:
        if args.split != "development":
            parser.error("The experimental reranker is restricted to the development split.")
        from scripts.rerank_retrieval import RerankedRetrieval
        service = RerankedRetrieval(service)
        try:
            service.initialize()
        except (RuntimeError, OSError) as exc:
            raise SystemExit(f"Reranker initialization failed: {exc}") from exc

    results = []
    for query in queries:
        result = evaluate_query(service, query)
        results.append(result)

        # print a compact per-query line for immediate feedback.
        status = result_status(result)
        print(
            f"  {query['id']} [{query['category']:14s}] {status:20s} "
            f"{result['latency_ms']:6.1f}ms  "
            f"retrieved={len(result['retrieved_passage_ids'])}  "
            f"{query['query'][:55]}"
        )

    report = build_report(queries, results)
    report["configuration"].update(collection=args.collection, corpus_path=str(args.corpus), split=args.split)
    report["configuration"]["evidence_minimum_score"] = settings.RETRIEVAL_MIN_SCORE
    report["configuration"]["candidate_content_allowed"] = args.allow_candidate_content
    if args.rerank:
        from scripts.rerank_retrieval import DEFAULT_MODEL
        report["configuration"].update(reranker=DEFAULT_MODEL, reranker_device="cpu",
                                       reranker_revision=service.model_revision,
                                       initialization_seconds=round(service.initialization_seconds, 3))
        report["metrics"]["mean_rerank_ms"] = round(
            sum(r["reranking"]["rerank_ms"] for r in results) / len(results), 1)
    if any("label_status" in case for case in queries):
        report["limitations"] = [
            "Metrics use a first-pass editorial positive pool, not exhaustive relevance labels or clinical approval.",
            "Retrieval metrics precede the evidence gate; separate gate checks measure score-based rejection, not semantic correctness or answer safety.",
            "Gate checks use four retrieved passages for this evaluation; live coaching may use a different retrieval limit.",
            "All locally known age-ineligible IDs are checked; unknown IDs still require investigation.",
            "Held-out results must not guide content selection or threshold tuning.",
        ]
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
    if args.rerank:
        print(f"  Rerank portion:  {m['mean_rerank_ms']}ms (mean; model initialization recorded separately)")
    print(f"  Hit@k mean:      {m['hit_at_k_mean']}")
    print(f"  Recall@k mean:   {m['recall_at_k_mean']}")
    print(f"  MRR:             {m['mrr']}")
    print(f"  Age leakage:     {m['age_leakage_total']} across {m['age_boundary_queries']} boundary queries")
    print(f"  Age boundary:    {m['age_boundary_passed']}/{m['age_boundary_queries']} passed")
    if m["missing_topic_queries"]:
        print(f"  Unsupported:     {m['missing_topic_returned_results']}/{m['missing_topic_queries']} returned raw candidates (before gate)")
    else:
        print("  Unsupported:     not evaluated (no labelled cases)")
    if m["expected_no_evidence_cases"]:
        print(f"  Gate rejection:  {m['expected_no_evidence_rejected']}/{m['expected_no_evidence_cases']} expected no-evidence cases")
    print(f"  Paraphrase hit:  {m['paraphrase_hit_rate']}")
    print(f"  Results saved:   {output_path}")
    print("=" * 70)


if __name__ == "__main__":
    main()
