"""Select reference support; similarity does not determine whether to answer."""

from math import isfinite

from backend.services.retrieval import RetrievedPassage


def select_evidence(passages: list[RetrievedPassage], minimum_score: float) -> list[RetrievedPassage]:
    """Keep only nonempty passages meeting the cutoff; do not assume score ordering."""
    if not isfinite(minimum_score) or not 0 <= minimum_score <= 1:
        raise ValueError("RETRIEVAL_MIN_SCORE must be a finite number between 0 and 1.")
    return [
        passage for passage in passages
        if passage.text.strip() and isfinite(passage.score) and passage.score >= minimum_score
    ]
