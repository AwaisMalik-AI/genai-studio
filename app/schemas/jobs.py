from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class JobListFilters(BaseModel):
    status: str | None = None
    job_type: str | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class GenerationJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_type: Any
    prompt_template_id: int | None
    prompt_text: str
    model_used: str
    input_variables: dict[str, Any] | None
    status: Any
    output_text: str | None
    output_image_path: str | None
    output_metadata: dict[str, Any] | None
    tokens_used: int | None
    generation_time_ms: int | None
    cost_estimate: float | None
    moderation_result: dict[str, Any] | None
    feedback_rating: int | None
    error_message: str | None
    created_by_id: int
    created_at: datetime
    completed_at: datetime | None
