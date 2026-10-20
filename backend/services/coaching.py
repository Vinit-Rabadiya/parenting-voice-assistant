"""Generate concise caregiver guidance from retrieved, source-linked passages."""

from dataclasses import dataclass

from google import genai
from google.genai import errors, types

from backend.core.config import settings
from backend.services.retrieval import RetrievedPassage


@dataclass
class CoachingResult:
    answer: str
    passages: list[RetrievedPassage]


class CoachingService:
    def __init__(self, api_key: str | None = None, model: str | None = None, client=None):
        self.api_key = (api_key or settings.GEMINI_API_KEY or "").strip()
        self.model = model or settings.GEMINI_MODEL
        self._client = client

    @property
    def client(self):
        if self._client is None:
            if not self.api_key:
                raise ValueError("GEMINI_API_KEY is not configured.")
            timeout = settings.GEMINI_TIMEOUT_SECONDS
            if type(timeout) is not int or not 1 <= timeout <= 120:
                raise ValueError("GEMINI_TIMEOUT_SECONDS must be an integer from 1 to 120.")
            self._client = genai.Client(
                api_key=self.api_key,
                http_options=types.HttpOptions(
                    timeout=timeout * 1000,  # The SDK expects milliseconds.
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
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
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.2),
            )
        except errors.APIError as exc:
            if exc.code == 504:
                raise TimeoutError("Guidance generation timed out.") from exc
            raise
        answer = (response.text or "").strip()
        if not answer:
            raise RuntimeError("The language model returned an empty answer.")
        return CoachingResult(answer=answer, passages=passages)
