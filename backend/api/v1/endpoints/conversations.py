"""Read and manage the authenticated account's conversations."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from google.api_core.exceptions import FailedPrecondition

from backend.api.dependencies import get_caregiver_data_service
from backend.core.security import require_authenticated_user, require_caregiver_user
from backend.api.consent import require_processing_consent
from backend.schemas.conversations import (
    ConversationCreateRequest,
    ConversationDetailResponse,
    ConversationResponse,
)
from backend.services.caregiver_data import CaregiverDataService


router = APIRouter(prefix="/conversations", dependencies=[Depends(require_caregiver_user)])
DocumentId = Annotated[str, Path(min_length=1, max_length=128, pattern=r"^[^/]+$")]
CursorId = Annotated[str | None, Query(min_length=1, max_length=128, pattern=r"^[^/]+$")]


@router.post("", response_model=ConversationResponse, status_code=201, dependencies=[Depends(require_processing_consent)])
def create_conversation(
    payload: ConversationCreateRequest,
    user: dict = Depends(require_authenticated_user),
    service: CaregiverDataService = Depends(get_caregiver_data_service),
):
    conversation = service.create_conversation(user["uid"], payload.child_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Child profile not found.")
    return conversation


@router.get("", response_model=list[ConversationResponse])
def list_conversations(
    child_id: Annotated[str, Query(min_length=1, max_length=128, pattern=r"^[^/]+$")],
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    before: CursorId = None,
    user: dict = Depends(require_authenticated_user),
    service: CaregiverDataService = Depends(get_caregiver_data_service),
):
    if service.get_child(user["uid"], child_id) is None:
        raise HTTPException(status_code=404, detail="Child profile not found.")
    try:
        return service.list_conversations(user["uid"], child_id, limit, before)
    except FailedPrecondition:
        raise HTTPException(
            status_code=503,
            detail="Conversation history is unavailable. Check that the Firestore conversations index (child_id ascending, updated_at descending) is enabled.",
        ) from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
def get_conversation(
    conversation_id: DocumentId,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    before: CursorId = None,
    user: dict = Depends(require_authenticated_user),
    service: CaregiverDataService = Depends(get_caregiver_data_service),
):
    try:
        conversation = service.get_conversation(user["uid"], conversation_id, limit, before)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return conversation


@router.delete("/{conversation_id}", status_code=204)
def delete_conversation(
    conversation_id: DocumentId,
    user: dict = Depends(require_authenticated_user),
    service: CaregiverDataService = Depends(get_caregiver_data_service),
):
    try:
        deleted = service.delete_conversation(user["uid"], conversation_id)
    except Exception:
        raise HTTPException(status_code=503, detail="Conversation deletion could not finish. Please retry.") from None
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found.")
