"""Application settings — all secrets and URLs from environment (no hardcoding)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    APP_NAME: str = "GenAI Studio"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api"

    # Database
    DATABASE_URL: PostgresDsn = Field(
        ...,
        description="Async PostgreSQL URL, e.g. postgresql+asyncpg://user:pass@host:5432/db",
    )

    # Redis
    REDIS_URL: RedisDsn = Field(..., description="Redis URL for cache and Celery broker")

    # Security
    SECRET_KEY: str = Field(..., min_length=32, description="JWT signing secret")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    # LLM
    LLM_PROVIDER: Literal["openai", "anthropic"] = "openai"
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_API_KEY: str = Field(..., description="API key for the configured LLM provider")

    # Image generation
    IMAGE_GEN_PROVIDER: Literal["openai_dalle", "stability_ai", "replicate"] = "openai_dalle"
    IMAGE_GEN_API_KEY: str = Field(default="", description="API key for image provider (required when generating images)")
    REPLICATE_MODEL_VERSION: str = Field(
        default="",
        description="Replicate model version id when using replicate provider",
    )

    # Celery
    CELERY_BROKER_URL: str = Field(default="", description="Defaults to REDIS_URL if empty")
    CELERY_RESULT_BACKEND: str = Field(default="", description="Defaults to REDIS_URL if empty")

    # Storage
    STORAGE_PATH: str = Field(default="./storage/generated")

    # Features
    CONTENT_MODERATION_ENABLED: bool = True
    MAX_BATCH_SIZE: int = Field(default=50, ge=1, le=200)

    LOG_LEVEL: str = "INFO"

    @model_validator(mode="after")
    def celery_defaults_from_redis(self) -> "Settings":
        r = str(self.REDIS_URL)
        if not self.CELERY_BROKER_URL:
            object.__setattr__(self, "CELERY_BROKER_URL", r)
        if not self.CELERY_RESULT_BACKEND:
            object.__setattr__(self, "CELERY_RESULT_BACKEND", r)
        return self

    @property
    def database_url_str(self) -> str:
        return str(self.DATABASE_URL)

    @property
    def sync_database_url(self) -> str:
        """SQLAlchemy sync URL for Alembic/migrations if needed."""
        u = str(self.DATABASE_URL)
        return u.replace("+asyncpg", "")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
