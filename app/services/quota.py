from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import UsageQuota


async def get_or_create_quota(db: AsyncSession, user_id: UUID) -> UsageQuota:
    r = await db.execute(select(UsageQuota).where(UsageQuota.user_id == user_id))
    q = r.scalar_one_or_none()
    if q:
        return q
    q = UsageQuota(user_id=user_id)
    db.add(q)
    await db.flush()
    return q


async def ensure_text_quota(db: AsyncSession, user_id: UUID) -> UsageQuota:
    q = await get_or_create_quota(db, user_id)
    _maybe_reset_daily(q)
    if q.text_used_today >= q.daily_text_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Daily text generation limit reached",
        )
    return q


async def ensure_text_quota_n(db: AsyncSession, user_id: UUID, n: int) -> UsageQuota:
    q = await get_or_create_quota(db, user_id)
    _maybe_reset_daily(q)
    if q.text_used_today + n > q.daily_text_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Daily text generation limit would be exceeded for this batch",
        )
    return q


async def ensure_image_quota(db: AsyncSession, user_id: UUID, n: int = 1) -> UsageQuota:
    q = await get_or_create_quota(db, user_id)
    _maybe_reset_daily(q)
    if q.images_used_today + n > q.daily_image_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Daily image generation limit reached",
        )
    return q


def _maybe_reset_daily(q: UsageQuota) -> None:
    now = datetime.now(timezone.utc)
    last = q.last_reset_at
    if last is None or now.date() > last.date():
        q.text_used_today = 0
        q.images_used_today = 0
        q.last_reset_at = now


async def record_text_usage(db: AsyncSession, user_id: UUID, tokens: int | None, cost: float | None) -> None:
    q = await get_or_create_quota(db, user_id)
    _maybe_reset_daily(q)
    q.text_used_today += 1
    if tokens:
        q.total_tokens_lifetime += tokens
    if cost:
        q.total_cost_lifetime += float(cost)
    await db.flush()


async def record_image_usage(db: AsyncSession, user_id: UUID, n: int = 1, cost: float | None = None) -> None:
    q = await get_or_create_quota(db, user_id)
    _maybe_reset_daily(q)
    q.images_used_today += n
    if cost:
        q.total_cost_lifetime += float(cost)
    await db.flush()
