"""Administrator feedback responses omit conversation and account identifiers."""
from pydantic import BaseModel, ConfigDict, Field


class FeedbackBucket(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str
    count: int = Field(strict=True, ge=0)


class FeedbackComment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    comment: str = Field(min_length=1, max_length=500)
    rating: int | None = Field(default=None, strict=True, ge=1, le=5)
    helpful: bool | None = None
    reasons: list[str]


class FeedbackSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    unit: str = "Saved feedback per answer"
    ratings: list[FeedbackBucket]
    reasons: list[FeedbackBucket]
    legacy_helpfulness: list[FeedbackBucket]
    comments: list[FeedbackComment] = Field(default_factory=list, max_length=50)
    comment_count: int = Field(default=0, strict=True, ge=0)
