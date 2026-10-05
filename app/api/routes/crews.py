from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.deps import CurrentUser
from app.services.content_crew import ContentCrew
from app.tasks.crew_tasks import run_content_crew_task

router = APIRouter(prefix="/crews", tags=["crews"])


class ContentCrewRequest(BaseModel):
    brief: str = Field(..., min_length=3, max_length=4000)
    style: str = Field(default="professional", max_length=64)
    async_run: bool = False


class ContentCrewResponse(BaseModel):
    crew: str
    used_llm: bool
    steps: list[dict[str, Any]]
    final: str
    task_id: str | None = None


@router.post("/content", response_model=ContentCrewResponse)
async def run_content_crew(body: ContentCrewRequest, _: CurrentUser) -> ContentCrewResponse:
    if body.async_run:
        task = run_content_crew_task.delay(body.brief, body.style)
        return ContentCrewResponse(crew="content", used_llm=False, steps=[], final="queued", task_id=task.id)
    result = ContentCrew().run(body.brief, body.style)
    return ContentCrewResponse(crew=result.crew, used_llm=result.used_llm, steps=result.steps, final=result.final)
