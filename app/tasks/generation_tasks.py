"""Async generation workloads: batch text, image, A/B evaluation."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from celery import shared_task
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.content import (
    ABPromptTest,
    ABTestStatus,
    ABWinner,
    GenerationJob,
    ImageGeneration,
    JobStatus,
    JobType,
    PromptTemplate,
)
from app.services.generators.image_generator import ImageGenerator, ImageGenerationError
from app.services.generators.text_generator import TextGenerator
from app.services.prompt_optimizer import PromptOptimizer
from app.services.quota_service import increment_text_usage


@shared_task(name="app.tasks.generation_tasks.batch_generate_task")
def batch_generate_task(
    user_id: int,
    items: list[dict[str, Any]],
    style_preset_id: int | None,
    model_override: str | None,
) -> dict:
    async def _run() -> dict:
        gen = TextGenerator()
        completed = 0
        async with AsyncSessionLocal() as session:
            for it in items:
                job = GenerationJob(
                    job_type=JobType.BATCH,
                    prompt_text=it.get("prompt") or f"template:{it.get('template_id')}",
                    model_used=model_override or "",
                    input_variables=it.get("variables"),
                    status=JobStatus.GENERATING,
                    created_by_id=user_id,
                )
                session.add(job)
                await session.flush()
                try:
                    if it.get("template_id"):
                        result, tmpl = await gen.generate_with_template(
                            session,
                            int(it["template_id"]),
                            dict(it.get("variables") or {}),
                            style_preset_id,
                            model_override,
                            config_overrides=None,
                        )
                        job.prompt_template_id = tmpl.id
                        job.model_used = result.model_used
                    else:
                        result = await gen.generate(
                            it.get("prompt") or "",
                            None,
                            model_override,
                            {},
                        )
                        job.model_used = result.model_used
                    job.status = JobStatus.COMPLETED
                    job.output_text = result.text
                    job.tokens_used = result.tokens_used
                    job.cost_estimate = result.cost_estimate
                    job.generation_time_ms = result.generation_time_ms
                    job.completed_at = datetime.now(timezone.utc)
                    await increment_text_usage(session, user_id, result.tokens_used, result.cost_estimate)
                    completed += 1
                except Exception as e:
                    job.status = JobStatus.FAILED
                    job.error_message = str(e)[:4000]
                    job.completed_at = datetime.now(timezone.utc)
            await session.commit()
        return {"processed": len(items), "completed": completed}

    return asyncio.run(_run())


@shared_task(name="app.tasks.generation_tasks.image_generate_task")
def image_generate_task(
    user_id: int,
    prompt: str,
    negative_prompt: str | None,
    size: str,
    style: str | None,
    quality: str,
    model_override: str | None,
    enhance_prompt: bool,
) -> dict:
    async def _run() -> dict:
        ig = ImageGenerator()
        async with AsyncSessionLocal() as session:
            job = GenerationJob(
                job_type=JobType.IMAGE,
                prompt_text=prompt,
                model_used=model_override or "",
                status=JobStatus.GENERATING,
                created_by_id=user_id,
            )
            session.add(job)
            await session.flush()
            try:
                path, rev, m = await ig.generate(
                    prompt,
                    negative_prompt,
                    size,
                    style,
                    quality,
                    model_override,
                    enhance=enhance_prompt,
                )
                session.add(
                    ImageGeneration(
                        job_id=job.id,
                        prompt=prompt,
                        negative_prompt=negative_prompt,
                        model=m,
                        size=size,
                        style=style,
                        quality=quality,
                        image_path=path,
                        revised_prompt=rev,
                    )
                )
                job.model_used = m
                job.status = JobStatus.COMPLETED
                job.output_image_path = path
                job.output_metadata = {"revised_prompt": rev}
                job.completed_at = datetime.now(timezone.utc)
                await session.commit()
                return {"job_id": job.id, "path": path}
            except ImageGenerationError as e:
                job.status = JobStatus.FAILED
                job.error_message = str(e)
                job.completed_at = datetime.now(timezone.utc)
                await session.commit()
                raise

    return asyncio.run(_run())


@shared_task(name="app.tasks.generation_tasks.ab_test_task")
def ab_test_task(test_id: int, user_id: int) -> dict:
    async def _run() -> dict:
        opt = PromptOptimizer()
        gen = TextGenerator()
        async with AsyncSessionLocal() as session:
            r = await session.execute(
                select(ABPromptTest).where(
                    ABPromptTest.id == test_id,
                    ABPromptTest.created_by_id == user_id,
                )
            )
            test = r.scalar_one_or_none()
            if not test:
                return {"error": "not_found"}
            test.status = ABTestStatus.RUNNING
            await session.commit()

            pa = await session.execute(select(PromptTemplate).where(PromptTemplate.id == test.prompt_a_id))
            pb = await session.execute(select(PromptTemplate).where(PromptTemplate.id == test.prompt_b_id))
            ta, tb = pa.scalar_one_or_none(), pb.scalar_one_or_none()
            if not ta or not tb:
                test.status = ABTestStatus.PENDING
                await session.commit()
                return {"error": "template_missing"}

            from app.services.template_render import render_template_text

            ra = await gen.generate(
                render_template_text(ta.template_text, {}) + "\n\n" + test.test_input,
                ta.system_prompt,
                None,
                dict(ta.model_config_json or {}),
            )
            rb = await gen.generate(
                render_template_text(tb.template_text, {}) + "\n\n" + test.test_input,
                tb.system_prompt,
                None,
                dict(tb.model_config_json or {}),
            )
            winner, scores = await opt.ab_evaluate(ra.text, rb.text, test.evaluation_criteria)
            test.result_a = ra.text
            test.result_b = rb.text
            test.winner = ABWinner(winner) if winner in ("a", "b", "tie") else ABWinner.TIE
            test.auto_eval_scores = scores
            test.status = ABTestStatus.EVALUATED
            await session.commit()
            return {"winner": winner, "test_id": test_id}

    return asyncio.run(_run())
