from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(default="ok", description="Server health status")


class UserResponse(BaseModel):
    uid: str = Field(description="Unique Firebase User ID")
