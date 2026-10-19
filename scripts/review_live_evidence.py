"""Read-only development examples for the current Qdrant corpus and evidence gate."""

import json

from backend.core.config import settings
from backend.services.evidence import select_evidence
from backend.services.retrieval import RetrievalService


def main() -> None:
    service = RetrievalService()
    examples = [
        ("covered", "How can I talk to my baby during bath time?", "bathing"),
        ("unrelated", "How do I repair a car engine?", None),
        ("coverage_review", "When will my baby sleep through the night?", None),
    ]
    try:
        for category, question, routine in examples:
            passages = service.retrieve(question, child_age_months=6.0, routine=routine, limit=3)
            evidence = select_evidence(passages, settings.RETRIEVAL_MIN_SCORE)
            print(json.dumps({
                "category": category, "question": question, "age_months": 6.0,
                "routine": routine, "threshold": settings.RETRIEVAL_MIN_SCORE,
                "gate_outcome": "accepted" if evidence else "no_evidence",
                "passages": [{"id": passage.passage_id, "title": passage.title,
                              "score": passage.score, "text": passage.text,
                              "passed_gate": passage in evidence} for passage in passages],
            }, ensure_ascii=True, indent=2), flush=True)
    finally:
        if service._client is not None:
            service._client.close()


if __name__ == "__main__":
    main()
