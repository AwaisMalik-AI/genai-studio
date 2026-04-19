from typing import Any

from pydantic import BaseModel


class AnalyticsUsage(BaseModel):
    period: str
    text_generations: int
    image_generations: int
    code_generations: int
    batch_jobs: int


class AnalyticsCosts(BaseModel):
    period: str
    total_tokens: int
    estimated_cost_usd: float
    by_model: dict[str, dict[str, Any]]


class AnalyticsQuality(BaseModel):
    template_id: int
    template_name: str
    avg_rating: float | None
    sample_size: int


class AnalyticsPopularTemplates(BaseModel):
    templates: list[dict[str, Any]]
