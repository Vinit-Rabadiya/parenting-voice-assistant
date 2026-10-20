"""API models for grounded caregiver coaching and feedback."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CitationSchema(BaseModel):
    passage_id: str
    source_title: str
    pdf_page: int | None
    source_url: str
    title: str


class CoachingRequest(BaseModel):
    child_id: str = Field(min_length=1, max_length=128)
    question: str = Field(min_length=2, max_length=1200)
    routine: str | None = Field(default=None, max_length=40)
    support_country: Literal["KE"] | None = None


class SupportResource(BaseModel):
    label: str
    url: str
    service: str
    country: Literal["KE"]
    availability: str
    source_url: str
    verified_on: str


class CoachingResponse(BaseModel):
    interaction_id: str | None
    answer: str
    citations: list[CitationSchema]
    child_age_months: float
    processing_seconds: float
    status: Literal["answered", "no_evidence", "safety_blocked", "escalated", "crisis_support", "caregiver_support"] = "answered"
    safety: Literal["not_flagged", "escalate"] = "not_flagged"
    support_resources: list[SupportResource] = Field(default_factory=list)


class FeedbackRequest(BaseModel):
    helpful: bool
    comment: str | None = Field(default=None, max_length=500)


class FeedbackResponse(BaseModel):
    interaction_id: str
    helpful: bool
    recorded_at: datetime
