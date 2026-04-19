"""Prompt template CRUD, render preview, versioning, performance."""

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.core.deps import CreatorUser, CurrentUser, DbSession
from app.models.content import PromptTemplate, TemplateCategory
from app.schemas.templates import (
    PromptTemplateCreate,
    PromptTemplateRead,
    PromptTemplateUpdate,
    RenderTemplateRequest,
    RenderTemplateResponse,
    TemplatePerformanceRead,
    VersionPromptRequest,
)
from app.services.prompt_optimizer import PromptOptimizer
from app.services.template_render import render_template_text

router = APIRouter(prefix="/templates", tags=["templates"])


def _parse_category(v: str) -> TemplateCategory:
    try:
        return TemplateCategory(v)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid category: {v}") from None


@router.post("", response_model=PromptTemplateRead, status_code=status.HTTP_201_CREATED)
async def create_template(db: DbSession, user: CreatorUser, body: PromptTemplateCreate) -> PromptTemplate:
    t = PromptTemplate(
        name=body.name,
        description=body.description,
        category=_parse_category(body.category),
        template_text=body.template_text,
        variables=dict(body.variables or {}),
        system_prompt=body.system_prompt,
        model_config_json=dict(body.model_config_json or {}),
        is_active=body.is_active,
        created_by_id=user.id,
    )
    db.add(t)
    await db.flush()
    await db.refresh(t)
    return t


@router.get("", response_model=list[PromptTemplateRead])
async def list_templates(
    db: DbSession,
    user: CurrentUser,
    active_only: bool = Query(default=True),
) -> list[PromptTemplate]:
    q = select(PromptTemplate).where(PromptTemplate.created_by_id == user.id)
    if active_only:
        q = q.where(PromptTemplate.is_active.is_(True))
    q = q.order_by(PromptTemplate.created_at.desc())
    result = await db.execute(q)
    return list(result.scalars().all())


@router.get("/{template_id}", response_model=PromptTemplateRead)
async def get_template(db: DbSession, user: CurrentUser, template_id: int) -> PromptTemplate:
    result = await db.execute(
        select(PromptTemplate).where(
            PromptTemplate.id == template_id,
            PromptTemplate.created_by_id == user.id,
        )
    )
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Not found")
    return t


@router.patch("/{template_id}", response_model=PromptTemplateRead)
async def update_template(
    db: DbSession,
    user: CreatorUser,
    template_id: int,
    body: PromptTemplateUpdate,
) -> PromptTemplate:
    result = await db.execute(
        select(PromptTemplate).where(
            PromptTemplate.id == template_id,
            PromptTemplate.created_by_id == user.id,
        )
    )
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Not found")
    data = body.model_dump(exclude_unset=True)
    if "model_config_json" in data:
        t.model_config_json = data.pop("model_config_json") or {}
    if "category" in data and data["category"] is not None:
        t.category = _parse_category(data.pop("category"))
    for k, v in data.items():
        setattr(t, k, v)
    await db.flush()
    await db.refresh(t)
    return t


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(db: DbSession, user: CreatorUser, template_id: int) -> None:
    result = await db.execute(
        select(PromptTemplate).where(
            PromptTemplate.id == template_id,
            PromptTemplate.created_by_id == user.id,
        )
    )
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Not found")
    t.is_active = False
    await db.flush()


@router.post("/{template_id}/render", response_model=RenderTemplateResponse)
async def render_template(
    db: DbSession,
    user: CurrentUser,
    template_id: int,
    body: RenderTemplateRequest,
) -> RenderTemplateResponse:
    result = await db.execute(
        select(PromptTemplate).where(
            PromptTemplate.id == template_id,
            PromptTemplate.created_by_id == user.id,
        )
    )
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Not found")
    rendered = render_template_text(t.template_text, body.variables)
    cfg = dict(t.model_config_json or {})
    return RenderTemplateResponse(
        rendered_user_prompt=rendered,
        system_prompt=t.system_prompt,
        effective_model_config=cfg,
    )


@router.post("/{template_id}/version", response_model=PromptTemplateRead, status_code=status.HTTP_201_CREATED)
async def version_template(
    db: DbSession,
    user: CreatorUser,
    template_id: int,
    body: VersionPromptRequest,
) -> PromptTemplate:
    opt = PromptOptimizer()
    try:
        clone = await opt.version_prompt(
            db,
            template_id,
            body.new_template_text,
            description=body.description,
            created_by_id=user.id,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="Parent template not found") from None
    await db.flush()
    await db.refresh(clone)
    return clone


@router.get("/{template_id}/versions", response_model=list[PromptTemplateRead])
async def template_versions(db: DbSession, user: CurrentUser, template_id: int) -> list[PromptTemplate]:
    root = await db.execute(
        select(PromptTemplate).where(
            PromptTemplate.id == template_id,
            PromptTemplate.created_by_id == user.id,
        )
    )
    base = root.scalar_one_or_none()
    if not base:
        raise HTTPException(status_code=404, detail="Not found")
    by_name = await db.execute(
        select(PromptTemplate).where(
            PromptTemplate.created_by_id == user.id,
            PromptTemplate.name == base.name,
        )
    )
    return sorted(by_name.scalars().all(), key=lambda x: (x.version, x.id))


@router.get("/{template_id}/performance", response_model=TemplatePerformanceRead)
async def template_performance(db: DbSession, user: CurrentUser, template_id: int) -> TemplatePerformanceRead:
    result = await db.execute(
        select(PromptTemplate).where(
            PromptTemplate.id == template_id,
            PromptTemplate.created_by_id == user.id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Not found")
    opt = PromptOptimizer()
    agg = await opt.aggregate_performance(db, template_id)
    return TemplatePerformanceRead(**agg)
