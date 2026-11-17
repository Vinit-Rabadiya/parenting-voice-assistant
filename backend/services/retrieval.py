from dataclasses import dataclass, field as dataclass_field
from collections import OrderedDict
from copy import deepcopy
from functools import lru_cache
import hmac
import json
import logging
from math import ceil, isfinite
from pathlib import Path
from secrets import token_bytes
from threading import Lock
from time import monotonic, sleep
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Document, FieldCondition, Filter, IsNullCondition, PayloadField, Range,
)

from backend.core.config import settings

logger = logging.getLogger(__name__)

SOURCE_MANIFESTS = (
    "sources.json", "common-care-guidance.json", "reference-expansion.json",
    "health-reference-expansion.json", "pdf-health-reference-expansion.json",
    "everyday-care-reference-expansion.json", "activity-safety-reference-expansion.json",
    "practical-care-reference-expansion.json",
)


def _canonical_source_url(value: str) -> str | None:
    """Normalize citation identity without accepting another publisher or path."""
    if not isinstance(value, str) or not value or any(ord(char) < 33 or ord(char) == 127 or char == "\\" for char in value):
        return None
    try:
        parsed = urlsplit(value)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.port not in (None, 443)):
            return None
        return urlunsplit(("https", parsed.hostname.lower(), parsed.path or "/", parsed.query, ""))
    except ValueError:
        return None


@lru_cache(maxsize=1)
def _approved_source_urls() -> frozenset[str]:
    """Use the versioned local source registry, never destinations from Qdrant."""
    urls = set()
    directory = Path(__file__).resolve().parents[2] / "data"
    for name in SOURCE_MANIFESTS:
        sources = json.loads((directory / name).read_text(encoding="utf-8"))["sources"]
        records = sources.values() if isinstance(sources, dict) else sources
        for record in records:
            url = _canonical_source_url(record.get("source_url") or record.get("url"))
            if url is None:
                raise ValueError("The checked-in source registry contains an invalid citation URL.")
            urls.add(url)
    return frozenset(urls)


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
    applicability_conditions: list[str] = dataclass_field(default_factory=list)
    selection_method: str = "vector_retrieval"


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
        *,
        allow_candidate_content: bool = False,
        cache_ttl_seconds: float | None = None,
        corpus_revision: str | None = None,
        source_urls=None,
    ):
        self.url = (url or settings.QDRANT_URL or "").strip()
        self.api_key = (api_key or settings.QDRANT_API_KEY or "").strip()
        self.collection_name = collection_name or settings.QDRANT_COLLECTION
        if type(allow_candidate_content) is not bool:
            raise ValueError("allow_candidate_content must be a boolean.")
        if allow_candidate_content and self.collection_name == settings.QDRANT_COLLECTION:
            raise ValueError("Candidate content is restricted to a separate evaluation collection.")
        self.allow_candidate_content = allow_candidate_content
        self.corpus_revision = settings.QDRANT_CORPUS_REVISION if corpus_revision is None else corpus_revision
        self._cache_ttl = settings.RETRIEVAL_CACHE_TTL_SECONDS if cache_ttl_seconds is None else cache_ttl_seconds
        if type(self._cache_ttl) not in (int, float) or not isfinite(self._cache_ttl) or not 0 <= self._cache_ttl <= 300:
            raise ValueError("Retrieval cache TTL must be between 0 and 300 seconds.")
        # Keys never retain the question, account identifiers or profile notes.
        # A per-instance secret also prevents dictionary lookup of question hashes.
        self._cache_secret = token_bytes(32)
        self._cache: OrderedDict[str, tuple[float, list[RetrievedPassage]]] = OrderedDict()
        self._cache_epoch = 0
        self._client = client
        self._owns_client = client is None
        self._client_lock = Lock()
        self._closed = False
        if isinstance(source_urls, str):
            raise ValueError("Source URL policy must be a collection of approved HTTPS URLs.")
        self._source_urls = None if source_urls is None else frozenset(_canonical_source_url(value) for value in source_urls)
        if self._source_urls is not None and (not self._source_urls or None in self._source_urls):
            raise ValueError("Source URL policy must contain approved HTTPS URLs.")
        self._ready: bool | None = None

    @property
    def readiness(self) -> bool | None:
        """Last observed reference-service availability, without a network call."""
        with self._client_lock:
            return self._ready

    def _record_availability(self, ready: bool) -> None:
        with self._client_lock:
            if not self._closed:
                self._ready = ready

    @property
    def client(self) -> QdrantClient:
        with self._client_lock:
            if self._closed:
                raise RuntimeError("Retrieval service is closed.")
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

    def close(self) -> None:
        """Close only an internally created client, without creating an unused one."""
        with self._client_lock:
            if self._closed:
                return
            self._closed = True
            self._cache.clear()
            self._cache_epoch += 1
            client, self._client = self._client, None
        if self._owns_client and client is not None:
            client.close()

    def clear_cache(self) -> None:
        """Invalidate reference results, including any query already in flight."""
        with self._client_lock:
            self._cache.clear()
            self._cache_epoch += 1

    def warmup(self, *, timeout: float = 5.0, retries: int = 2) -> dict[str, Any]:
        """Warm inference with one query per attempt and a shared retry deadline."""
        if type(timeout) not in (int, float) or not isfinite(timeout) or not 0 < timeout <= 30:
            raise ValueError("Warmup timeout must be greater than zero and at most 30 seconds.")
        if type(retries) is not int or not 0 <= retries <= 3:
            raise ValueError("Warmup retries must be an integer from zero to three.")
        started = monotonic()
        deadline = started + timeout
        last_error = None
        attempts = 0
        self._record_availability(False)
        for _ in range(retries + 1):
            remaining = deadline - monotonic()
            if remaining <= 0:
                break
            attempts += 1
            try:
                # Successful inference also proves the collection exists.
                # Avoid metadata round trips that do not warm the encoder.
                self.client.query_points(
                    collection_name=self.collection_name,
                    query=Document(text="baby care guidance", model="sentence-transformers/all-minilm-l6-v2"),
                    limit=1, with_payload=False, with_vectors=False,
                    timeout=max(1, ceil(remaining)),
                )
                self._record_availability(True)
                duration = monotonic() - started
                logger.info(
                    "qdrant_warmup status=ready duration_seconds=%.3f attempts=%d", duration, attempts,
                )
                return {
                    "status": "ready",
                    "duration_seconds": round(duration, 3),
                    "attempts": attempts,
                }
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "qdrant_warmup_attempt_failed attempt=%d error_type=%s",
                    attempts, type(exc).__name__,
                )
                remaining = deadline - monotonic()
                if attempts <= retries and remaining > 0:
                    sleep(min(0.25, remaining))

        duration = monotonic() - started
        logger.error(
            "qdrant_warmup_failed duration_seconds=%.3f error_type=%s",
            duration, type(last_error).__name__,
        )
        return {
            "status": "degraded",
            "error": type(last_error).__name__,
            "duration_seconds": round(duration, 3),
            "attempts": attempts,
        }

    def retrieve(
        self,
        query: str,
        child_age_months: float | None = None,
        routine: str | None = None,
        limit: int = 3,
        *,
        child_age_days: int | None = None,
        candidate_limit: int | None = None,
    ) -> list[RetrievedPassage]:
        if not query.strip():
            return []

        age_filter = None
        if child_age_months is not None:
            age_filter = build_age_filter(child_age_months, child_age_days=child_age_days)

        # Age eligibility is mandatory. Routine is only a preference: a stale
        # selection must not hide a semantically relevant source for a new topic.
        if candidate_limit is None:
            candidate_limit = max(limit * 5, 15)
        elif type(candidate_limit) is not int or candidate_limit < limit or candidate_limit < 1:
            raise ValueError("candidate_limit must be a positive integer at least as large as limit.")

        normalized_routine = routine.strip().lower() if routine else None
        key = hmac.digest(self._cache_secret, json.dumps([
            self.url, self.collection_name, self.corpus_revision, self.allow_candidate_content,
            "sentence-transformers/all-minilm-l6-v2", query.strip(), child_age_months,
            child_age_days, normalized_routine, limit, candidate_limit,
        ], separators=(",", ":")).encode(), "sha256").hex()
        with self._client_lock:
            if self._closed:
                raise RuntimeError("Retrieval service is closed.")
            now = monotonic()
            for expired in [item for item, (deadline, _) in self._cache.items() if deadline <= now]:
                del self._cache[expired]
            cached = self._cache.get(key) if self._cache_ttl else None
            if cached is not None:
                self._cache.move_to_end(key)
                return deepcopy(cached[1])
            epoch = self._cache_epoch

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
            self._record_availability(True)
        except Exception as exc:
            self._record_availability(False)
            logger.error("error querying qdrant: %s", type(exc).__name__)
            raise

        filtered: list[RetrievedPassage] = []

        for point in results.points:
            payload = point.payload
            if not isinstance(payload, dict):
                continue
            text, score = payload.get("text"), point.score
            source_url = payload.get("source_url")
            routines = payload.get("routines", [])
            source_age = payload.get("source_age", {})
            project_scope = payload.get("project_scope", {})
            # One malformed result must not abort the search or occupy a slot
            # ahead of a valid source when ranking the full candidate pool.
            if (not isinstance(text, str) or not text.strip()
                    or type(score) not in (int, float) or not isfinite(score)
                    or not isinstance(routines, list)
                    or any(not isinstance(value, str) or not value.strip() for value in routines)
                    or not isinstance(source_age, dict) or not isinstance(project_scope, dict)):
                continue
            # The collection can supply excerpts, not arbitrary destinations.
            # An approved URL does not itself prove that an excerpt is accurate.
            approved_urls = self._source_urls if self._source_urls is not None else _approved_source_urls()
            if _canonical_source_url(source_url) not in approved_urls:
                continue
            # A collection configuration change must not silently publish review-only
            # candidates. Only explicit evaluation instances may inspect these records.
            if not self.allow_candidate_content and (
                payload.get("review_status") == "candidate_not_expert_validated"
                or payload.get("release_status") == "blocked_pending_health_review"
                or (payload.get("clinical_review_required") is not None
                    and payload.get("clinical_review_required") is not False)
            ):
                continue
            project_maximum = project_scope.get("max_months_inclusive")
            if child_age_months is not None and isinstance(project_maximum, (int, float)) and child_age_months > project_maximum:
                continue

            # exclude passages outside the child's developmental age.
            if child_age_months is not None and not is_age_eligible(source_age, child_age_months, child_age_days=child_age_days):
                continue

            point_routines = [value.strip().lower() for value in routines]

            conditions = payload.get("applicability_conditions", [])
            if not isinstance(conditions, list) or any(not isinstance(value, str) or not value.strip() for value in conditions):
                continue
            filtered.append(
                RetrievedPassage(
                    passage_id=payload.get("passage_id", str(point.id)),
                    text=text,
                    title=payload.get("title", ""),
                    source_title=payload.get("source_title", "Parenting Reference"),
                    pdf_page=payload.get("pdf_page", 1),
                    source_url=source_url,
                    score=float(score),
                    source_age_label=source_age.get("label", "0-24 months"),
                    routines=point_routines,
                    applicability_conditions=conditions,
                )
            )

        # Prefer semantic score; use the routine to break equal-score ties only.
        # Preserve original scores for the evidence cutoff and provenance checks.
        filtered.sort(key=lambda passage: (passage.score, normalized_routine in passage.routines), reverse=True)
        filtered = filtered[:limit]

        # Cache only successful, nonempty, filtered public source passages.
        # Never cache provider errors, model replies or caregiver/profile records.
        if filtered and self._cache_ttl:
            with self._client_lock:
                if not self._closed and epoch == self._cache_epoch:
                    self._cache[key] = monotonic() + self._cache_ttl, deepcopy(filtered)
                    self._cache.move_to_end(key)
                    while len(self._cache) > 128:
                        self._cache.popitem(last=False)
        return filtered
