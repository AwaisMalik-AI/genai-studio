"""Scheduled maintenance: quota reset, storage cleanup."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from celery import shared_task

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.services.quota_service import reset_all_daily_quotas


@shared_task(name="app.tasks.maintenance_tasks.reset_quotas_task")
def reset_quotas_task() -> dict:
    async def _run() -> int:
        async with AsyncSessionLocal() as session:
            try:
                n = await reset_all_daily_quotas(session)
                await session.commit()
                return n
            except Exception:
                await session.rollback()
                raise

    n = asyncio.run(_run())
    return {"reset_rows": n, "at": datetime.now(timezone.utc).isoformat()}


@shared_task(name="app.tasks.maintenance_tasks.cleanup_old_images_task")
def cleanup_old_images_task(max_age_days: int = 30) -> dict:
    root = Path(settings.STORAGE_PATH)
    if not root.is_dir():
        return {"removed": 0, "message": "storage not found"}
    cutoff = time.time() - max_age_days * 86400
    removed = 0
    for p in root.glob("**/*"):
        if p.is_file() and p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
            try:
                if p.stat().st_mtime < cutoff:
                    p.unlink(missing_ok=True)
                    meta = p.with_suffix(p.suffix + ".json")
                    meta.unlink(missing_ok=True)
                    removed += 1
            except OSError:
                continue
    return {"removed": removed, "max_age_days": max_age_days}
