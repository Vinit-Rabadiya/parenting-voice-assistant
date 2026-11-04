"""Request-local batched reads for coaching; no cross-request family-data cache."""
from fastapi import Depends, HTTPException, Request

from backend.api.consent import verify_processing_consent
from backend.api.dependencies import get_caregiver_data_service
from backend.core.http_security import timed_request_stage
from backend.core.security import require_caregiver_user
from backend.schemas.coaching import CoachingRequest
from backend.services.caregiver_data import CaregiverDataService


def prepare_coaching_documents(request: Request, payload: CoachingRequest,
                               user: dict = Depends(require_caregiver_user),
                               service: CaregiverDataService = Depends(get_caregiver_data_service)) -> None:
    try:
        with timed_request_stage(request, "coaching_documents"):
            documents = service.get_coaching_documents(
                user["uid"], payload.child_id,
                payload.conversation_id if not payload.start_conversation else None,
            )
    except Exception:
        raise HTTPException(status_code=503, detail="Guidance data could not be loaded. Please retry.") from None
    # Do not interpret the profile or read any messages until current consent passes.
    verify_processing_consent(documents["consent"])
    request.state.coaching_documents = documents
