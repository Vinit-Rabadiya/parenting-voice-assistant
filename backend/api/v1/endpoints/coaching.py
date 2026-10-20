"""Authenticated, retrieval-grounded coaching and feedback routes."""

import logging
import time
from contextlib import contextmanager
from uuid import uuid4

from google.genai import errors as genai_errors
from fastapi import APIRouter, Depends, HTTPException
from starlette.concurrency import run_in_threadpool

from backend.api.dependencies import get_caregiver_data_service, get_coaching_service, get_retrieval_service
from backend.core.security import require_authenticated_user
from backend.schemas.coaching import CoachingRequest, CoachingResponse, CitationSchema, FeedbackRequest, FeedbackResponse
from backend.services.caregiver_data import CaregiverDataService
from backend.services.coaching import CoachingResult, CoachingService, generation_request_id
from backend.services.retrieval import RetrievalService
from backend.services.evidence import NO_GUIDANCE_MESSAGE, select_evidence
from backend.services.response_safety import SAFE_RESPONSE, inspect_response
from backend.core.config import settings


router = APIRouter(prefix="/coach", dependencies=[Depends(require_authenticated_user)])
logger = logging.getLogger(__name__)
# Use Uvicorn's console logger so temporary diagnostics appear at normal INFO level.
timing_logger = logging.getLogger("uvicorn.error.coaching_timing")


@contextmanager
def timed_stage(request_id: str, stage: str):
    token = generation_request_id.set(request_id)
    started = time.perf_counter()
    outcome = "failed"
    timing_logger.info("coach_timing request=%s stage=%s event=started", request_id, stage)
    try:
        yield
        outcome = "completed"
    finally:
        generation_request_id.reset(token)
        timing_logger.info(
            "coach_timing request=%s stage=%s event=%s seconds=%.3f",
            request_id, stage, outcome, time.perf_counter() - started,
        )


@router.post("", response_model=CoachingResponse)
async def coach(
    payload: CoachingRequest,
    user: dict = Depends(require_authenticated_user),
    data_service: CaregiverDataService = Depends(get_caregiver_data_service),
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
    coaching_service: CoachingService = Depends(get_coaching_service),
) -> CoachingResponse:
    # Random diagnostic correlation only; never log account or child identifiers.
    request_id = uuid4().hex[:12]
    with timed_stage(request_id, "profile_lookup"):
        child = await run_in_threadpool(data_service.get_child, user["uid"], payload.child_id)
    if child is None:
        raise HTTPException(status_code=404, detail="Select a child profile before asking for guidance.")
    if child.get("in_scope") is not True:
        raise HTTPException(status_code=422, detail="Coaching supports children from birth through their second birthday. Select a profile within this age range.")

    started = time.perf_counter()
    stage = "Qdrant retrieval"
    try:
        with timed_stage(request_id, "retrieval"):
            passages = await run_in_threadpool(retrieval_service.retrieve, payload.question, child["completed_months"], payload.routine, 3, child_age_days=child["age_days"])
        stage = "Evidence selection"
        with timed_stage(request_id, "evidence_selection"):
            evidence = select_evidence(passages, settings.RETRIEVAL_MIN_SCORE)
        timing_logger.info(
            "coach_timing request=%s passages=%d evidence=%d evidence_characters=%d",
            request_id, len(passages), len(evidence), sum(len(item.text) for item in evidence),
        )
        status = "answered" if evidence else "no_evidence"
        if evidence:
            stage = "Gemini generation"
            with timed_stage(request_id, "generation"):
                result = await run_in_threadpool(coaching_service.generate, payload.question, child["age_months"], payload.routine, evidence)
            stage = "Response safety"
            with timed_stage(request_id, "response_safety"):
                decision = inspect_response(result.answer, result.passages, evidence, child["age_months"])
                timing_logger.info(
                    "coaching_safety request=%s outcome=%s reasons=%s",
                    request_id, "blocked" if decision.blocked else "passed",
                    ",".join(decision.reasons) or "none",
                )
                if decision.blocked:
                    # Replace before storage and delivery; never save the blocked text.
                    status = "safety_blocked"
                    result = CoachingResult(answer=SAFE_RESPONSE, passages=[])
        else:
            # A normal response, not a service error: no generation call or supporting citations.
            result = CoachingResult(answer=NO_GUIDANCE_MESSAGE, passages=[])
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        if (stage == "Gemini generation" and isinstance(exc, genai_errors.ClientError)
                and exc.code == 429):
            logger.warning("Gemini generation request limit reached (primary_model=%s, code=429)", coaching_service.model)
            raise HTTPException(
                status_code=429,
                detail="The coaching service request limit has been reached. Please try again later.",
            ) from None
        if (stage == "Gemini generation" and isinstance(exc, genai_errors.ServerError)
                and exc.code == 503):
            logger.warning("Gemini generation unavailable (primary_model=%s, code=503)", coaching_service.model)
            raise HTTPException(
                status_code=503,
                detail="The coaching service is temporarily busy. Please try again later.",
            ) from None
        # Log diagnostic metadata only: provider exceptions can contain request content.
        logger.error("%s failed: %s (model=%s, code=%s, status=%s)", stage, type(exc).__name__,
                     coaching_service.model, getattr(exc, "code", None), getattr(exc, "status", None))
        if stage == "Gemini generation":
            # Provider descriptions explain errors such as unavailable model endpoints.
            # Redact credentials and user content before writing diagnostic output.
            description = str(getattr(exc, "message", "No provider description returned."))
            sensitive_values = [coaching_service.api_key, payload.question]
            sensitive_values.extend(passage.text for passage in passages)
            for value in sensitive_values:
                if value:
                    description = description.replace(value, "[redacted]")
            logger.error("Gemini error description: %s", description[:1500])
        raise HTTPException(status_code=502, detail="Guidance generation is unavailable. Please try again.") from None

    citations = [
        {"passage_id": item.passage_id, "source_title": item.source_title, "pdf_page": item.pdf_page,
         "source_url": item.source_url, "title": item.title}
        for item in result.passages
    ]
    with timed_stage(request_id, "interaction_save"):
        interaction_id = await run_in_threadpool(
            data_service.create_interaction, user["uid"], payload.child_id, payload.question, payload.routine, result.answer, citations, status
        )
    timing_logger.info(
        "coach_timing request=%s stage=reported_total event=completed seconds=%.3f",
        request_id, time.perf_counter() - started,
    )
    return CoachingResponse(interaction_id=interaction_id, answer=result.answer,
        citations=[CitationSchema(**citation) for citation in citations], child_age_months=child["age_months"],
        processing_seconds=round(time.perf_counter() - started, 3), status=status)


@router.post("/{interaction_id}/feedback", response_model=FeedbackResponse)
async def feedback(
    interaction_id: str,
    payload: FeedbackRequest,
    user: dict = Depends(require_authenticated_user),
    data_service: CaregiverDataService = Depends(get_caregiver_data_service),
) -> FeedbackResponse:
    recorded_at = await run_in_threadpool(data_service.save_feedback, user["uid"], interaction_id, payload.helpful, payload.comment)
    if recorded_at is None:
        raise HTTPException(status_code=404, detail="Interaction not found.")
    return FeedbackResponse(interaction_id=interaction_id, helpful=payload.helpful, recorded_at=recorded_at)
