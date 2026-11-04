"""Two pooled model services, with quota cooldowns and a bounded one-way retry."""
from email.utils import parsedate_to_datetime
import logging
from math import isfinite
import re
from threading import Lock
import time

from google.genai import errors

from backend.core.config import settings
from backend.services.coaching import CoachingService, generation_request_id
from backend.services.groq_client import GenerationProviderError

logger = logging.getLogger("uvicorn.error.coaching_timing")


def retry_delay(error, default: int) -> float:
    """Read only typed retry metadata; never expose provider descriptions."""
    raw = getattr(error, "retry_after_seconds", None)
    response = getattr(error, "response", None)
    if raw is None and response is not None:
        headers = getattr(response, "headers", None)
        raw = headers.get("Retry-After") if headers is not None else None
    if raw is not None:
        try:
            seconds = float(raw)
        except (TypeError, ValueError):
            try:
                seconds = parsedate_to_datetime(raw).timestamp() - time.time()
            except (TypeError, ValueError, OverflowError):
                seconds = default
        if isfinite(seconds) and seconds >= 0:
            return max(1, min(seconds, 86400))
    details = getattr(error, "details", None)
    if isinstance(details, dict):
        root = details.get("error", details)
        details = root.get("details", []) if isinstance(root, dict) else []
        if isinstance(details, list):
            for detail in details:
                if isinstance(detail, dict) and detail.get("@type") == "type.googleapis.com/google.rpc.RetryInfo":
                    match = re.fullmatch(r"(\d+(?:\.\d+)?)s", str(detail.get("retryDelay", "")))
                    if match:
                        return max(1, min(float(match[1]), 86400))
    return default


class ProviderFailoverService:
    supports_failover = True

    def __init__(self, *, services=None, primary=None, cooldown_seconds=None, clock=time.monotonic):
        self.provider = primary or settings.COACHING_PROVIDER
        if self.provider not in {"groq", "gemini"}:
            raise ValueError("Unsupported coaching provider.")
        self.order = (self.provider, "gemini" if self.provider == "groq" else "groq")
        self._owns_services = services is None
        self.services = services if services is not None else {
            provider: CoachingService(provider=provider, fallback_model="") for provider in self.order
        }
        if set(self.services) != {"groq", "gemini"}:
            raise ValueError("Failover requires both Groq and Gemini.")
        self.model = self.services[self.provider].model
        self.cooldown = settings.COACHING_PROVIDER_COOLDOWN_SECONDS if cooldown_seconds is None else cooldown_seconds
        if type(self.cooldown) is not int or not 1 <= self.cooldown <= 86400:
            raise ValueError("Provider cooldown must be between 1 and 86400 seconds.")
        self.clock = clock
        self._limited_until = {}
        self._lock = Lock()
        self._closed = False

    def generate(self, question, child_age_months, routine, passages, *, on_delta=None, on_reset=None, **context):
        attempted = set()
        for _ in self.order:
            with self._lock:
                if self._closed:
                    raise RuntimeError("Coaching service is closed.")
                now = self.clock()
                provider = next((name for name in self.order if name not in attempted
                                 and now >= self._limited_until.get(name, 0)), None)
                if provider is None:
                    break
                attempted.add(provider)
            emitted = False

            def forward(text):
                nonlocal emitted
                emitted = True
                on_delta(text)

            options = {**context, **({"on_delta": forward} if on_delta is not None else {})}
            try:
                result = self.services[provider].generate(question, child_age_months, routine, passages, **options)
            except (errors.ClientError, GenerationProviderError) as exc:
                if exc.code != 429:
                    raise
                delay = retry_delay(exc, self.cooldown)
                with self._lock:
                    self._limited_until[provider] = max(self._limited_until.get(provider, 0), self.clock() + delay)
                logger.info("generation_provider_limited request=%s provider=%s cooldown_seconds=%.1f",
                            generation_request_id.get() or "none", provider, delay)
                if emitted and on_reset is None:
                    raise GenerationProviderError(503) from None
                if on_reset is not None:
                    on_reset()
                continue
            logger.info("generation_provider_selected request=%s provider=%s model=%s",
                        generation_request_id.get() or "none", provider, self.services[provider].model)
            return result
        # No infinite retries and no quota messages or private provider details.
        raise GenerationProviderError(503, kind="providers_unavailable") from None

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._limited_until.clear()
        if self._owns_services:
            failure = None
            for service in self.services.values():
                try:
                    service.close()
                except Exception as exc:
                    failure = exc
            if failure is not None:
                raise failure
