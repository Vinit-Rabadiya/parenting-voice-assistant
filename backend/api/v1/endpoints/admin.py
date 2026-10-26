"""Administrator access to feedback without conversation or profile lookup."""
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from backend.api.dependencies import get_caregiver_data_service
from backend.core.security import require_authenticated_user, require_feedback_summary_admin
from backend.schemas.admin import FeedbackSummary
from backend.services.caregiver_data import CaregiverDataService
from backend.services.feedback_summary import FeedbackSummaryService

router = APIRouter(prefix="/admin/feedback")


@router.get("/access")
def feedback_access(request: Request, response: Response,
                    user: dict = Depends(require_authenticated_user)):
    response.headers["Cache-Control"] = "no-store"
    return {"allowed": getattr(request.state, "feedback_summary_admin", False) is True}


@router.get("/summary", response_model=FeedbackSummary)
def feedback_summary(request: Request, response: Response,
                     user: dict = Depends(require_feedback_summary_admin),
                     service: CaregiverDataService = Depends(get_caregiver_data_service)):
    response.headers["Cache-Control"] = "no-store"
    # No account, child, date or category filters or individual-record drill-down.
    if request.query_params:
        raise HTTPException(status_code=422, detail="Feedback summary filters are not supported.")
    try:
        return FeedbackSummaryService(service.client).read()
    except Exception:
        raise HTTPException(status_code=503, detail="Feedback summary is unavailable. Please try again.") from None
