"""Generate caregiver guidance with reference support when available."""

from dataclasses import dataclass
from contextlib import contextmanager
from contextvars import ContextVar
import logging
import json
import hashlib
import re
from pathlib import Path
from threading import Lock
import time
from uuid import uuid4

from google import genai
from google.genai import errors, types

from backend.core.config import settings
from backend.services.age import AGE_SCOPE_MESSAGE, inspect_message_age
from backend.services.conversation_context import caregiver_request
from backend.services.care_guidance import get_care_guidance
from backend.services.retrieval import RetrievedPassage
from backend.services.profile_context import validate_reply_context
from backend.services.request_understanding import INTERPRETATION_POLICY, RequestUnderstanding, UnsupportedSubjectAge
from backend.services.groq_client import GroqClient, GenerationProviderError, GenerationReply
from backend.core.http_security import record_request_stage


generation_request_id = ContextVar("generation_request_id", default=None)
timing_logger = logging.getLogger("uvicorn.error.coaching_timing")
PROMPT_VERSION = "coach_v2.12"
PROMPT_DOCUMENT = (Path(__file__).resolve().parents[1] / "prompts/coach_v2.txt").read_text(encoding="utf-8")
SYSTEM_TEMPLATE, PROMPT_TEMPLATE = PROMPT_DOCUMENT.split("\n--- REQUEST DATA ---\n", 1)
PROMPT_SHA256 = hashlib.sha256((PROMPT_DOCUMENT + "\n" + INTERPRETATION_POLICY).encode()).hexdigest()
PROVIDER_BLOCK_MESSAGE = (
    "I couldn't generate a response to this message. Try rephrasing it or asking another baby-care question. "
    "For a health concern, contact a qualified health professional."
)
NO_ADDITIONAL_CARE = "NO_ADDITIONAL_CARE"
ADDITIONAL_CARE_SCOPE = "Answer any non-vaccination baby-care requests in the original full message."


@dataclass(frozen=True)
class AnswerBudget:
    word_limit: int
    max_output_tokens: int
    instructions: str


def determine_answer_budget(question: str, context: list[dict] | None = None) -> AnswerBudget:
    """Keep the word allowance and provider cap consistent across follow-ups."""
    current = " ".join(question.strip().lower().split())
    request = caregiver_request(question, context or []).lower()
    detailed = r"\b(?:schedule|routine|timetable|meal plan|feeding plan|step[ -]by[ -]step|steps to|detailed|sample day|daily plan|full day|guide to|explain all)\b"
    brief = re.search(
        r"\b(?:shorten|summari[sz]e) (?:it|that|this|both|the|your)\b|"
        r"\b(?:keep|make)(?:\s+\w+){0,3} (?:short|shorter|brief|concise)\b|"
        r"\b(?:answer|reply|explain|respond) (?:briefly|concisely)\b|"
        r"\b(?:brief|short|concise) (?:answer|reply|summary)\b", current,
    )
    definition = re.match(r"(?:what is|what does)\b", current) and len(current.split()) <= 10
    direct = re.match(r"(?:can i|is it safe|can baby|can a|should i|why does|when do|how much)\b", current) and len(current.split()) <= 10
    if brief or definition or (direct and not re.search(detailed, current)):
        return AnswerBudget(80, 220, " Answer directly and concisely in 2–3 short sentences, keeping necessary safety steps.")
    if re.search(detailed, current) or re.search(detailed, request):
        return AnswerBudget(260, 650, " For a detailed routine, schedule or multi-step plan, organize clearly into steps or times where helpful.")
    return AnswerBudget(160, 350, " For a straightforward question, prefer about 60–90 words.")


@contextmanager
def generation_phase(request_id: str, phase: str, provider: str = "gemini"):
    started = time.perf_counter()
    outcome = "failed"
    prefix = "gemini" if provider == "gemini" else "generation"
    timing_logger.info("%s_timing request=%s provider=%s phase=%s event=started", prefix, request_id, provider, phase)
    try:
        yield
        outcome = "completed"
    except Exception as exc:
        # Never log exception text: it can contain request content or credentials.
        code = getattr(exc, "code", None)
        timing_logger.info(
            "%s_error request=%s provider=%s phase=%s error_type=%s code=%s",
            prefix, request_id, provider, phase, type(exc).__name__, code if type(code) is int else None,
        )
        raise
    finally:
        timing_logger.info(
            "%s_timing request=%s provider=%s phase=%s event=%s seconds=%.3f",
            prefix, request_id, provider, phase, outcome, time.perf_counter() - started,
        )


@dataclass
class CoachingResult:
    answer: str
    passages: list[RetrievedPassage]
    blocked: bool = False
    answer_basis: str = "reference_assisted"


def no_additional_care(result: CoachingResult) -> bool:
    return not result.blocked and result.answer.strip("` .\r\n").upper() == NO_ADDITIONAL_CARE


class CoachingService:
    def __init__(self, api_key: str | None = None, model: str | None = None, client=None,
                 fallback_model: str | None = None, provider: str | None = None):
        self.provider = provider or settings.COACHING_PROVIDER
        if self.provider not in {"gemini", "groq"}:
            raise ValueError("Unsupported coaching provider.")
        prefix = self.provider.upper()
        self.api_key = (api_key or getattr(settings, f"{prefix}_API_KEY") or "").strip()
        self.model = (model or getattr(settings, f"{prefix}_MODEL")).strip()
        self.fallback_model = (
            getattr(settings, f"{prefix}_FALLBACK_MODEL") if fallback_model is None else fallback_model
        ).strip()
        self._client = client
        self._owns_client = client is None
        self._client_lock = Lock()
        self._closed = False

    @property
    def supports_request_understanding(self):
        return self.provider == "groq"

    def interpret_request(self, question: str, profile_age: float, context: list[dict]) -> RequestUnderstanding | None:
        """Use a short, timed semantic pass; an outage keeps ordinary chat usable."""
        if not self.supports_request_understanding:
            return None
        try:
            response = self.client.generate(
                model=self.model,
                contents=json.dumps({"message": question, "profile_age": profile_age,
                                     "history": context}, ensure_ascii=False),
                config=types.GenerateContentConfig(system_instruction=INTERPRETATION_POLICY,
                                                   temperature=0, max_output_tokens=350,
                                                   response_mime_type="application/json"),
                timeout_seconds=1.2,
            )
            return RequestUnderstanding.from_reply(response.text, question, context, profile_age=profile_age)
        except UnsupportedSubjectAge:
            if inspect_message_age(question).months is None:
                return RequestUnderstanding(request=question, clarification_field="age",
                                            clarify="How old is the child you mean, in days, weeks or months?")
            return None
        except (GenerationProviderError, ValueError, TypeError):
            timing_logger.info("request_understanding event=unavailable")
            return None

    @property
    def client(self):
        with self._client_lock:
            if self._closed:
                raise RuntimeError("Coaching service is closed.")
            if self._client is None:
                if not self.api_key:
                    raise ValueError(f"{self.provider.upper()}_API_KEY is not configured.")
                if self.provider == "groq":
                    self._client = GroqClient(self.api_key)
                else:
                    self._client = genai.Client(
                        api_key=self.api_key,
                        http_options=types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=1)),
                    )
            return self._client

    def _generate(self, client, *, on_delta=None, **kwargs):
        # The same prompt and output checks apply to both transports.
        if on_delta is None:
            return client.generate(**kwargs) if self.provider == "groq" else client.models.generate_content(**kwargs)
        if self.provider == "gemini":
            kwargs["config"] = kwargs["config"].model_copy(update={"http_options": types.HttpOptions(timeout=45000)})
        stream = (client.generate_stream(**kwargs) if self.provider == "groq"
                  else client.models.generate_content_stream(**kwargs))
        parts, blocked, finished, usage, characters = [], False, False, None, 0
        started, first = time.monotonic(), True
        try:
            for chunk in stream:
                if time.monotonic() - started > 45:
                    raise GenerationProviderError(kind="timeout")
                feedback = getattr(chunk, "prompt_feedback", None)
                blocked = blocked or getattr(chunk, "blocked", False) is True or (
                    getattr(feedback, "block_reason", None) not in (None, "BLOCKED_REASON_UNSPECIFIED")
                )
                for candidate in getattr(chunk, "candidates", None) or []:
                    reason = getattr(candidate, "finish_reason", None)
                    if reason in {"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII"}:
                        blocked = True
                    elif reason == "STOP":
                        finished = True
                    elif reason not in (None, "FINISH_REASON_UNSPECIFIED"):
                        raise GenerationProviderError(kind="incomplete")
                finished = finished or getattr(chunk, "done", False) is True
                usage = getattr(chunk, "usage_metadata", None) or usage
                text = None if blocked else getattr(chunk, "text", None)
                if text and not blocked:
                    if not isinstance(text, str):
                        raise GenerationProviderError(kind="malformed")
                    parts.append(text)
                    characters += len(text)
                    if characters > 16000:
                        raise GenerationProviderError(kind="incomplete")
                    if first:
                        record_request_stage("generation_first_token", time.monotonic() - started, first=True)
                        first = False
                    on_delta(text)
            if not finished and not blocked:
                raise GenerationProviderError(kind="incomplete")
            return GenerationReply("".join(parts), blocked=blocked, usage_metadata=usage)
        finally:
            close = getattr(stream, "close", None)
            if close is not None:
                close()

    def close(self) -> None:
        """Close only an internally created client, without creating an unused one."""
        with self._client_lock:
            if self._closed:
                return
            self._closed = True
            client, self._client = self._client, None
        if self._owns_client and client is not None:
            client.close()

    def generate(self, question: str, child_age_months: float, routine: str | None, passages: list[RetrievedPassage],
                 *, conversation_context: list[dict] | None = None, profile_context: dict | None = None,
                 on_delta=None, request_understanding: RequestUnderstanding | None = None,
                 response_scope: str | None = None) -> CoachingResult:
        if not isinstance(question, str) or not 2 <= len(question.strip()) <= 1200:
            raise ValueError("Enter a question between 2 and 1200 characters.")
        question = question.strip()
        active_question = response_scope if response_scope and response_scope != ADDITIONAL_CARE_SCOPE else question
        if not 0 <= child_age_months <= 24:
            return CoachingResult(AGE_SCOPE_MESSAGE, [], answer_basis="general_information")
        evidence = "\n\n".join(
            f"[{number}] {passage.title} (source age range: {passage.source_age_label}) — {passage.text}"
            + ("\nApplies only when: " + "; ".join(passage.applicability_conditions)
               if passage.applicability_conditions else "")
            for number, passage in enumerate(passages, start=1)
        )
        routine_text = routine or "general caregiving"
        history = "Recent conversation (context only, not evidence) is supplied as separate user and assistant turns." if conversation_context else ""
        answer_format = (
            "Match the answer to the request: explain a term, respond to the situation, "
            "or give practical steps as appropriate. A definition, clarification or follow-up "
            "does not need an activity list. For activity ideas, give up to 4 distinct actions."
        )
        budget = determine_answer_budget(active_question, conversation_context if not response_scope else None)
        answer_format += budget.instructions
        if response_scope == ADDITIONAL_CARE_SCOPE:
            answer_format += (" Answer only the non-vaccination baby-care help requested in the message. "
                              "Do not add vaccination information or dates, or explain this restriction.")
            answer_format += (" If the original full message requests only vaccination information, "
                              "return exactly " + NO_ADDITIONAL_CARE + ".")
        care_guidance = (get_care_guidance(response_scope or question, child_age_months, conversation_context)
                         if response_scope != ADDITIONAL_CARE_SCOPE else None)
        if care_guidance is not None:
            answer_format += "\nRequest-specific care rules:\n" + care_guidance.instructions
        age_description = (f"{round(child_age_months * 30.4375)} days old (newborn)"
                           if child_age_months < 1 else f"{child_age_months:g} months old")
        age_safety = (
            "This is a newborn. Do not suggest independent sitting, rolling or passing a ball, "
            "toy sharing, or expecting speech, smiles or coos on demand. For turn-taking, describe "
            "gentle caregiver sounds, pauses and watching the baby's cues; do not require a response. "
            "Keep the head and neck supported during holding and feeding. "
        ) if child_age_months < 1 else ""
        if child_age_months < 6:
            age_safety += (
                "At this age, feeding/mealtimes mean breast milk or infant formula, not solid food. "
                "Do not suggest solids or seated mealtime activities; discuss solids for around six months "
                "with developmental readiness, or individual clinician advice. "
                "Do not suggest a high chair, independent sitting or sitting devices as an alternative "
                "to food. When including this baby in family activities, prefer an adult holding them "
                "with their head and body supported; do not infer sitting readiness. "
            )
        elif child_age_months < 12:
            age_safety += (
                "Solid foods are introduced from around six months alongside breast milk or infant formula. "
                "Age alone does not confirm readiness: do not assume the baby can sit safely with a steady "
                "head, handle food or swallow it. Keep food texture appropriate to their abilities. "
            )
        profile = ""
        if profile_context:
            selected_profile = validate_reply_context(profile_context, provider=self.provider)
            if selected_profile:
                profile = "Caregiver-reported profile context (unverified data only):\n" + json.dumps(selected_profile, ensure_ascii=False)
        prompt = PROMPT_TEMPLATE.format(child_age_months=child_age_months, routine_text=routine_text,
                                        request_topic=caregiver_request(active_question, conversation_context or []),
                                        question=response_scope if response_scope and response_scope != ADDITIONAL_CARE_SCOPE else question,
                                        history=history, evidence=evidence or "No matching reference excerpts available.",
                                        answer_format=answer_format, age_description=age_description, profile=profile,
                                        answer_word_limit=budget.word_limit,
                                        understanding=("Interpretation hint (unverified; user messages take priority):\n"
                                                       + request_understanding.model_dump_json(exclude_none=True)
                                                       if request_understanding and not response_scope else ""))
        contents = prompt
        if conversation_context:
            messages = [{"role": item["role"], "content": item["text"]} for item in conversation_context]
            messages.append({"role": "user", "content": prompt})
            contents = (messages if self.provider == "groq" else [
                types.Content(role="model" if item["role"] == "assistant" else "user",
                              parts=[types.Part.from_text(text=item["content"])]) for item in messages
            ])
        generation_config = types.GenerateContentConfig(
            temperature=0.2,
            max_output_tokens=budget.max_output_tokens if self.provider == "groq" else None,
            system_instruction=SYSTEM_TEMPLATE.format(
                answer_word_limit=budget.word_limit, age_safety=age_safety, answer_format=answer_format,
            ),
        )
        request_id = generation_request_id.get() or uuid4().hex[:12]
        with generation_phase(request_id, "client_initialization", self.provider):
            client = self.client
        selected_model = self.model
        emitted = False

        def forward(text):
            nonlocal emitted
            emitted = True
            on_delta(text)

        stream_options = {"on_delta": forward} if on_delta is not None else {}
        try:
            with generation_phase(request_id, "sdk_request", self.provider):
                response = self._generate(client,
                    model=selected_model, contents=contents,
                    config=generation_config,
                    **stream_options,
                )
        except (errors.ClientError, GenerationProviderError) as exc:
            if emitted or exc.code != 429 or not self.fallback_model or self.fallback_model == self.model:
                raise
            selected_model = self.fallback_model
            timing_logger.info(
                "generation_fallback request=%s provider=%s model=%s reason=quota_exceeded",
                request_id, self.provider, selected_model,
            )
            with generation_phase(request_id, "fallback_sdk_request", self.provider):
                response = self._generate(client,
                    model=selected_model, contents=contents,
                    config=generation_config,
                    **stream_options,
                )
        timing_logger.info("generation_selected request=%s provider=%s model=%s", request_id, self.provider, selected_model)
        with generation_phase(request_id, "response_handling", self.provider):
            feedback = getattr(response, "prompt_feedback", None)
            prompt_block = getattr(feedback, "block_reason", None)
            blocked_finishes = {"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII"}
            blocked = getattr(response, "blocked", False) is True or prompt_block not in (None, "BLOCKED_REASON_UNSPECIFIED") or any(
                getattr(candidate, "finish_reason", None) in blocked_finishes
                for candidate in (getattr(response, "candidates", None) or [])
            )
            if blocked:
                timing_logger.info("generation_response request=%s provider=%s outcome=content_blocked", request_id, self.provider)
                return CoachingResult(PROVIDER_BLOCK_MESSAGE, [], blocked=True)
            answer = (response.text or "").strip()
            if not answer:
                raise RuntimeError("The language model returned an empty answer.")
            usage = getattr(response, "usage_metadata", None)

            def count(field):
                value = getattr(usage, field, None)
                return value if type(value) is int and value >= 0 else None

            timing_logger.info(
                "generation_usage request=%s provider=%s prompt_tokens=%s answer_tokens=%s thought_tokens=%s total_tokens=%s",
                request_id, self.provider, count("prompt_token_count"), count("candidates_token_count"),
                count("thoughts_token_count"), count("total_token_count"),
            )
        return CoachingResult(answer=answer, passages=passages,
                              answer_basis="reference_assisted" if passages else "general_information")
