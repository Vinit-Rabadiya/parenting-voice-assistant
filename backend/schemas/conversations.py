"""Contracts for account-scoped conversation history."""

from datetime import datetime

from pydantic import BaseModel, Field

from backend.schemas.coaching import CitationSchema, SupportResource


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


class ConversationDetailResponse(ConversationResponse):
    messages: list[ConversationMessageResponse] = Field(default_factory=list)
