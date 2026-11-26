"""Administrator feedback and application usage reports."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response

from backend.api.dependencies import get_caregiver_data_service
from backend.core.security import require_authenticated_user, require_feedback_summary_admin
from backend.schemas.admin import FeedbackSummary, TokenUsageSummary
from backend.services.caregiver_data import CaregiverDataService
from backend.services.feedback_summary import FeedbackSummaryService
from backend.schemas.feedback_improvements import ImprovementCreate, ImprovementUpdate, ImprovementRecord, ImprovementPage
from backend.services.feedback_improvements import (
    FeedbackImprovementService, ImprovementConflict, ImprovementNotFound, ImprovementStageError,
)

router = APIRouter(prefix="/admin")
CaseId = Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")]


def improvement_operation(operation):
    try:
        return operation()
    except ImprovementNotFound:
        raise HTTPException(status_code=404, detail="Improvement case not found.") from None
    except ImprovementConflict:
        raise HTTPException(status_code=409, detail="This case changed. Refresh before saving again.") from None
    except ImprovementStageError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except Exception:
        raise HTTPException(status_code=503, detail="Improvement cases are unavailable. Please retry.") from None


@router.get("/feedback/improvements", response_model=ImprovementPage)
def list_improvements(request: Request, response: Response,
                      limit: int = Query(default=20, ge=1, le=50),
                      before: str | None = Query(default=None, pattern=r"^[0-9a-f]{32}$"),
                      user: dict = Depends(require_feedback_summary_admin),
                      service: CaregiverDataService = Depends(get_caregiver_data_service)):
    response.headers["Cache-Control"] = "no-store"
    if set(request.query_params) - {"limit", "before"}:
        raise HTTPException(status_code=422, detail="Improvement case filters are not supported.")
    return improvement_operation(lambda: FeedbackImprovementService(service.client).list(user["uid"], limit, before))


@router.post("/feedback/improvements", response_model=ImprovementRecord, status_code=201)
def create_improvement(payload: ImprovementCreate, response: Response,
                       user: dict = Depends(require_feedback_summary_admin),
                       service: CaregiverDataService = Depends(get_caregiver_data_service)):
    response.headers["Cache-Control"] = "no-store"
    return improvement_operation(lambda: FeedbackImprovementService(service.client).create(user["uid"], payload.content))


@router.put("/feedback/improvements/{identifier}", response_model=ImprovementRecord)
def update_improvement(identifier: CaseId, payload: ImprovementUpdate, response: Response,
                       user: dict = Depends(require_feedback_summary_admin),
                       service: CaregiverDataService = Depends(get_caregiver_data_service)):
    response.headers["Cache-Control"] = "no-store"
    return improvement_operation(lambda: FeedbackImprovementService(service.client).update(
        user["uid"], identifier, payload.expected_version, payload.content,
    ))


@router.delete("/feedback/improvements/{identifier}", status_code=204)
def delete_improvement(identifier: CaseId, response: Response,
                       expected_version: int = Query(ge=1),
                       user: dict = Depends(require_feedback_summary_admin),
                       service: CaregiverDataService = Depends(get_caregiver_data_service)):
    response.headers["Cache-Control"] = "no-store"
    improvement_operation(lambda: FeedbackImprovementService(service.client).delete(user["uid"], identifier, expected_version))


@router.get("/feedback/access")
def feedback_access(request: Request, response: Response,
                    user: dict = Depends(require_authenticated_user)):
    response.headers["Cache-Control"] = "no-store"
    return {"allowed": getattr(request.state, "feedback_summary_admin", False) is True}


@router.get("/feedback/summary", response_model=FeedbackSummary)
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


@router.get("/token-usage", response_model=TokenUsageSummary, dependencies=[Depends(require_feedback_summary_admin)])
def token_usage(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    if request.query_params:
        raise HTTPException(status_code=422, detail="Token usage filters are not supported.")
    try:
        return request.app.state.token_usage_service.summary()
    except Exception:
        raise HTTPException(status_code=503, detail="Token usage is unavailable. Please try again.") from None
