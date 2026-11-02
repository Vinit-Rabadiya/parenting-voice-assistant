"""Request and response models for a caregiver's child profiles."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StringConstraints
from typing import Annotated

MilestoneText = Annotated[str, StringConstraints(min_length=1, max_length=120, strip_whitespace=True)]
HealthNote = Annotated[str, StringConstraints(max_length=600, strip_whitespace=True)]


class ChildHealthDetails(BaseModel):
    """Optional caregiver notes, not verified clinical records or uploaded reports."""

    model_config = ConfigDict(extra="forbid")
    allergies: HealthNote = ""
    conditions: HealthNote = ""
    history: HealthNote = ""
    care_instructions: HealthNote = ""
    test_result_notes: HealthNote = ""


class ChildCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    date_of_birth: date
    milestone_focus: str | None = Field(default=None, max_length=120)
    milestones: list[MilestoneText] = Field(default_factory=list, max_length=20)
    health_details: ChildHealthDetails = Field(default_factory=ChildHealthDetails)
    use_health_details: StrictBool = False


class ChildUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    date_of_birth: date | None = None
    milestone_focus: str | None = Field(default=None, max_length=120)
    milestones: list[MilestoneText] | None = Field(default=None, max_length=20)
    health_details: ChildHealthDetails | None = None
    use_health_details: StrictBool | None = None


class ChildProfileResponse(BaseModel):
    id: str
    name: str
    date_of_birth: date
    age_months: float
    age_days: int
    completed_months: int
    in_scope: bool
    age_label: str
    milestone_focus: str | None = None
    baseline_milestones: list[str]
    milestones: list[str] = Field(default_factory=list)
    health_details: ChildHealthDetails = Field(default_factory=ChildHealthDetails)
    use_health_details: bool = False
    health_context_available: bool = False
    created_at: datetime | None = None
