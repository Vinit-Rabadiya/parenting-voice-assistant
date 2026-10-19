"""Authenticated, retrieval-grounded coaching and feedback routes."""

import logging
import time

from fastapi import APIRouter, Depends, HTTPException
from starlette.concurrency import run_in_threadpool

from backend.api.dependencies import get_caregiver_data_service, get_coaching_service, get_retrieval_service
from backend.core.security import require_authenticated_user
from backend.schemas.coaching import CoachingRequest, CoachingResponse, CitationSchema, FeedbackRequest, FeedbackResponse
from backend.services.caregiver_data import CaregiverDataService
from backend.services.coaching import CoachingResult, CoachingService
from backend.services.retrieval import RetrievalService
from backend.services.evidence import NO_GUIDANCE_MESSAGE, select_evidence
from backend.core.config import settings


router = APIRouter(prefix="/coach", dependencies=[Depends(require_authenticated_user)])
logger = logging.getLogger(__name__)


@router.post("", response_model=CoachingResponse)
async def coach(
    payload: CoachingRequest,
    user: dict = Depends(require_authenticated_user),
    data_service: CaregiverDataService = Depends(get_caregiver_data_service),
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
    coaching_service: CoachingService = Depends(get_coaching_service),
) -> CoachingResponse:
    child = await run_in_threadpool(data_service.get_child, user["uid"], payload.child_id)
    if child is None:
        raise HTTPException(status_code=404, detail="Select a child profile before asking for guidance.")

    started = time.perf_counter()
    stage = "Qdrant retrieval"
    try:
        passages = await run_in_threadpool(retrieval_service.retrieve, payload.question, child["age_months"], payload.routine, 3)
        stage = "Evidence selection"
        evidence = select_evidence(passages, settings.RETRIEVAL_MIN_SCORE)
        status = "answered" if evidence else "no_evidence"
        if evidence:
            stage = "Gemini generation"
            result = await run_in_threadpool(coaching_service.generate, payload.question, child["age_months"], payload.routine, evidence)
        else:
            # A normal response, not a service error: no generation call or supporting citations.
            result = CoachingResult(answer=NO_GUIDANCE_MESSAGE, passages=[])
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
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
    interaction_id = await run_in_threadpool(
        data_service.create_interaction, user["uid"], payload.child_id, payload.question, payload.routine, result.answer, citations, status
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
