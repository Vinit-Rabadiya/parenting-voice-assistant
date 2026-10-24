"""Allowlisted aggregate response: never individual feedback or conversation data."""
from pydantic import BaseModel, ConfigDict, Field


class FeedbackBucket(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str
    lower: int | None = Field(default=None, ge=5)
    upper: int | None = Field(default=None, ge=9)


class FeedbackSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    unit: str = "Latest consented feedback per caregiver"
    minimum_group_size: int = 5
    ratings: list[FeedbackBucket]
    reasons: list[FeedbackBucket]
    legacy_helpfulness: list[FeedbackBucket]
