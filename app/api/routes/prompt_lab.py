from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.deps import CurrentUser
from app.services.prompt_lab import variants

router = APIRouter(prefix="/prompt-lab", tags=["prompt-lab"])


class LabRequest(BaseModel):
    brief: str = Field(..., min_length=3, max_length=2000)
    style: str = Field(default="direct", max_length=40)


@router.post("/variants")
async def prompt_variants(body: LabRequest, _: CurrentUser) -> dict:
    return {"kind": "prompt_lab", **variants(body.brief, body.style)}
