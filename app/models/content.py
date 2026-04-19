"""Core domain models: templates, jobs, images, collections, A/B tests, quotas, styles."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class TemplateCategory(str, enum.Enum):
    TEXT_GEN = "text_gen"
    IMAGE_GEN = "image_gen"
    CODE_GEN = "code_gen"
    TRANSLATION = "translation"
    SUMMARIZATION = "summarization"


class JobType(str, enum.Enum):
    TEXT = "text"
    IMAGE = "image"
    CODE = "code"
    BATCH = "batch"


class JobStatus(str, enum.Enum):
    QUEUED = "queued"
    GENERATING = "generating"
    MODERATION_CHECK = "moderation_check"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class CollectionType(str, enum.Enum):
    BLOG_SERIES = "blog_series"
    PRODUCT_CATALOG = "product_catalog"
    SOCIAL_MEDIA = "social_media"
    EMAIL_CAMPAIGN = "email_campaign"


class ABWinner(str, enum.Enum):
    A = "a"
    B = "b"
    TIE = "tie"


class ABTestStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    EVALUATED = "evaluated"


class StyleCategory(str, enum.Enum):
    WRITING_STYLE = "writing_style"
    IMAGE_STYLE = "image_style"
    TONE = "tone"


class PromptTemplate(Base):
    __tablename__ = "prompt_templates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[TemplateCategory] = mapped_column(
        Enum(TemplateCategory, native_enum=False, length=32),
        nullable=False,
    )
    template_text: Mapped[str] = mapped_column(Text, nullable=False)
    variables: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_config_json: Mapped[dict[str, Any]] = mapped_column("model_config", JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    parent_version_id: Mapped[int | None] = mapped_column(ForeignKey("prompt_templates.id"), nullable=True)
    performance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    creator = relationship("User", back_populates="prompt_templates")
    parent_version = relationship("PromptTemplate", remote_side="PromptTemplate.id", backref="child_versions")
    generation_jobs = relationship("GenerationJob", back_populates="prompt_template")


class GenerationJob(Base):
    __tablename__ = "generation_jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_type: Mapped[JobType] = mapped_column(Enum(JobType, native_enum=False, length=32), nullable=False)
    prompt_template_id: Mapped[int | None] = mapped_column(ForeignKey("prompt_templates.id"), nullable=True)
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    model_used: Mapped[str] = mapped_column(String(128), nullable=False)
    input_variables: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, native_enum=False, length=32),
        default=JobStatus.QUEUED,
    )
    output_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_image_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    output_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    generation_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_estimate: Mapped[float | None] = mapped_column(Float, nullable=True)
    moderation_result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    feedback_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    prompt_template = relationship("PromptTemplate", back_populates="generation_jobs")
    creator = relationship("User", back_populates="generation_jobs")
    images = relationship("ImageGeneration", back_populates="job", cascade="all, delete-orphan")
    collection_items = relationship("CollectionItem", back_populates="job")


class ImageGeneration(Base):
    __tablename__ = "image_generations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("generation_jobs.id", ondelete="CASCADE"), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    negative_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    size: Mapped[str] = mapped_column(String(32), default="1024x1024")
    style: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quality: Mapped[str] = mapped_column(String(32), default="standard")
    image_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    revised_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    job = relationship("GenerationJob", back_populates="images")


class ContentCollection(Base):
    __tablename__ = "content_collections"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    collection_type: Mapped[CollectionType] = mapped_column(
        Enum(CollectionType, native_enum=False, length=32),
        nullable=False,
    )
    total_items: Mapped[int] = mapped_column(Integer, default=0)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    creator = relationship("User", back_populates="collections")
    items = relationship(
        "CollectionItem",
        back_populates="collection",
        cascade="all, delete-orphan",
        order_by="CollectionItem.order_index",
    )


class CollectionItem(Base):
    __tablename__ = "collection_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    collection_id: Mapped[int] = mapped_column(
        ForeignKey("content_collections.id", ondelete="CASCADE"),
        nullable=False,
    )
    job_id: Mapped[int] = mapped_column(ForeignKey("generation_jobs.id"), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    collection = relationship("ContentCollection", back_populates="items")
    job = relationship("GenerationJob", back_populates="collection_items")


class ABPromptTest(Base):
    __tablename__ = "ab_prompt_tests"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt_a_id: Mapped[int] = mapped_column(ForeignKey("prompt_templates.id"), nullable=False)
    prompt_b_id: Mapped[int] = mapped_column(ForeignKey("prompt_templates.id"), nullable=False)
    test_input: Mapped[str] = mapped_column(Text, nullable=False)
    result_a: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_b: Mapped[str | None] = mapped_column(Text, nullable=True)
    winner: Mapped[ABWinner | None] = mapped_column(Enum(ABWinner, native_enum=False, length=8), nullable=True)
    evaluation_criteria: Mapped[str | None] = mapped_column(Text, nullable=True)
    auto_eval_scores: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[ABTestStatus] = mapped_column(
        Enum(ABTestStatus, native_enum=False, length=32),
        default=ABTestStatus.PENDING,
    )
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    creator = relationship("User", back_populates="ab_tests")
    prompt_a = relationship("PromptTemplate", foreign_keys=[prompt_a_id])
    prompt_b = relationship("PromptTemplate", foreign_keys=[prompt_b_id])


class UsageQuota(Base):
    __tablename__ = "usage_quotas"
    __table_args__ = (UniqueConstraint("user_id", name="uq_usage_quota_user"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    daily_text_limit: Mapped[int] = mapped_column(Integer, default=100)
    daily_image_limit: Mapped[int] = mapped_column(Integer, default=20)
    text_used_today: Mapped[int] = mapped_column(Integer, default=0)
    images_used_today: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens_lifetime: Mapped[int] = mapped_column(Integer, default=0)
    total_cost_lifetime: Mapped[float] = mapped_column(Float, default=0.0)
    last_reset_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="usage_quota")


class StylePreset(Base):
    __tablename__ = "style_presets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[StyleCategory] = mapped_column(Enum(StyleCategory, native_enum=False, length=32), nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    example_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    creator = relationship("User", back_populates="style_presets")
