"""Read-only account usage response."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class UsageWindow(BaseModel):
    used: int
    limit: int
    remaining: int
    resets_at: datetime


class UsageItem(BaseModel):
    action: Literal["coaching", "child_creation"]
    hourly: UsageWindow
    daily: UsageWindow


class UsageResponse(BaseModel):
    items: list[UsageItem]
    as_of: datetime
