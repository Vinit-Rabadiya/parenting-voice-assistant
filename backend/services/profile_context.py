"""Select bounded profile observations for replies without profile identifiers."""

from pydantic import BaseModel, ConfigDict, Field

from backend.core.config import settings
from backend.schemas.children import ChildHealthDetails, MilestoneText


class ReplyProfileContext(BaseModel):
    model_config = ConfigDict(extra="ignore")
    milestones: list[MilestoneText] = Field(default_factory=list, max_length=20)
    health_details: ChildHealthDetails = Field(default_factory=ChildHealthDetails)


def health_context_available() -> bool:
    # Non-personal test notes use the same context path without changing billing.
    return settings.provider_data_allowed


def validate_reply_context(context: dict, *, provider: str | None = None) -> dict:
    """Recheck the provider gate immediately before constructing a model prompt."""
    values = {"milestones": context.get("milestones", [])}
    if settings.data_allowed_for(provider or settings.COACHING_PROVIDER):
        values["health_details"] = context.get("health_details") or {}
    return ReplyProfileContext.model_validate(values).model_dump(exclude_defaults=True)


def child_reply_context(child: dict) -> dict:
    values = {"milestones": child.get("milestones") or (
        [child["milestone_focus"]] if child.get("milestone_focus") else []
    )}
    if child.get("use_health_details") is True and health_context_available():
        values["health_details"] = child.get("health_details") or {}
    return validate_reply_context(values)
