"""Usage quotas: ensure or create quota row, check limits, increment counters."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.content import UsageQuota


async def get_or_create_quota(db: AsyncSession, user_id: int) -> UsageQuota:
    result = await db.execute(select(UsageQuota).where(UsageQuota.user_id == user_id))
    q = result.scalar_one_or_none()
    if q:
        return q
    q = UsageQuota(user_id=user_id)
    db.add(q)
    await db.flush()
    return q


async def check_text_quota(db: AsyncSession, user_id: int) -> None:
    q = await get_or_create_quota(db, user_id)
    if q.text_used_today >= q.daily_text_limit:
        raise PermissionError("Daily text generation limit reached")


async def check_image_quota(db: AsyncSession, user_id: int, n: int = 1) -> None:
    q = await get_or_create_quota(db, user_id)
    if q.images_used_today + n > q.daily_image_limit:
        raise PermissionError("Daily image generation limit reached")


async def increment_text_usage(db: AsyncSession, user_id: int, tokens: int, cost: float) -> None:
    q = await get_or_create_quota(db, user_id)
    q.text_used_today += 1
    q.total_tokens_lifetime += max(tokens, 0)
    q.total_cost_lifetime = float(q.total_cost_lifetime or 0) + cost


async def increment_image_usage(db: AsyncSession, user_id: int, n: int = 1) -> None:
    q = await get_or_create_quota(db, user_id)
    q.images_used_today += n


async def check_batch_size(n: int) -> None:
    if n > settings.MAX_BATCH_SIZE:
        raise ValueError(f"Batch size exceeds MAX_BATCH_SIZE ({settings.MAX_BATCH_SIZE})")


async def reset_all_daily_quotas(db: AsyncSession) -> int:
    """Reset text/image daily counters; returns number of rows updated."""
    result = await db.execute(select(UsageQuota))
    rows = result.scalars().all()
    now = datetime.now(timezone.utc)
    for q in rows:
        q.text_used_today = 0
        q.images_used_today = 0
        q.last_reset_at = now
    return len(rows)
