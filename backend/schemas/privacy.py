"""Consent input never accepts a client-supplied account ID or timestamp."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, StrictBool


class ConsentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str
    accepted: StrictBool
    caregiver_authority: StrictBool


class ConsentResponse(BaseModel):
    version: str
    accepted: bool
    accepted_at: datetime | None = None
    notice: list[str]
