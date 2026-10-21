"""Require current recorded consent before starting new personal-data processing."""
from fastapi import Depends, HTTPException

from backend.api.dependencies import get_caregiver_data_service
from backend.core.privacy import CONSENT_VERSION
from backend.core.security import require_authenticated_user
from backend.services.caregiver_data import CaregiverDataService


def require_processing_consent(
    user: dict = Depends(require_authenticated_user),
    service: CaregiverDataService = Depends(get_caregiver_data_service),
) -> None:
    try:
        consent = service.get_consent(user["uid"])
    except Exception:
        raise HTTPException(status_code=503, detail="Privacy consent could not be checked. Please retry.") from None
    if (consent.get("consent_version") != CONSENT_VERSION or consent.get("consent_at") is None
            or consent.get("caregiver_authority") is not True):
        raise HTTPException(status_code=403, detail="Review and accept the current privacy notice before continuing.")
