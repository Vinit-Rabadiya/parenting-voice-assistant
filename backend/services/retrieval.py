from dataclasses import dataclass
import logging
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import Document

from backend.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class RetrievedPassage:
    passage_id: str
    text: str
    title: str
    source_title: str
    pdf_page: int
    source_url: str
    score: float
    source_age_label: str
    routines: list[str]


def is_age_eligible(source_age: dict[str, Any], child_age_months: float) -> bool:
    if not isinstance(source_age, dict):
        return False

    approx_child_days = child_age_months * 30.4375

    # check day-based bounds for the newborn first week.
    if "min_days" in source_age and "max_days_exclusive" in source_age:
        min_days = source_age.get("min_days", 0)
        max_days = source_age.get("max_days_exclusive", 7)
        return min_days <= approx_child_days < max_days

    # check mixed-unit range for one week to six months.
    if "min_days" in source_age and "max_months_exclusive" in source_age:
        min_days = source_age.get("min_days", 7)
        max_months = source_age.get("max_months_exclusive", 6)
        return approx_child_days >= min_days and child_age_months < max_months

    # check month boundaries for standard age groups.
    if "min_months" in source_age:
        min_months = source_age.get("min_months", 0)
        max_months = source_age.get("max_months_exclusive")
        if max_months is None:
            return child_age_months >= min_months
        return min_months <= child_age_months < max_months

    return True


class RetrievalService:
    def __init__(
        self,
        url: str | None = None,
        api_key: str | None = None,
        collection_name: str | None = None,
        client: QdrantClient | None = None,
    ):
        self.url = (url or settings.QDRANT_URL or "").strip()
        self.api_key = (api_key or settings.QDRANT_API_KEY or "").strip()
        self.collection_name = collection_name or settings.QDRANT_COLLECTION
        self._client = client

    @property
    def client(self) -> QdrantClient:
        if self._client is None:
            if not self.url or not self.api_key:
                raise ValueError("QDRANT_URL and QDRANT_API_KEY must be configured in settings.")
            self._client = QdrantClient(
                url=self.url,
                # Use standard HTTPS for Cloud endpoints on networks blocking port 6333.
                port=443,
                api_key=self.api_key,
                cloud_inference=True,
                timeout=15,
            )
        return self._client

    def retrieve(
        self,
        query: str,
        child_age_months: float | None = None,
        routine: str | None = None,
        limit: int = 3,
    ) -> list[RetrievedPassage]:
        if not query.strip():
            return []

        # fetch enough candidates to allow age and routine filtering.
        candidate_limit = max(limit * 5, 15)

        try:
            results = self.client.query_points(
                collection_name=self.collection_name,
                query=Document(
                    text=query.strip(),
                    model="sentence-transformers/all-minilm-l6-v2",
                ),
                limit=candidate_limit,
            )
        except Exception as exc:
            logger.error("error querying qdrant: %s", exc)
            raise

        filtered: list[RetrievedPassage] = []
        normalized_routine = routine.strip().lower() if routine else None

        for point in results.points:
            payload = point.payload or {}
            source_age = payload.get("source_age", {})

            # exclude passages outside the child's developmental age.
            if child_age_months is not None and not is_age_eligible(source_age, child_age_months):
                continue

            # exclude passages when a specific routine is requested and tags do not match.
            point_routines = [r.lower() for r in payload.get("routines", [])]
            if normalized_routine and point_routines and normalized_routine not in point_routines:
                continue

            filtered.append(
                RetrievedPassage(
                    passage_id=payload.get("passage_id", str(point.id)),
                    text=payload.get("text", ""),
                    title=payload.get("title", ""),
                    source_title=payload.get("source_title", "Parenting Reference"),
                    pdf_page=payload.get("pdf_page", 1),
                    source_url=payload.get("source_url", ""),
                    score=float(point.score or 0.0),
                    source_age_label=source_age.get("label", "0-24 months"),
                    routines=point_routines,
                )
            )

            if len(filtered) >= limit:
                break

        return filtered
