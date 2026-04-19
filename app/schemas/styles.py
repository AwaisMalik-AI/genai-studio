from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class StylePresetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    category: str
    config: dict[str, Any] = Field(default_factory=dict)
    example_output: str | None = None
    is_public: bool = True


class StylePresetUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    category: str | None = None
    config: dict[str, Any] | None = None
    example_output: str | None = None
    is_public: bool | None = None


class StylePresetRead(BaseModel):
    id: UUID
    name: str
    description: str | None
    category: str
    config: dict[str, Any]
    example_output: str | None
    is_public: bool
    created_by: UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class StylePreviewRequest(BaseModel):
    base_prompt: str = Field(min_length=1)
