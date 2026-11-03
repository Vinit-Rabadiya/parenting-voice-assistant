"""Read the processing notice and record explicit authenticated acceptance."""
from fastapi import APIRouter, Depends, HTTPException

from backend.api.dependencies import get_caregiver_data_service
from backend.core.privacy import CONSENT_VERSION, PRIVACY_NOTICE
from backend.core.security import require_authenticated_user
from backend.schemas.privacy import ConsentRequest, ConsentResponse
from backend.services.caregiver_data import CaregiverDataService

router = APIRouter(prefix="/privacy/consent")


def consent_response(data: dict) -> ConsentResponse:
    accepted = (data.get("consent_version") == CONSENT_VERSION and data.get("consent_at") is not None
                and data.get("caregiver_authority") is True)
    return ConsentResponse(version=CONSENT_VERSION, accepted=accepted,
                           accepted_at=data.get("consent_at") if accepted else None, notice=PRIVACY_NOTICE)


@router.get("", response_model=ConsentResponse)
def get_consent(user: dict = Depends(require_authenticated_user),
                service: CaregiverDataService = Depends(get_caregiver_data_service)):
    try:
        data = service.get_consent(user["uid"])
    except Exception:
        raise HTTPException(status_code=503, detail="Privacy consent could not be loaded. Please retry.") from None
    return consent_response(data)


@router.post("", response_model=ConsentResponse)
def accept_consent(payload: ConsentRequest, user: dict = Depends(require_authenticated_user),
                   service: CaregiverDataService = Depends(get_caregiver_data_service)):
    if payload.version != CONSENT_VERSION:
        raise HTTPException(status_code=409, detail="The privacy notice changed. Reload it before accepting.")
    if not payload.accepted or not payload.caregiver_authority:
        raise HTTPException(status_code=422, detail="Explicit acceptance and caregiver authority are required.")
    try:
        accepted_at = service.save_consent(user["uid"], CONSENT_VERSION)
    except Exception:
        raise HTTPException(status_code=503, detail="Consent could not be saved. Please retry.") from None
    return ConsentResponse(version=CONSENT_VERSION, accepted=True, accepted_at=accepted_at, notice=PRIVACY_NOTICE)
