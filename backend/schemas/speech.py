from pydantic import BaseModel, Field

class TranscriptionResponse(BaseModel):
    text: str = Field(description="recognized words")
    audio_seconds: float = Field(gt=0, le=30, description="duration of the submitted recording")
    processing_seconds: float = Field(ge=0, description="time spent processing the recording")

