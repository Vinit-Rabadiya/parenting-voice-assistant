# this file handles the /health/live and /health/ready endpoints to check whether the backend is running.
# it is included in backend/api/v1/router.py and called by monitoring or test scripts.
from fastapi import APIRouter, Request
from backend.schemas.auth import HealthResponse

router = APIRouter()


@router.get("/health/live", response_model=HealthResponse, summary="Liveness Health Check")
def health_live():
    """Verify that the backend server is up and responsive."""
    return HealthResponse(status="ok")


@router.get("/health/ready", response_model=HealthResponse, summary="Readiness Health Check")
def health_ready(request: Request):
    """Report readiness and optional reference availability without remote probes.

    Reference search is optional: local sources and other app features still work
    during an outage, so degraded references do not remove this replica from service.
    """
    service = getattr(request.app.state, "retrieval_service", None)
    qdrant_ready = getattr(service, "readiness", None)
    if qdrant_ready is False:
        return HealthResponse(status="degraded")
    return HealthResponse(status="ok")
