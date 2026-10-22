from dataclasses import dataclass
import logging
from math import isfinite
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Document, FieldCondition, Filter, IsNullCondition, PayloadField, Range,
)

from backend.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class RetrievedPassage:
    passage_id: str
    text: str
    title: str
    source_title: str
    pdf_page: int | None
    source_url: str
    score: float
    source_age_label: str
    routines: list[str]


def is_age_eligible(source_age: dict[str, Any], child_age_months: float, *, child_age_days: int | None = None) -> bool:
    if not isinstance(source_age, dict):
        return False

    if (type(child_age_months) not in (int, float)
            or not isfinite(child_age_months) or child_age_months < 0):
        return False

    # Match the explicit formats accepted during indexing. Missing upper keys are
    # invalid; only an explicitly null upper bound represents an open-ended band.
    boundaries = set(source_age) - {"label"}
    supported = (
        {"min_days", "max_days_exclusive"},
        {"min_days", "max_months_exclusive"},
        {"min_months", "max_months_exclusive"},
    )
    if boundaries not in supported:
        return False
    for field in boundaries:
        value = source_age[field]
        if field.startswith("max_") and value is None:
            continue
        if type(value) is not int or value < 0:
            return False

    if boundaries == {"min_days", "max_months_exclusive"}:
        # The reviewed mixed-unit format is one week to under six months.
        if source_age["min_days"] != 7 or source_age["max_months_exclusive"] != 6:
            return False
    else:
        unit = "days" if "min_days" in boundaries else "months"
        upper = source_age[f"max_{unit}_exclusive"]
        if upper is not None and upper <= source_age[f"min_{unit}"]:
            return False

    if child_age_days is not None and (type(child_age_days) is not int or child_age_days < 0):
        return False
    # Older evaluation callers supply months only. Live coaching supplies exact
    # days plus completed calendar months and never uses this legacy approximation.
    approx_child_days = child_age_days if child_age_days is not None else child_age_months * 30.4375

    # check day-based bounds for the newborn first week.
    if "min_days" in source_age and "max_days_exclusive" in source_age:
        min_days = source_age.get("min_days", 0)
        max_days = source_age.get("max_days_exclusive", 7)
        return approx_child_days >= min_days and (max_days is None or approx_child_days < max_days)

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

    return False


def build_age_filter(child_age_months: float, *, child_age_days: int | None = None) -> Filter:
    """Filter the existing payload in its original units, without day conversions."""
    if (type(child_age_months) not in (int, float)
            or not isfinite(child_age_months) or child_age_months < 0):
        raise ValueError("Child age must be a finite non-negative number of months.")
    if child_age_days is not None and (type(child_age_days) is not int or child_age_days < 0):
        raise ValueError("Child age in days must be a non-negative integer.")
    days = child_age_days if child_age_days is not None else child_age_months * 30.4375

    def band(lower: str, upper: str, age: float) -> Filter:
        return Filter(
            must=[FieldCondition(key=f"source_age.{lower}", range=Range(gte=0, lte=age))],
            should=[
                FieldCondition(key=f"source_age.{upper}", range=Range(gt=age)),
                IsNullCondition(is_null=PayloadField(key=f"source_age.{upper}")),
            ],
        )

    # Any one supported band can match. Python still rejects malformed metadata.
    return Filter(should=[
        band("min_days", "max_days_exclusive", days),
        Filter(must=[
            FieldCondition(key="source_age.min_days", range=Range(gte=7, lte=7)),
            FieldCondition(key="source_age.max_months_exclusive", range=Range(gte=6, lte=6, gt=child_age_months)),
            FieldCondition(key="source_age.min_days", range=Range(lte=days)),
        ]),
        band("min_months", "max_months_exclusive", child_age_months),
    ])


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
        *,
        child_age_days: int | None = None,
    ) -> list[RetrievedPassage]:
        if not query.strip():
            return []

        age_filter = None
        if child_age_months is not None:
            age_filter = build_age_filter(child_age_months, child_age_days=child_age_days)

        # Age filtering happens before ranking; retain extra candidates for routines.
        candidate_limit = max(limit * 5, 15)

        try:
            results = self.client.query_points(
                collection_name=self.collection_name,
                query=Document(
                    text=query.strip(),
                    model="sentence-transformers/all-minilm-l6-v2",
                ),
                limit=candidate_limit,
                query_filter=age_filter,
            )
        except Exception as exc:
            logger.error("error querying qdrant: %s", type(exc).__name__)
            raise

        filtered: list[RetrievedPassage] = []
        normalized_routine = routine.strip().lower() if routine else None

        for point in results.points:
            payload = point.payload or {}
            source_age = payload.get("source_age", {})

            # exclude passages outside the child's developmental age.
            if child_age_months is not None and not is_age_eligible(source_age, child_age_months, child_age_days=child_age_days):
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
