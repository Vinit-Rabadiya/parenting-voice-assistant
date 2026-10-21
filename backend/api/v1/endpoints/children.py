"""Authenticated child-profile routes."""

from fastapi import APIRouter, Depends, HTTPException

from backend.api.dependencies import get_caregiver_data_service
from backend.core.security import require_authenticated_user
from backend.api.consent import require_processing_consent
from backend.schemas.children import ChildCreateRequest, ChildProfileResponse, ChildUpdateRequest
from backend.services.caregiver_data import CaregiverDataService


router = APIRouter(prefix="/children", dependencies=[Depends(require_authenticated_user)])


@router.delete("/{child_id}", status_code=204)
def delete_child(child_id: str, user: dict = Depends(require_authenticated_user), service: CaregiverDataService = Depends(get_caregiver_data_service)):
    try:
        deleted = service.delete_child(user["uid"], child_id)
    except Exception:
        raise HTTPException(status_code=503, detail="Profile deletion could not finish. Please retry. Some related interactions may already have been removed.") from None
    if not deleted:
        raise HTTPException(status_code=404, detail="Child profile not found.")


@router.get("", response_model=list[ChildProfileResponse])
def list_children(user: dict = Depends(require_authenticated_user), service: CaregiverDataService = Depends(get_caregiver_data_service)):
    return service.list_children(user["uid"])


@router.post("", response_model=ChildProfileResponse, status_code=201, dependencies=[Depends(require_processing_consent)])
def create_child(payload: ChildCreateRequest, user: dict = Depends(require_authenticated_user), service: CaregiverDataService = Depends(get_caregiver_data_service)):
    try:
        return service.create_child(user["uid"], payload.name, payload.date_of_birth, payload.milestone_focus, payload.milestones)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/{child_id}", response_model=ChildProfileResponse, dependencies=[Depends(require_processing_consent)])
def update_child(child_id: str, payload: ChildUpdateRequest, user: dict = Depends(require_authenticated_user), service: CaregiverDataService = Depends(get_caregiver_data_service)):
    try:
        child = service.update_child(user["uid"], child_id, payload.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if child is None:
        raise HTTPException(status_code=404, detail="Child profile not found.")
    return child
