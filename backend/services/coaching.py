"""Generate concise caregiver guidance from retrieved, source-linked passages."""

from dataclasses import dataclass
from contextlib import contextmanager
from contextvars import ContextVar
import logging
import time
from uuid import uuid4

from google import genai
from google.genai import errors, types

from backend.core.config import settings
from backend.services.retrieval import RetrievedPassage


generation_request_id = ContextVar("generation_request_id", default=None)
timing_logger = logging.getLogger("uvicorn.error.coaching_timing")


@contextmanager
def generation_phase(request_id: str, phase: str):
    started = time.perf_counter()
    outcome = "failed"
    timing_logger.info("gemini_timing request=%s phase=%s event=started", request_id, phase)
    try:
        yield
        outcome = "completed"
    except Exception as exc:
        # Never log exception text: it can contain request content or credentials.
        code = getattr(exc, "code", None)
        timing_logger.info(
            "gemini_error request=%s phase=%s error_type=%s code=%s",
            request_id, phase, type(exc).__name__, code if type(code) is int else None,
        )
        raise
    finally:
        timing_logger.info(
            "gemini_timing request=%s phase=%s event=%s seconds=%.3f",
            request_id, phase, outcome, time.perf_counter() - started,
        )


@dataclass
class CoachingResult:
    answer: str
    passages: list[RetrievedPassage]


class CoachingService:
    def __init__(self, api_key: str | None = None, model: str | None = None, client=None,
                 fallback_model: str | None = None):
        self.api_key = (api_key or settings.GEMINI_API_KEY or "").strip()
        self.model = model or settings.GEMINI_MODEL
        self.fallback_model = (
            settings.GEMINI_FALLBACK_MODEL if fallback_model is None else fallback_model
        ).strip()
        self._client = client

    @property
    def client(self):
        if self._client is None:
            if not self.api_key:
                raise ValueError("GEMINI_API_KEY is not configured.")
            self._client = genai.Client(
                api_key=self.api_key,
                http_options=types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=1)),
            )
        return self._client

    def generate(self, question: str, child_age_months: float, routine: str | None, passages: list[RetrievedPassage]) -> CoachingResult:
        if not passages:
            return CoachingResult(
                answer="I do not have suitable guidance for that question yet. Please ask a health worker or early-childhood professional for help.",
                passages=[],
            )

        evidence = "\n\n".join(
            f"[{number}] {passage.title} — {passage.text}"
            for number, passage in enumerate(passages, start=1)
        )
        routine_text = routine or "general caregiving"
        prompt = f"""Child age: {child_age_months:g} months
Routine: {routine_text}
Caregiver question: {question}

Evidence excerpts:
{evidence}

Write one warm, practical answer of at most 90 words. Use only the evidence excerpts.
Give 2 to 4 short actions in plain language. Do not diagnose, prescribe medicine,
give a dose, invent a milestone, or make a claim not supported by the excerpts.
If the excerpts do not answer the question, say so and suggest contacting a health worker.
Do not use markdown headings or citation markers; the application shows the sources separately."""
        request_id = generation_request_id.get() or uuid4().hex[:12]
        with generation_phase(request_id, "client_initialization"):
            client = self.client
        selected_model = self.model
        try:
            with generation_phase(request_id, "sdk_request"):
                response = client.models.generate_content(
                    model=selected_model, contents=prompt,
                    config=types.GenerateContentConfig(temperature=0.2),
                )
        except errors.ClientError as exc:
            if exc.code != 429 or not self.fallback_model or self.fallback_model == self.model:
                raise
            selected_model = self.fallback_model
            timing_logger.info(
                "gemini_fallback request=%s model=%s reason=quota_exceeded",
                request_id, selected_model,
            )
            with generation_phase(request_id, "fallback_sdk_request"):
                response = client.models.generate_content(
                    model=selected_model, contents=prompt,
                    config=types.GenerateContentConfig(temperature=0.2),
                )
        timing_logger.info("gemini_selected request=%s model=%s", request_id, selected_model)
        with generation_phase(request_id, "response_handling"):
            answer = (response.text or "").strip()
            if not answer:
                raise RuntimeError("The language model returned an empty answer.")
            usage = getattr(response, "usage_metadata", None)

            def count(field):
                value = getattr(usage, field, None)
                return value if type(value) is int and value >= 0 else None

            timing_logger.info(
                "gemini_usage request=%s prompt_tokens=%s answer_tokens=%s thought_tokens=%s total_tokens=%s",
                request_id, count("prompt_token_count"), count("candidates_token_count"),
                count("thoughts_token_count"), count("total_token_count"),
            )
        return CoachingResult(answer=answer, passages=passages)
