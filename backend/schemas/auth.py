# this file defines the expected data blueprints for api response bodies using pydantic.
# it is imported in backend/api/v1/endpoints/ for automatic response formatting and checks.
from pydantic import BaseModel, Field
from typing import Literal
from backend.schemas.children import ChildProfileResponse
from backend.schemas.privacy import ConsentResponse


class HealthResponse(BaseModel):
    status: str = Field(default="ok", description="Server health status")


class UserResponse(BaseModel):
    uid: str = Field(description="Unique Firebase User ID")
    role: Literal["caregiver", "administrator"] = "caregiver"


class AccountSecurityResponse(BaseModel):
    mfa_enabled: bool
    mfa_required: bool


class StartupResponse(UserResponse):
    consent: ConsentResponse | None = None
    children: list[ChildProfileResponse] | None = None
