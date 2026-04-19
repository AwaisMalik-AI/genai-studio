from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PromptTemplateCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    category: str
    template_text: str = Field(min_length=1)
    variables: dict[str, Any] = Field(default_factory=dict)
    system_prompt: str | None = None
    model_config_json: dict[str, Any] = Field(default_factory=dict, alias="model_config")
    is_active: bool = True


class PromptTemplateUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str | None = None
    description: str | None = None
    category: str | None = None
    template_text: str | None = None
    variables: dict[str, Any] | None = None
    system_prompt: str | None = None
    model_config_json: dict[str, Any] | None = Field(default=None, alias="model_config")
    is_active: bool | None = None


class PromptTemplateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    name: str
    description: str | None
    category: str
    template_text: str
    variables: dict[str, Any]
    system_prompt: str | None
    llm_model_config: dict[str, Any] = Field(
        validation_alias="model_config_json",
        serialization_alias="model_config",
    )
    version: int
    parent_version_id: int | None
    performance_score: float | None
    usage_count: int
    is_active: bool
    created_by_id: int
    created_at: datetime


class RenderTemplateRequest(BaseModel):
    variables: dict[str, Any] = Field(default_factory=dict)


class RenderTemplateResponse(BaseModel):
    rendered_user_prompt: str
    system_prompt: str | None
    effective_model_config: dict[str, Any]


class VersionPromptRequest(BaseModel):
    new_template_text: str
    description: str | None = None
    bump_message: str | None = None


class TemplatePerformanceRead(BaseModel):
    template_id: int
    version: int
    usage_count: int
    performance_score: float | None
    avg_feedback_rating: float | None
    total_jobs: int
