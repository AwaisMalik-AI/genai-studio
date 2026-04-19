"""User model with role-based access (admin, creator, viewer)."""

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    CREATOR = "creator"
    VIEWER = "viewer"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, native_enum=False, length=32), default=UserRole.VIEWER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    prompt_templates = relationship("PromptTemplate", back_populates="creator")
    generation_jobs = relationship("GenerationJob", back_populates="creator")
    collections = relationship("ContentCollection", back_populates="creator")
    ab_tests = relationship("ABPromptTest", back_populates="creator")
    style_presets = relationship("StylePreset", back_populates="creator")
    usage_quota = relationship("UsageQuota", back_populates="user", uselist=False)
