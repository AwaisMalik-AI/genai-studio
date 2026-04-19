"""Usage, cost, quality, and template popularity analytics."""

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from app.core.deps import CurrentUser, DbSession
from app.models.user import UserRole
from app.models.content import GenerationJob, JobStatus, JobType, PromptTemplate
from app.schemas.analytics import AnalyticsCosts, AnalyticsPopularTemplates, AnalyticsQuality, AnalyticsUsage

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _validate_period(period: str) -> None:
    if period not in ("daily", "weekly", "monthly"):
        raise HTTPException(status_code=400, detail="period must be daily, weekly, or monthly")


def _period_bounds(period: str) -> datetime:
    now = datetime.now(timezone.utc)
    if period == "daily":
        return now - timedelta(days=1)
    if period == "weekly":
        return now - timedelta(days=7)
    if period == "monthly":
        return now - timedelta(days=30)
    return now - timedelta(days=7)


@router.get("/usage", response_model=AnalyticsUsage)
async def analytics_usage(
    db: DbSession,
    user: CurrentUser,
    period: str = Query(default="weekly"),
) -> AnalyticsUsage:
    _validate_period(period)
    since = _period_bounds(period)
    uid_filter = [] if user.role == UserRole.ADMIN else [GenerationJob.created_by_id == user.id]

    async def count_type(jt: JobType) -> int:
        q = select(func.count()).select_from(GenerationJob).where(
            GenerationJob.created_at >= since,
            GenerationJob.job_type == jt,
            *uid_filter,
        )
        r = await db.execute(q)
        return int(r.scalar() or 0)

    text_n = await count_type(JobType.TEXT)
    img_n = await count_type(JobType.IMAGE)
    code_n = await count_type(JobType.CODE)
    batch_n = await count_type(JobType.BATCH)
    return AnalyticsUsage(
        period=period,
        text_generations=text_n,
        image_generations=img_n,
        code_generations=code_n,
        batch_jobs=batch_n,
    )


@router.get("/costs", response_model=AnalyticsCosts)
async def analytics_costs(
    db: DbSession,
    user: CurrentUser,
    period: str = Query(default="weekly"),
) -> AnalyticsCosts:
    _validate_period(period)
    since = _period_bounds(period)
    uid_filter = [] if user.role == UserRole.ADMIN else [GenerationJob.created_by_id == user.id]
    q = select(
        func.coalesce(func.sum(GenerationJob.tokens_used), 0),
        func.coalesce(func.sum(GenerationJob.cost_estimate), 0.0),
        GenerationJob.model_used,
    ).where(
        GenerationJob.created_at >= since,
        GenerationJob.status == JobStatus.COMPLETED,
        *uid_filter,
    ).group_by(GenerationJob.model_used)
    result = await db.execute(q)
    rows = result.all()
    by_model: dict[str, dict[str, Any]] = {}
    total_tokens = 0
    total_cost = 0.0
    for tokens, cost, model in rows:
        total_tokens += int(tokens or 0)
        total_cost += float(cost or 0)
        by_model[model or "unknown"] = {"tokens": int(tokens or 0), "cost_estimate": float(cost or 0)}
    return AnalyticsCosts(
        period=period,
        total_tokens=total_tokens,
        estimated_cost_usd=round(total_cost, 4),
        by_model=by_model,
    )


@router.get("/quality", response_model=list[AnalyticsQuality])
async def analytics_quality(db: DbSession, user: CurrentUser) -> list[AnalyticsQuality]:
    uid_filter = [] if user.role == UserRole.ADMIN else [PromptTemplate.created_by_id == user.id]
    q = (
        select(
            PromptTemplate.id,
            PromptTemplate.name,
            func.avg(GenerationJob.feedback_rating),
            func.count(GenerationJob.id),
        )
        .join(GenerationJob, GenerationJob.prompt_template_id == PromptTemplate.id)
        .where(
            GenerationJob.feedback_rating.isnot(None),
            *uid_filter,
        )
        .group_by(PromptTemplate.id, PromptTemplate.name)
    )
    result = await db.execute(q)
    out = []
    for tid, name, avg_r, cnt in result.all():
        out.append(
            AnalyticsQuality(
                template_id=tid,
                template_name=name,
                avg_rating=float(avg_r) if avg_r is not None else None,
                sample_size=int(cnt or 0),
            )
        )
    return out


@router.get("/popular-templates", response_model=AnalyticsPopularTemplates)
async def popular_templates(db: DbSession, user: CurrentUser) -> AnalyticsPopularTemplates:
    uid_filter = [] if user.role == UserRole.ADMIN else [PromptTemplate.created_by_id == user.id]
    q = (
        select(PromptTemplate.id, PromptTemplate.name, PromptTemplate.usage_count)
        .where(*uid_filter)
        .order_by(PromptTemplate.usage_count.desc())
        .limit(20)
    )
    result = await db.execute(q)
    templates = [{"id": r[0], "name": r[1], "usage_count": r[2]} for r in result.all()]
    return AnalyticsPopularTemplates(templates=templates)
