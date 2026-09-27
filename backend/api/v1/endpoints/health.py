from fastapi import APIRouter
from backend.schemas.auth import HealthResponse

router = APIRouter()


@router.get("/health/live", response_model=HealthResponse, summary="Liveness Health Check")
def health_live():
    """Verify that the backend server is up and responsive."""
    return HealthResponse(status="ok")
