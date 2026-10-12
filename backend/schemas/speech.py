# defines the result built by the speech service and serialized by the speech endpoint.
from pydantic import BaseModel, Field

class TranscriptionResponse(BaseModel):
    # field bounds validate durations; processing time is not the full browser request time.
    text: str = Field(description="recognized words")
    audio_seconds: float = Field(gt=0, le=30, description="duration of the submitted recording")
    processing_seconds: float = Field(ge=0, description="time spent processing the recording")

