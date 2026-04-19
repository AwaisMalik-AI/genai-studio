"""Prompt optimization, expansion, A/B judging, and template versioning."""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.content import GenerationJob, JobStatus, PromptTemplate
from app.services.llm_client import complete_chat


class PromptOptimizer:
    async def optimize(self, prompt: str, goal: str | None) -> str:
        g = goal or "maximize clarity and specificity for a large language model"
        user = f"Goal: {g}\n\nOriginal prompt:\n{prompt}\n\nReturn only the improved prompt."
        text, _ = await complete_chat(
            system_prompt="You are an expert prompt engineer.",
            user_prompt=user,
            temperature=0.4,
            max_tokens=1024,
        )
        return text.strip()

    async def expand(self, prompt: str) -> str:
        user = f"Expand this prompt with useful constraints, format, and context. Return only expanded prompt.\n\n{prompt}"
        text, _ = await complete_chat(
            system_prompt="You enrich prompts without changing the user's intent.",
            user_prompt=user,
            temperature=0.5,
            max_tokens=1200,
        )
        return text.strip()

    async def ab_evaluate(
        self,
        result_a: str,
        result_b: str,
        criteria: str | None,
    ) -> tuple[Literal["a", "b", "tie"], dict[str, Any]]:
        crit = criteria or "overall usefulness, accuracy, and alignment with typical user expectations"
        user = (
            f"Criteria: {crit}\n\n--- Output A ---\n{result_a[:8000]}\n--- Output B ---\n{result_b[:8000]}\n\n"
            "Respond JSON: {\"winner\": \"a\"|\"b\"|\"tie\", \"rationale\": \"...\", \"scores\": {\"a\": 0-10, \"b\": 0-10}}"
        )
        raw, _ = await complete_chat(
            system_prompt="You are an impartial evaluator of two model outputs.",
            user_prompt=user,
            temperature=0.2,
            max_tokens=800,
            json_mode=(settings.LLM_PROVIDER == "openai"),
        )
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            m = re.search(r"\{[\s\S]*\}", raw)
            data = json.loads(m.group(0)) if m else {}
        w = str(data.get("winner", "tie")).lower()
        if w not in ("a", "b", "tie"):
            w = "tie"
        return w, data  # type: ignore[return-value]

    async def version_prompt(
        self,
        db: AsyncSession,
        template_id: int,
        new_template: str,
        *,
        description: str | None = None,
        created_by_id: int,
    ) -> PromptTemplate:
        result = await db.execute(select(PromptTemplate).where(PromptTemplate.id == template_id))
        parent = result.scalar_one_or_none()
        if not parent:
            raise ValueError("Parent template not found")
        new_version = parent.version + 1
        clone = PromptTemplate(
            name=parent.name,
            description=description or parent.description,
            category=parent.category,
            template_text=new_template,
            variables=dict(parent.variables or {}),
            system_prompt=parent.system_prompt,
            model_config_json=dict(parent.model_config_json or {}),
            version=new_version,
            parent_version_id=parent.id,
            performance_score=None,
            usage_count=0,
            is_active=True,
            created_by_id=created_by_id,
        )
        db.add(clone)
        await db.flush()
        return clone

    async def record_template_usage(self, db: AsyncSession, template_id: int, job_success: bool) -> None:
        result = await db.execute(select(PromptTemplate).where(PromptTemplate.id == template_id))
        tmpl = result.scalar_one_or_none()
        if not tmpl:
            return
        tmpl.usage_count = (tmpl.usage_count or 0) + 1
        if job_success:
            tmpl.performance_score = (tmpl.performance_score or 0.7) * 0.95 + 0.05 * 1.0
        else:
            tmpl.performance_score = (tmpl.performance_score or 0.7) * 0.95 + 0.05 * 0.0

    async def aggregate_performance(self, db: AsyncSession, template_id: int) -> dict[str, Any]:
        j = GenerationJob
        q = await db.execute(
            select(
                func.count(j.id),
                func.avg(j.feedback_rating),
            ).where(j.prompt_template_id == template_id, j.status == JobStatus.COMPLETED)
        )
        row = q.one()
        count, avg_rating = row[0], row[1]
        t = await db.execute(select(PromptTemplate).where(PromptTemplate.id == template_id))
        tmpl = t.scalar_one_or_none()
        return {
            "template_id": template_id,
            "version": tmpl.version if tmpl else None,
            "usage_count": tmpl.usage_count if tmpl else 0,
            "performance_score": tmpl.performance_score if tmpl else None,
            "avg_feedback_rating": float(avg_rating) if avg_rating is not None else None,
            "total_jobs": int(count or 0),
        }
