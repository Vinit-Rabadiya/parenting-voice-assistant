"""Authenticated, retrieval-grounded coaching and feedback routes."""

import logging
import time
from contextlib import contextmanager
from uuid import uuid4
from typing import Annotated

from google.genai import errors as genai_errors
from fastapi import APIRouter, Depends, HTTPException, Path
from starlette.concurrency import run_in_threadpool

from backend.api.dependencies import get_caregiver_data_service, get_coaching_service, get_retrieval_service
from backend.api.dependencies import enforce_usage_limit, get_usage_control_service
from backend.core.security import require_authenticated_user, require_caregiver_user
from backend.api.consent import require_processing_consent
from backend.schemas.coaching import CoachingRequest, CoachingResponse, CitationSchema, FeedbackRequest, FeedbackResponse
from backend.services.caregiver_data import CaregiverDataService
from backend.services.age import message_age_months
from backend.services.coaching import CoachingResult, CoachingService, generation_request_id, PROVIDER_BLOCK_MESSAGE
from backend.services.usage import UsageControlService
from backend.services.retrieval import RetrievalService
from backend.services.evidence import select_evidence
from backend.services.care_response import professional_assessment_response, conversation_boundary_response
from backend.services.response_safety import SAFE_RESPONSE, SafetyDecision, inspect_response
from backend.services.input_safety import ESCALATION_MESSAGE, inspect_input
from backend.services.crisis_safety import inspect_crisis
from backend.services.vaccination import inspect_vaccination
from backend.services.conversation_context import (
    MAX_CONTEXT_MESSAGES, contextual_retrieval_query, is_follow_up, select_conversation_context,
)
from backend.core.config import settings


router = APIRouter(prefix="/coach", dependencies=[Depends(require_caregiver_user)])
logger = logging.getLogger(__name__)
# Use Uvicorn's console logger so temporary diagnostics appear at normal INFO level.
timing_logger = logging.getLogger("uvicorn.error.coaching_timing")


async def save_coaching_response(data_service: CaregiverDataService, uid: str,
                                 payload: CoachingRequest, response: CoachingResponse) -> None:
    """Use one storage path per answer; never duplicate new messages as interactions."""
    if payload.conversation_id is not None:
        stored = response.model_dump(include={
            "citations", "support_resources", "status", "safety",
            "child_age_months", "processing_seconds",
            "answer_basis", "reference_status",
        })
        if response.vaccination_country is not None:
            stored["vaccination_country"] = response.vaccination_country
        if response.response_kind is not None:
            stored["response_kind"] = response.response_kind
        stored["text"] = response.answer
        response.message_id = await run_in_threadpool(
            data_service.save_conversation_turn, uid, payload.conversation_id,
            payload.child_id, payload.question, payload.routine, stored,
        )
        response.conversation_id = payload.conversation_id
    else:
        response.interaction_id = await run_in_threadpool(
            data_service.create_interaction, uid, payload.child_id, payload.question,
            payload.routine, response.answer,
            [citation.model_dump() for citation in response.citations], response.status,
            **({"vaccination_country": response.vaccination_country} if response.vaccination_country else {}),
            **({"response_kind": response.response_kind} if response.response_kind else {}),
            **({"answer_basis": response.answer_basis, "reference_status": response.reference_status}
               if response.answer_basis else {}),
        )


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


@router.post("", response_model=CoachingResponse, dependencies=[Depends(require_processing_consent)])
async def coach(
    payload: CoachingRequest,
    user: dict = Depends(require_authenticated_user),
    data_service: CaregiverDataService = Depends(get_caregiver_data_service),
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
    coaching_service: CoachingService = Depends(get_coaching_service),
    usage: UsageControlService = Depends(get_usage_control_service),
) -> CoachingResponse:
    # Random diagnostic correlation only; never log account or child identifiers.
    request_id = uuid4().hex[:12]
    with timed_stage(request_id, "profile_lookup"):
        child = await run_in_threadpool(data_service.get_child, user["uid"], payload.child_id)
    if child is None:
        raise HTTPException(status_code=404, detail="Select a child profile before asking for guidance.")
    explicit_age = message_age_months(payload.question)
    outside_age_range = explicit_age is None and child.get("in_scope") is False
    age_months = child["age_months"] if explicit_age is None else explicit_age
    completed_months = child["completed_months"] if explicit_age is None else int(explicit_age)
    age_days = child["age_days"] if explicit_age is None else round(explicit_age * 30.4375)
    # Urgent reports take priority over retrieval and ordinary generation.
    triage_started = time.perf_counter()
    with timed_stage(request_id, "caregiver_safety"):
        crisis = inspect_crisis(payload.question, payload.support_country)
    with timed_stage(request_id, "input_safety"):
        triage = inspect_input(payload.question, completed_months)
    timing_logger.info(
        "coaching_caregiver_safety request=%s outcome=%s reasons=%s",
        request_id, crisis.kind or "not_flagged", ",".join(crisis.reasons) or "none",
    )
    timing_logger.info(
        "coaching_input_safety request=%s outcome=%s reasons=%s",
        request_id, "escalate" if triage.escalate else "not_flagged",
        ",".join(triage.reasons) or "none",
    )
    if triage.escalate or crisis.kind:
        citations = list(triage.citations)
        # A child danger sign takes priority; caregiver resources are still retained.
        status = "escalated" if triage.escalate else crisis.kind
        answer = ESCALATION_MESSAGE if triage.escalate else crisis.answer
        # No retrieval or generation is needed for this fixed referral message.
        response = CoachingResponse(
            interaction_id=None, answer=answer,
            citations=[CitationSchema(**citation) for citation in citations],
            child_age_months=age_months,
            processing_seconds=round(time.perf_counter() - triage_started, 3),
            status=status, safety="not_flagged" if status == "caregiver_support" else "escalate",
            support_resources=list(crisis.resources),
        )
        try:
            with timed_stage(request_id, "interaction_save"):
                await save_coaching_response(data_service, user["uid"], payload, response)
        except Exception:
            # A persistence outage must not replace a recognized danger referral
            # with a generic error. No fabricated interaction ID is returned.
            timing_logger.warning("coaching_input_safety request=%s persistence=failed", request_id)
        response.processing_seconds = round(time.perf_counter() - triage_started, 3)
        return response
    started = time.perf_counter()
    context = []
    if payload.conversation_id is not None:
        try:
            with timed_stage(request_id, "conversation_context"):
                conversation = await run_in_threadpool(
                    data_service.get_conversation, user["uid"], payload.conversation_id,
                    MAX_CONTEXT_MESSAGES, expected_child_id=payload.child_id,
                )
        except Exception:
            raise HTTPException(status_code=503, detail="Conversation context could not be loaded. Please try again.") from None
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found for the selected child.")
        context = select_conversation_context(conversation["messages"])
    await run_in_threadpool(enforce_usage_limit, usage, user["uid"], "coaching")
    retrieval_query = contextual_retrieval_query(payload.question, context)
    # A direct follow-up keeps the age explicitly stated in its caregiver topic.
    # Current profile age remains the fallback when no subject age was supplied.
    if explicit_age is None and retrieval_query != payload.question:
        context_age = message_age_months(retrieval_query)
        if context_age is not None:
            age_months, completed_months = context_age, int(context_age)
            age_days = round(context_age * 30.4375)
            outside_age_range = False
    vaccination = inspect_vaccination(retrieval_query)
    unresolved_follow_up = is_follow_up(payload.question) and retrieval_query == payload.question
    assessment = professional_assessment_response(payload.question)
    boundary = conversation_boundary_response(payload.question, unresolved_follow_up=unresolved_follow_up,
                                              child_age_months=age_months, outside_age_range=outside_age_range)
    stage = "Qdrant retrieval"
    reference_status = "no_match"
    try:
        with timed_stage(request_id, "retrieval"):
            # Do not retrieve arbitrary advice for a follow-up with no safe topic.
            if boundary is not None or vaccination is not None or assessment is not None:
                passages = []
            else:
                try:
                    passages = await run_in_threadpool(
                        retrieval_service.retrieve, retrieval_query, completed_months,
                        payload.routine, 3, child_age_days=age_days,
                    )
                except Exception as exc:
                    # Retrieval supports the answer; an outage must not prevent generation.
                    logger.warning("Reference retrieval unavailable: %s", type(exc).__name__)
                    reference_status = "unavailable"
                    passages = []
        stage = "Evidence selection"
        with timed_stage(request_id, "evidence_selection"):
            evidence = select_evidence(passages, settings.RETRIEVAL_MIN_SCORE)
        timing_logger.info(
            "coach_timing request=%s passages=%d evidence=%d evidence_characters=%d",
            request_id, len(passages), len(evidence), sum(len(item.text) for item in evidence),
        )
        if evidence:
            reference_status = "matched"
        status = "no_evidence"
        response_kind = None
        if boundary is not None:
            response_kind = boundary.kind
            result = CoachingResult(answer=boundary.answer, passages=[])
            vaccination = None
        elif vaccination is not None:
            status = "vaccination_notice"
            result = CoachingResult(answer=vaccination.answer, passages=[])
        elif assessment is not None:
            response_kind = assessment.kind
            result = CoachingResult(answer=assessment.answer, passages=[])
        else:
            status = "answered"
            stage = "Gemini generation"
            with timed_stage(request_id, "generation"):
                context_options = {"conversation_context": context} if context else {}
                result = await run_in_threadpool(
                    coaching_service.generate, payload.question, age_months,
                    payload.routine, evidence, **context_options,
                )
            stage = "Response safety"
            with timed_stage(request_id, "response_safety"):
                decision = (SafetyDecision(True, ("provider_content_block",)) if result.blocked else
                            inspect_response(result.answer, result.passages, evidence, age_months))
                timing_logger.info(
                    "coaching_safety request=%s outcome=%s reasons=%s",
                    request_id, "blocked" if decision.blocked else "passed",
                    ",".join(decision.reasons) or "none",
                )
                if decision.blocked:
                    # Replace before storage and delivery; never save the blocked text.
                    status = "safety_blocked"
                    result = CoachingResult(answer=PROVIDER_BLOCK_MESSAGE if result.blocked else SAFE_RESPONSE, passages=[])
    except ValueError:
        raise HTTPException(status_code=503, detail="Guidance could not be prepared. Please try again.") from None
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
        # Provider descriptions may echo partial, escaped or reformatted personal
        # information. Log bounded metadata rather than trying to redact text.
        code = getattr(exc, "code", None)
        logger.error("%s failed: %s (request=%s, code=%s)", stage, type(exc).__name__,
                     request_id, code if type(code) is int else None)
        raise HTTPException(status_code=502, detail="Guidance generation is unavailable. Please try again.") from None

    citations = [
        {"passage_id": item.passage_id, "source_title": item.source_title, "pdf_page": item.pdf_page,
         "source_url": item.source_url, "title": item.title}
        for item in result.passages
    ]
    if vaccination is not None and vaccination.source_url:
        citations.append({
            "passage_id": "vaccination-" + vaccination.reason,
            "source_title": vaccination.source_title, "pdf_page": None,
            "source_url": vaccination.source_url, "title": "General vaccination education",
        })
    response = CoachingResponse(
        interaction_id=None, answer=result.answer,
        response_kind=response_kind,
        answer_basis=result.answer_basis if status == "answered" else None,
        reference_status=reference_status if status == "answered" else None,
        citations=[CitationSchema(**citation) for citation in citations],
        child_age_months=age_months,
        processing_seconds=round(time.perf_counter() - started, 3), status=status,
        vaccination_country=payload.vaccination_country if vaccination is not None else None,
    )
    try:
        with timed_stage(request_id, "interaction_save"):
            await save_coaching_response(data_service, user["uid"], payload, response)
    except ValueError:
        raise HTTPException(status_code=404, detail="Conversation not found for the selected child.") from None
    except Exception:
        raise HTTPException(status_code=503, detail="Guidance could not be saved. Please try again.") from None
    timing_logger.info(
        "coach_timing request=%s stage=reported_total event=completed seconds=%.3f",
        request_id, time.perf_counter() - started,
    )
    response.processing_seconds = round(time.perf_counter() - started, 3)
    return response


@router.post("/{interaction_id}/feedback", response_model=FeedbackResponse, dependencies=[Depends(require_processing_consent)])
async def feedback(
    interaction_id: Annotated[str, Path(min_length=1, max_length=128, pattern=r"^[^/]+$")],
    payload: FeedbackRequest,
    user: dict = Depends(require_authenticated_user),
    data_service: CaregiverDataService = Depends(get_caregiver_data_service),
) -> FeedbackResponse:
    extra = {"rating": payload.rating, "reasons": payload.reasons} if payload.rating is not None or payload.reasons else {}
    if payload.conversation_id is not None:
        recorded_at = await run_in_threadpool(
            data_service.save_message_feedback, user["uid"], payload.conversation_id,
            interaction_id, payload.helpful, payload.comment,
            **extra,
        )
    else:
        recorded_at = await run_in_threadpool(data_service.save_feedback, user["uid"], interaction_id, payload.helpful, payload.comment, **extra)
    if recorded_at is None:
        raise HTTPException(status_code=404, detail="Interaction not found.")
    return FeedbackResponse(
        interaction_id=interaction_id if payload.conversation_id is None else None,
        conversation_id=payload.conversation_id,
        message_id=interaction_id if payload.conversation_id is not None else None,
        helpful=payload.helpful, recorded_at=recorded_at,
        rating=payload.rating, reasons=payload.reasons,
    )
