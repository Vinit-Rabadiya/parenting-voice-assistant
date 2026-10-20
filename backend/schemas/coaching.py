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


class CoachingResponse(BaseModel):
    interaction_id: str | None
    answer: str
    citations: list[CitationSchema]
    child_age_months: float
    processing_seconds: float
    status: Literal["answered", "no_evidence", "safety_blocked", "escalated"] = "answered"
    safety: Literal["not_flagged", "escalate"] = "not_flagged"


class FeedbackRequest(BaseModel):
    helpful: bool
    comment: str | None = Field(default=None, max_length=500)


class FeedbackResponse(BaseModel):
    interaction_id: str
    helpful: bool
    recorded_at: datetime
