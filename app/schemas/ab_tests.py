from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ABPromptTestCreate(BaseModel):
    name: str
    prompt_a_id: int
    prompt_b_id: int
    test_input: str
    evaluation_criteria: str | None = None


class ABPromptTestUpdate(BaseModel):
    name: str | None = None
    test_input: str | None = None
    evaluation_criteria: str | None = None


class ABPromptTestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    prompt_a_id: int
    prompt_b_id: int
    test_input: str
    result_a: str | None
    result_b: str | None
    winner: Any
    evaluation_criteria: str | None
    auto_eval_scores: dict[str, Any] | None
    status: Any
    created_by_id: int
    created_at: datetime


class RunABTestRequest(BaseModel):
    force_rerun: bool = False
