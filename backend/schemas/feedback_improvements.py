"""Administrator-authored fictional review cases, separate from caregiver feedback."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from backend.services.age import within_project_scope


class ReviewScores(BaseModel):
    model_config = ConfigDict(extra="forbid")
    faithfulness: int | None = Field(default=None, strict=True, ge=1, le=5)
    helpfulness: int | None = Field(default=None, strict=True, ge=1, le=5)
    age_fit: int | None = Field(default=None, strict=True, ge=1, le=5)
    clarity: int | None = Field(default=None, strict=True, ge=1, le=5)
    safety: int | None = Field(default=None, strict=True, ge=1, le=5)


class AnswerReview(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    answer: str = Field(default="", max_length=6000)
    model: str = Field(default="", max_length=120)
    prompt_revision: str = Field(default="", max_length=160)
    corpus_revision: str = Field(default="", max_length=160)
    report_reference: str = Field(default="", max_length=300)
    scores: ReviewScores = Field(default_factory=ReviewScores)
    faithfulness_not_applicable: StrictBool = False
    faithfulness_note: str = Field(default="", max_length=500)

    @property
    def complete(self):
        source_assessed = (self.scores.faithfulness is None and bool(self.faithfulness_note)
                           if self.faithfulness_not_applicable else self.scores.faithfulness is not None)
        return (all((self.answer, self.model, self.prompt_revision, self.corpus_revision, self.report_reference))
                and source_assessed and all(value is not None for key, value in self.scores.model_dump().items()
                                            if key != "faithfulness"))


class ImprovementChecks(BaseModel):
    model_config = ConfigDict(extra="forbid")
    issue_resolved: StrictBool = False
    sources_checked: StrictBool = False
    age_checked: StrictBool = False
    safety_checked: StrictBool = False
    regressions_passed: StrictBool = False


class ImprovementContent(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=3, max_length=120)
    category: Literal["unclear", "repeated_advice", "did_not_answer", "not_age_appropriate", "other"]
    scenario: str = Field(min_length=3, max_length=1200)
    expected_behavior: str = Field(min_length=3, max_length=1200)
    fictional_date_of_birth: date
    evaluation_date: date
    fictional_confirmed: StrictBool
    status: Literal["investigating", "ready_for_release", "released"] = "investigating"
    change_area: Literal["prompt", "references", "retrieval", "guardrails"] = "prompt"
    change_summary: str = Field(default="", max_length=1200)
    change_reference: str = Field(default="", max_length=300)
    baseline: AnswerReview = Field(default_factory=AnswerReview)
    candidate: AnswerReview = Field(default_factory=AnswerReview)
    checks: ImprovementChecks = Field(default_factory=ImprovementChecks)
    evaluation_notes: str = Field(default="", max_length=2000)
    release_revision: str = Field(default="", pattern=r"^(?:[0-9a-f]{40})?$")
    deployment_checked: StrictBool = False
    release_notes: str = Field(default="", max_length=1200)

    @model_validator(mode="after")
    def validate_review_stage(self):
        if not self.fictional_confirmed:
            raise ValueError("Confirm that the case contains no caregiver identifiers or private chat text.")
        if not within_project_scope(self.fictional_date_of_birth, self.evaluation_date):
            raise ValueError("The child's age on the evaluation date must be between birth and the second birthday, inclusive.")
        if self.status != "investigating":
            if not (self.baseline.complete and self.candidate.complete and self.change_summary
                    and self.change_reference and self.evaluation_notes):
                raise ValueError("Record both reviewed answers, their provenance, the correction and evaluation notes.")
            if not all(self.checks.model_dump().values()):
                raise ValueError("Record all review and regression checks before advancing.")
            if any(after is not None and before is not None and after < before for after, before in (
                (getattr(self.candidate.scores, field), getattr(self.baseline.scores, field))
                for field in ("faithfulness", "age_fit", "safety")
            )):
                raise ValueError("Resolve source, age or safety score regressions before advancing.")
            if any(value is not None and value < 4 for value in (
                self.candidate.scores.faithfulness, self.candidate.scores.age_fit, self.candidate.scores.safety,
            )):
                raise ValueError("Candidate source, age and safety review scores must be at least four when applicable.")
        if self.status == "released" and not (self.release_revision and self.deployment_checked and self.release_notes):
            raise ValueError("Record the full deployed commit, deployment check and release notes.")
        return self


class ImprovementCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: ImprovementContent


class ImprovementUpdate(ImprovementCreate):
    expected_version: int = Field(strict=True, ge=1)


class ImprovementRecord(ImprovementCreate):
    id: str = Field(pattern=r"^[0-9a-f]{32}$")
    version: int = Field(strict=True, ge=1)
    created_at: datetime
    updated_at: datetime
    released_at: datetime | None = None


class ImprovementPage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[ImprovementRecord] = Field(max_length=50)
    next_cursor: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
