"""API models for grounded caregiver coaching and feedback."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class CitationSchema(BaseModel):
    passage_id: str
    source_title: str
    pdf_page: int | None
    source_url: str
    title: str


class CoachingRequest(BaseModel):
    child_id: str = Field(min_length=1, max_length=128, pattern=r"^[^/]+$")
    conversation_id: str | None = Field(default=None, min_length=1, max_length=128, pattern=r"^[^/]+$")
    question: str = Field(min_length=2, max_length=1200)
    routine: str | None = Field(default=None, max_length=40)
    support_country: Literal["KE"] | None = None
    vaccination_country: Literal["KE"] = "KE"
    start_conversation: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def require_new_conversation_id(self):
        if self.start_conversation:
            from uuid import UUID
            if self.conversation_id is None:
                raise ValueError("A new conversation needs an ID.")
            try:
                identifier = UUID(self.conversation_id)
            except ValueError:
                raise ValueError("A new conversation needs a UUID.") from None
            if identifier.version != 4 or str(identifier) != self.conversation_id:
                raise ValueError("A new conversation needs a canonical UUID v4.")
        return self

    @field_validator("question", mode="before")
    @classmethod
    def trim_question(cls, value):
        return value.strip() if isinstance(value, str) else value


class SupportResource(BaseModel):
    label: str
    url: str
    service: str
    category: Literal["emergency", "ambulance", "hospital", "support"] = "support"
    location: str | None = None
    country: Literal["KE"]
    availability: str
    source_url: str
    verified_on: str


class CoachingResponse(BaseModel):
    interaction_id: str | None
    conversation_id: str | None = None
    message_id: str | None = None
    answer: str
    response_kind: Literal["clarification", "unrelated", "professional_referral", "insufficient_references", "age_out_of_scope"] | None = None
    answer_basis: Literal["reference_assisted", "general_information"] | None = None
    reference_status: Literal["matched", "no_match", "unavailable"] | None = None
    citations: list[CitationSchema]
    child_age_months: float
    subject_age_override: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    health_context_used: bool = False
    health_context_revision: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    caregiver_request: str | None = Field(default=None, max_length=1200)
    clarification_field: Literal["age"] | None = None
    processing_seconds: float
    status: Literal["answered", "no_evidence", "safety_blocked", "escalated", "crisis_support", "caregiver_support", "vaccination_notice"] = "answered"
    vaccination_country: Literal["KE"] | None = None
    safety: Literal["not_flagged", "escalate"] = "not_flagged"
    support_resources: list[SupportResource] = Field(default_factory=list)


class FeedbackValues(BaseModel):
    helpful: bool | None = None
    rating: int | None = Field(default=None, strict=True, ge=1, le=5)
    reasons: list[Literal["unclear", "repeated_advice", "did_not_answer", "not_age_appropriate"]] = Field(default_factory=list, max_length=4)
    comment: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def require_feedback_value(self):
        if self.helpful is None and self.rating is None:
            raise ValueError("Provide a helpfulness rating or Helpful/Not helpful feedback.")
        if len(self.reasons) != len(set(self.reasons)):
            raise ValueError("Feedback reasons must be unique.")
        return self


class FeedbackRequest(FeedbackValues):
    conversation_id: str | None = Field(default=None, min_length=1, max_length=128, pattern=r"^[^/]+$")


class FeedbackRecord(FeedbackValues):
    recorded_at: datetime


class FeedbackResponse(BaseModel):
    interaction_id: str | None
    conversation_id: str | None = None
    message_id: str | None = None
    helpful: bool | None = None
    rating: int | None = None
    reasons: list[str] = Field(default_factory=list)
    recorded_at: datetime
