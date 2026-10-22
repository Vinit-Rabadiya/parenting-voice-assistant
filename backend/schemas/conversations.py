"""Contracts for account-scoped conversation history."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from backend.schemas.coaching import CitationSchema, FeedbackRecord, SupportResource


class ConversationCreateRequest(BaseModel):
    child_id: str = Field(min_length=1, max_length=128, pattern=r"^[^/]+$")


class ConversationResponse(BaseModel):
    id: str
    child_id: str
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationMessageResponse(BaseModel):
    id: str
    role: str = Field(pattern=r"^(user|assistant)$")
    text: str
    created_at: datetime
    citations: list[CitationSchema] = Field(default_factory=list)
    support_resources: list[SupportResource] = Field(default_factory=list)
    status: str | None = None
    routine: str | None = None
    vaccination_country: Literal["KE", "OTHER"] | None = None
    child_age_months: float | None = None
    processing_seconds: float | None = None
    safety: str | None = None
    feedback: FeedbackRecord | None = None


class ConversationDetailResponse(ConversationResponse):
    messages: list[ConversationMessageResponse] = Field(default_factory=list)
