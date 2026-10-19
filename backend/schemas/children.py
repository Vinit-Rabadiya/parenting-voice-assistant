"""Request and response models for a caregiver's child profiles."""

from datetime import date, datetime

from pydantic import BaseModel, Field, StringConstraints
from typing import Annotated

MilestoneText = Annotated[str, StringConstraints(min_length=1, max_length=120, strip_whitespace=True)]


class ChildCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    date_of_birth: date
    milestone_focus: str | None = Field(default=None, max_length=120)
    milestones: list[MilestoneText] = Field(default_factory=list, max_length=20)


class ChildUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    date_of_birth: date | None = None
    milestone_focus: str | None = Field(default=None, max_length=120)
    milestones: list[MilestoneText] | None = Field(default=None, max_length=20)


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
    created_at: datetime | None = None
