"""Optional evaluation-only cross-encoder; preserve original evidence-gate scores."""
from math import isfinite
import time

DEFAULT_MODEL = "cross-encoder/ms-marco-TinyBERT-L2-v2"


class RerankedRetrieval:
    def __init__(self, retrieval, model=None):
        self.retrieval = retrieval
        self.model = model
        self.last_timings = {}
        self.initialization_seconds = 0.0
        self.model_revision = None

    def initialize(self):
        if self.model is not None:
            return
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise RuntimeError(
                "Optional reranking dependency missing. Install requirements-evaluation.txt first."
            ) from exc
        started = time.perf_counter()
        # CPU is explicit so comparisons do not silently depend on GPU availability.
        self.model = CrossEncoder(DEFAULT_MODEL, device="cpu", max_length=512)
        self.initialization_seconds = time.perf_counter() - started
        self.model_revision = getattr(self.model.model.config, "_commit_hash", None)

    def retrieve(self, query, child_age_months=None, routine=None, limit=4, *, child_age_days=None):
        self.initialize()
        pool_size = max(limit * 5, 15)
        started = time.perf_counter()
        # Keep the same raw search budget as the baseline top-four evaluation.
        # Calling retrieve(limit=20) without this override would search 100 candidates.
        candidates = self.retrieval.retrieve(
            query=query, child_age_months=child_age_months, routine=routine,
            limit=pool_size, child_age_days=child_age_days, candidate_limit=pool_size,
        )
        retrieved_at = time.perf_counter()
        if not candidates:
            self.last_timings = {"retrieval_ms": round((retrieved_at - started) * 1000, 1),
                                 "rerank_ms": 0.0, "candidate_count": 0, "ranking": []}
            return []
        values = self.model.predict([(query, p.text) for p in candidates],
                                    batch_size=16, show_progress_bar=False)
        scores = [float(value) for value in values]
        if len(scores) != len(candidates) or not all(isfinite(score) for score in scores):
            raise ValueError("Reranker returned an invalid score count or nonfinite score.")
        ranked = sorted(zip(candidates, scores), key=lambda pair: pair[1], reverse=True)
        self.last_timings = {
            "retrieval_ms": round((retrieved_at - started) * 1000, 1),
            "rerank_ms": round((time.perf_counter() - retrieved_at) * 1000, 1),
            "candidate_count": len(candidates),
            "ranking": [{"passage_id": p.passage_id, "reranker_score": score,
                         "original_similarity": p.score} for p, score in ranked],
        }
        # Reorder objects only. Never replace p.score with a cross-encoder logit.
        return [p for p, _ in ranked[:limit]]
