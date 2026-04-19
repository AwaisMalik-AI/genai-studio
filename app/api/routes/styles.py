"""Style presets CRUD and preview generation."""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import delete, select, or_

from app.core.deps import CreatorUser, CurrentUser, DbSession
from app.models.content import StyleCategory, StylePreset
from app.schemas.styles import StylePresetCreate, StylePresetRead, StylePresetUpdate, StylePreviewRequest
from app.services.generators.text_generator import TextGenerator

router = APIRouter(prefix="/styles", tags=["styles"])


def _parse_category(v: str) -> StyleCategory:
    try:
        return StyleCategory(v)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid category: {v}") from None


@router.post("", response_model=StylePresetRead, status_code=status.HTTP_201_CREATED)
async def create_style(db: DbSession, user: CreatorUser, body: StylePresetCreate) -> StylePreset:
    s = StylePreset(
        name=body.name,
        description=body.description,
        category=_parse_category(body.category),
        config=dict(body.config or {}),
        example_output=body.example_output,
        is_public=body.is_public,
        created_by_id=user.id,
    )
    db.add(s)
    await db.flush()
    await db.refresh(s)
    return s


@router.get("", response_model=list[StylePresetRead])
async def list_styles(db: DbSession, user: CurrentUser) -> list[StylePreset]:
    result = await db.execute(
        select(StylePreset).where(
            or_(StylePreset.is_public.is_(True), StylePreset.created_by_id == user.id)
        ).order_by(StylePreset.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/{style_id}", response_model=StylePresetRead)
async def get_style(db: DbSession, user: CurrentUser, style_id: int) -> StylePreset:
    result = await db.execute(select(StylePreset).where(StylePreset.id == style_id))
    s = result.scalar_one_or_none()
    if not s or (not s.is_public and s.created_by_id != user.id):
        raise HTTPException(status_code=404, detail="Not found")
    return s


@router.patch("/{style_id}", response_model=StylePresetRead)
async def update_style(
    db: DbSession,
    user: CreatorUser,
    style_id: int,
    body: StylePresetUpdate,
) -> StylePreset:
    result = await db.execute(
        select(StylePreset).where(
            StylePreset.id == style_id,
            StylePreset.created_by_id == user.id,
        )
    )
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Not found")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(s, k, v)
    await db.flush()
    await db.refresh(s)
    return s


@router.delete("/{style_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_style(db: DbSession, user: CreatorUser, style_id: int) -> None:
    result = await db.execute(
        select(StylePreset).where(
            StylePreset.id == style_id,
            StylePreset.created_by_id == user.id,
        )
    )
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Not found")
    await db.execute(delete(StylePreset).where(StylePreset.id == s.id))
    await db.flush()


@router.post("/{style_id}/preview")
async def preview_style(db: DbSession, user: CurrentUser, style_id: int, body: StylePreviewRequest) -> dict:
    result = await db.execute(select(StylePreset).where(StylePreset.id == style_id))
    s = result.scalar_one_or_none()
    if not s or (not s.is_public and s.created_by_id != user.id):
        raise HTTPException(status_code=404, detail="Not found")
    mod = (s.config.get("system_prompt_modifier") or "").strip()
    sys_prompt = mod or "Apply the style implied by this preset name and description."
    gen = TextGenerator()
    out = await gen.generate(
        body.sample_prompt,
        sys_prompt + f"\n\nPreset: {s.name}. {s.description or ''}",
        None,
        {"temperature": 0.7, "max_tokens": 512},
    )
    return {"preview_text": out.text, "model_used": out.model_used, "tokens_used": out.tokens_used}
