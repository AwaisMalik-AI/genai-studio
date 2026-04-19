"""Generation jobs listing, detail, and output retrieval."""

import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy import select

from app.core.deps import CurrentUser, DbSession
from app.models.user import UserRole
from app.models.content import GenerationJob, JobStatus, JobType
from app.schemas.jobs import GenerationJobRead

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=list[GenerationJobRead])
async def list_jobs(
    db: DbSession,
    user: CurrentUser,
    status_filter: str | None = Query(default=None, alias="status"),
    job_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[GenerationJob]:
    q = select(GenerationJob)
    if user.role != UserRole.ADMIN:
        q = q.where(GenerationJob.created_by_id == user.id)
    if status_filter:
        try:
            q = q.where(GenerationJob.status == JobStatus(status_filter))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid status") from None
    if job_type:
        try:
            q = q.where(GenerationJob.job_type == JobType(job_type))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid job_type") from None
    q = q.order_by(GenerationJob.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(q)
    return list(result.scalars().all())


@router.get("/{job_id}", response_model=GenerationJobRead)
async def get_job(db: DbSession, user: CurrentUser, job_id: int) -> GenerationJob:
    q = select(GenerationJob).where(GenerationJob.id == job_id)
    if user.role != UserRole.ADMIN:
        q = q.where(GenerationJob.created_by_id == user.id)
    result = await db.execute(q)
    j = result.scalar_one_or_none()
    if not j:
        raise HTTPException(status_code=404, detail="Not found")
    return j


@router.get("/{job_id}/output")
async def job_output(db: DbSession, user: CurrentUser, job_id: int):
    q = select(GenerationJob).where(GenerationJob.id == job_id)
    if user.role != UserRole.ADMIN:
        q = q.where(GenerationJob.created_by_id == user.id)
    result = await db.execute(q)
    j = result.scalar_one_or_none()
    if not j:
        raise HTTPException(status_code=404, detail="Not found")
    if j.status != JobStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Job not completed")
    if j.job_type == JobType.IMAGE and j.output_image_path:
        path = Path(j.output_image_path)
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Image file missing")
        mime, _ = mimetypes.guess_type(str(path))
        return FileResponse(path, media_type=mime or "application/octet-stream")
    if j.output_text:
        return PlainTextResponse(j.output_text)
    raise HTTPException(status_code=404, detail="No output available")
