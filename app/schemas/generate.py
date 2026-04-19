from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.config import settings


class GenerateTextRequest(BaseModel):
    """Either raw prompt or template_id + variables; optional style and model override."""

    prompt: str | None = None
    template_id: int | None = None
    variables: dict[str, Any] = Field(default_factory=dict)
    style_preset_id: int | None = None
    model_override: str | None = None
    system_prompt: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=128000)
    top_p: float | None = Field(default=None, ge=0, le=1)
    content_type: str | None = Field(
        default=None,
        description="Hint: blog_post, marketing_copy, product_description, email, social",
    )

    @model_validator(mode="after")
    def prompt_or_template(self):
        if not self.prompt and not self.template_id:
            raise ValueError("Provide prompt or template_id")
        return self


class GenerateTextResponse(BaseModel):
    job_id: int
    text: str
    model_used: str
    tokens_used: int | None = None
    cost_estimate: float | None = None
    generation_time_ms: int | None = None
    moderation: dict[str, Any] | None = None


class GenerateImageRequest(BaseModel):
    prompt: str = Field(min_length=1)
    negative_prompt: str | None = None
    size: str = "1024x1024"
    style: str | None = None
    quality: str = "standard"
    count: int = Field(default=1, ge=1, le=10)
    model_override: str | None = None
    enhance_prompt: bool = True


class GenerateImageResponse(BaseModel):
    job_id: int
    image_paths: list[str]
    revised_prompts: list[str | None] = Field(default_factory=list)
    model_used: str


class GenerateCodeRequest(BaseModel):
    description: str = Field(min_length=1)
    language: str = "python"
    framework: str | None = None


class GenerateCodeResponse(BaseModel):
    job_id: int
    code: str
    explanation: str
    model_used: str


class BatchGenerateItem(BaseModel):
    prompt: str | None = None
    template_id: int | None = None
    variables: dict[str, Any] = Field(default_factory=dict)


class BatchGenerateRequest(BaseModel):
    items: list[BatchGenerateItem]
    style_preset_id: int | None = None
    model_override: str | None = None

    @field_validator("items")
    @classmethod
    def limit_batch(cls, v: list[BatchGenerateItem]) -> list[BatchGenerateItem]:
        if len(v) > settings.MAX_BATCH_SIZE:
            raise ValueError(f"Batch size cannot exceed {settings.MAX_BATCH_SIZE}")
        if len(v) < 1:
            raise ValueError("At least one item required")
        return v


class BatchGenerateResponse(BaseModel):
    task_id: str
    message: str


class ABTestRequest(BaseModel):
    """Inline A/B: two prompt variants on the same input."""

    prompt_a: str
    prompt_b: str
    test_input: str
    evaluation_criteria: str | None = None


class StreamGenerateRequest(BaseModel):
    prompt: str = Field(min_length=1)
    system_prompt: str | None = None
    model_override: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=128000)


class StructuredGenerateRequest(BaseModel):
    prompt: str = Field(min_length=1)
    output_schema: dict[str, Any]
    system_prompt: str | None = None
    model_override: str | None = None
