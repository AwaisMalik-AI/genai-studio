"""Content collections CRUD, items, export."""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.core.deps import CreatorUser, CurrentUser, DbSession
from app.models.content import CollectionItem, CollectionType, ContentCollection, GenerationJob
from app.schemas.collections import (
    CollectionCreate,
    CollectionItemCreate,
    CollectionItemRead,
    CollectionRead,
    CollectionUpdate,
)

router = APIRouter(prefix="/collections", tags=["collections"])


@router.post("", response_model=CollectionRead, status_code=status.HTTP_201_CREATED)
async def create_collection(db: DbSession, user: CreatorUser, body: CollectionCreate) -> ContentCollection:
    try:
        ctype = CollectionType(body.collection_type)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid collection_type") from None
    c = ContentCollection(
        name=body.name,
        description=body.description,
        collection_type=ctype,
        created_by_id=user.id,
    )
    db.add(c)
    await db.flush()
    await db.refresh(c)
    return c


@router.get("", response_model=list[CollectionRead])
async def list_collections(db: DbSession, user: CurrentUser) -> list[ContentCollection]:
    result = await db.execute(
        select(ContentCollection)
        .where(ContentCollection.created_by_id == user.id)
        .order_by(ContentCollection.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/{collection_id}", response_model=CollectionRead)
async def get_collection(db: DbSession, user: CurrentUser, collection_id: int) -> ContentCollection:
    result = await db.execute(
        select(ContentCollection)
        .options(selectinload(ContentCollection.items))
        .where(
            ContentCollection.id == collection_id,
            ContentCollection.created_by_id == user.id,
        )
    )
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Not found")
    return c


@router.patch("/{collection_id}", response_model=CollectionRead)
async def update_collection(
    db: DbSession,
    user: CreatorUser,
    collection_id: int,
    body: CollectionUpdate,
) -> ContentCollection:
    result = await db.execute(
        select(ContentCollection).where(
            ContentCollection.id == collection_id,
            ContentCollection.created_by_id == user.id,
        )
    )
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Not found")
    if body.name is not None:
        c.name = body.name
    if body.description is not None:
        c.description = body.description
    await db.flush()
    await db.refresh(c)
    return c


@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_collection(db: DbSession, user: CreatorUser, collection_id: int) -> None:
    result = await db.execute(
        select(ContentCollection).where(
            ContentCollection.id == collection_id,
            ContentCollection.created_by_id == user.id,
        )
    )
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Not found")
    await db.execute(delete(CollectionItem).where(CollectionItem.collection_id == c.id))
    await db.execute(delete(ContentCollection).where(ContentCollection.id == c.id))
    await db.flush()


@router.post("/{collection_id}/items", response_model=CollectionItemRead, status_code=status.HTTP_201_CREATED)
async def add_item(
    db: DbSession,
    user: CreatorUser,
    collection_id: int,
    body: CollectionItemCreate,
) -> CollectionItem:
    result = await db.execute(
        select(ContentCollection).where(
            ContentCollection.id == collection_id,
            ContentCollection.created_by_id == user.id,
        )
    )
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Not found")
    jr = await db.execute(
        select(GenerationJob).where(
            GenerationJob.id == body.job_id,
            GenerationJob.created_by_id == user.id,
        )
    )
    if not jr.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Job not found")
    item = CollectionItem(
        collection_id=c.id,
        job_id=body.job_id,
        order_index=body.order_index,
        notes=body.notes,
    )
    db.add(item)
    c.total_items = (c.total_items or 0) + 1
    await db.flush()
    await db.refresh(item)
    return item


@router.get("/{collection_id}/export")
async def export_collection(db: DbSession, user: CurrentUser, collection_id: int) -> Response:
    result = await db.execute(
        select(ContentCollection)
        .options(selectinload(ContentCollection.items))
        .where(
            ContentCollection.id == collection_id,
            ContentCollection.created_by_id == user.id,
        )
    )
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Not found")
    job_ids = [i.job_id for i in c.items]
    jobs_map: dict[int, GenerationJob] = {}
    if job_ids:
        jr = await db.execute(select(GenerationJob).where(GenerationJob.id.in_(job_ids)))
        for j in jr.scalars().all():
            jobs_map[j.id] = j
    lines = []
    for item in sorted(c.items, key=lambda x: x.order_index):
        j = jobs_map.get(item.job_id)
        rec = {
            "order": item.order_index,
            "notes": item.notes,
            "job_id": item.job_id,
            "status": j.status.value if j else None,
            "output_text": j.output_text if j else None,
            "output_image_path": j.output_image_path if j else None,
            "output_metadata": j.output_metadata if j else None,
        }
        lines.append(rec)
    payload = {
        "collection": {"id": c.id, "name": c.name, "type": c.collection_type.value},
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "items": lines,
    }
    return JSONResponse(content=payload)
