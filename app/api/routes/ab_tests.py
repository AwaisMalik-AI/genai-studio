"""A/B prompt tests: CRUD, run, results."""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import delete, select

from app.core.deps import CreatorUser, CurrentUser, DbSession
from app.models.content import ABPromptTest, ABTestStatus, PromptTemplate
from app.schemas.ab_tests import ABPromptTestCreate, ABPromptTestRead, ABPromptTestUpdate, RunABTestRequest
from app.tasks.generation_tasks import ab_test_task

router = APIRouter(prefix="/ab-tests", tags=["ab-tests"])


@router.post("", response_model=ABPromptTestRead, status_code=status.HTTP_201_CREATED)
async def create_ab(db: DbSession, user: CreatorUser, body: ABPromptTestCreate) -> ABPromptTest:
    for pid in (body.prompt_a_id, body.prompt_b_id):
        r = await db.execute(
            select(PromptTemplate).where(
                PromptTemplate.id == pid,
                PromptTemplate.created_by_id == user.id,
            )
        )
        if not r.scalar_one_or_none():
            raise HTTPException(status_code=400, detail=f"Template {pid} not found")
    t = ABPromptTest(
        name=body.name,
        prompt_a_id=body.prompt_a_id,
        prompt_b_id=body.prompt_b_id,
        test_input=body.test_input,
        evaluation_criteria=body.evaluation_criteria,
        created_by_id=user.id,
    )
    db.add(t)
    await db.flush()
    await db.refresh(t)
    return t


@router.get("", response_model=list[ABPromptTestRead])
async def list_ab(db: DbSession, user: CurrentUser) -> list[ABPromptTest]:
    result = await db.execute(
        select(ABPromptTest)
        .where(ABPromptTest.created_by_id == user.id)
        .order_by(ABPromptTest.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/{test_id}", response_model=ABPromptTestRead)
async def get_ab(db: DbSession, user: CurrentUser, test_id: int) -> ABPromptTest:
    result = await db.execute(
        select(ABPromptTest).where(
            ABPromptTest.id == test_id,
            ABPromptTest.created_by_id == user.id,
        )
    )
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Not found")
    return t


@router.patch("/{test_id}", response_model=ABPromptTestRead)
async def update_ab(
    db: DbSession,
    user: CreatorUser,
    test_id: int,
    body: ABPromptTestUpdate,
) -> ABPromptTest:
    result = await db.execute(
        select(ABPromptTest).where(
            ABPromptTest.id == test_id,
            ABPromptTest.created_by_id == user.id,
        )
    )
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Not found")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(t, k, v)
    await db.flush()
    await db.refresh(t)
    return t


@router.delete("/{test_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ab(db: DbSession, user: CreatorUser, test_id: int) -> None:
    result = await db.execute(
        select(ABPromptTest).where(
            ABPromptTest.id == test_id,
            ABPromptTest.created_by_id == user.id,
        )
    )
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Not found")
    await db.execute(delete(ABPromptTest).where(ABPromptTest.id == t.id))
    await db.flush()


@router.post("/{test_id}/run")
async def run_ab(
    db: DbSession,
    user: CreatorUser,
    test_id: int,
    body: RunABTestRequest,
) -> dict:
    result = await db.execute(
        select(ABPromptTest).where(
            ABPromptTest.id == test_id,
            ABPromptTest.created_by_id == user.id,
        )
    )
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Not found")
    if t.status == ABTestStatus.RUNNING and not body.force_rerun:
        raise HTTPException(status_code=409, detail="Test already running")
    task = ab_test_task.delay(test_id, user.id)
    return {"task_id": task.id, "status": "queued"}


@router.get("/{test_id}/results", response_model=ABPromptTestRead)
async def ab_results(db: DbSession, user: CurrentUser, test_id: int) -> ABPromptTest:
    return await get_ab(db, user, test_id)
