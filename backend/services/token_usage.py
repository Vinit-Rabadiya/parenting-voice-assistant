"""Collect provider-reported model usage without retaining request data."""

from collections import Counter
from datetime import datetime, timezone
import logging
from threading import Lock
import time

from firebase_admin import firestore

from backend.schemas.admin import ProviderTokenCounts, TokenCounts, TokenUsageSummary

PROVIDERS = ("gemini", "groq")
COUNT_FIELDS = tuple(TokenCounts.model_fields)
logger = logging.getLogger("uvicorn.error")


class TokenUsageService:
    def __init__(self, get_client, environment):
        self._get_client = get_client
        self._environment = environment
        self._lock = Lock()
        self._pending = {}
        self._closed = False

    def _document(self, client, provider):
        return client.collection("model_token_usage").document(f"{self._environment}-{provider}")

    def record(self, provider, *, input_tokens, output_tokens, thinking_tokens, total_tokens):
        counts = {"input_tokens": input_tokens, "output_tokens": output_tokens, "thinking_tokens": thinking_tokens}
        if provider not in PROVIDERS or all(value is None for value in (input_tokens, output_tokens, thinking_tokens, total_tokens)):
            return
        observed = {field: value for field, value in counts.items() if value is not None}
        observed["total_tokens"] = total_tokens if total_tokens is not None else sum(observed.values())
        observed["model_calls"] = 1
        with self._lock:
            if not self._closed:
                totals, _ = self._pending.setdefault(provider, (Counter(), int(time.time())))
                totals.update(observed)

    def flush(self):
        with self._lock:
            pending, self._pending = self._pending, {}
        if not pending:
            return
        try:
            client = self._get_client()
            batch = client.batch()
            for provider, (counts, first_seen) in pending.items():
                changes = {field: firestore.Increment(value) for field, value in counts.items()}
                changes["first_recorded_epoch"] = firestore.Minimum(first_seen)
                batch.set(self._document(client, provider), changes, merge=True)
            # Replaying an increment after an ambiguous commit can double-count.
            batch.commit(retry=None, timeout=5)
        except Exception as exc:
            logger.warning("model_token_usage_write_failed error_type=%s", type(exc).__name__)

    def close(self):
        with self._lock:
            self._closed = True
        self.flush()

    def summary(self):
        client = self._get_client()
        documents = [self._document(client, provider) for provider in PROVIDERS]
        providers_by_path = {document.path: provider for document, provider in zip(documents, PROVIDERS)}
        snapshots = client.get_all(documents, field_paths=(*COUNT_FIELDS, "first_recorded_epoch"), retry=None, timeout=5)
        records = {providers_by_path[snapshot.reference.path]: snapshot.to_dict() for snapshot in snapshots if snapshot.exists}
        totals = Counter()
        first_seen = []
        providers = []
        for provider in PROVIDERS:
            record = records.get(provider) or {}
            counts = {field: record.get(field, 0) for field in COUNT_FIELDS}
            providers.append(ProviderTokenCounts(provider=provider, **counts))
            totals.update(counts)
            if "first_recorded_epoch" in record:
                first_seen.append(record["first_recorded_epoch"])
        return TokenUsageSummary(first_recorded_at=datetime.fromtimestamp(min(first_seen), timezone.utc) if first_seen else None,
                                 total=TokenCounts(**totals), providers=providers)
