"""Generation endpoints: text, image, code, batch (async), SSE stream."""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from sse_starlette.sse import EventSourceResponse

from app.core.deps import CreatorUser, DbSession
from app.models.content import GenerationJob, ImageGeneration, JobStatus, JobType
from app.schemas.generate import (
    ABTestRequest,
    BatchGenerateRequest,
    BatchGenerateResponse,
    GenerateCodeRequest,
    GenerateCodeResponse,
    GenerateImageRequest,
    GenerateImageResponse,
    GenerateTextRequest,
    GenerateTextResponse,
    StreamGenerateRequest,
    StructuredGenerateRequest,
)
from app.services.content_moderator import ContentModerator
from app.services.generators.code_generator import CodeGenerator
from app.services.generators.image_generator import ImageGenerator, ImageGenerationError
from app.services.generators.text_generator import TextGenerator
from app.services.prompt_optimizer import PromptOptimizer
from app.services.quota_service import (
    check_batch_size,
    check_image_quota,
    check_text_quota,
    increment_image_usage,
    increment_text_usage,
)
from app.tasks.generation_tasks import batch_generate_task

router = APIRouter(prefix="/generate", tags=["generate"])


@router.post("/text", response_model=GenerateTextResponse)
async def generate_text(db: DbSession, user: CreatorUser, body: GenerateTextRequest) -> GenerateTextResponse:
    if not body.prompt and not body.template_id:
        raise HTTPException(status_code=400, detail="Provide prompt or template_id")
    await check_text_quota(db, user.id)
    moderator = ContentModerator()
    gen = TextGenerator()
    if body.prompt:
        pre = await moderator.moderate_prompt(body.prompt)
        if pre.decision == "block":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"moderation": pre.__dict__})
        out_moderation = await moderator.moderate_text(body.prompt)
    else:
        out_moderation = None

    job = GenerationJob(
        job_type=JobType.TEXT,
        prompt_template_id=body.template_id,
        prompt_text=body.prompt or f"template:{body.template_id}",
        model_used=body.model_override or "",
        input_variables=body.variables or None,
        status=JobStatus.GENERATING,
        created_by_id=user.id,
    )
    db.add(job)
    await db.flush()

    try:
        if body.template_id:
            overrides = {
                "temperature": body.temperature,
                "max_tokens": body.max_tokens,
                "top_p": body.top_p,
            }
            result, tmpl = await gen.generate_with_template(
                db,
                body.template_id,
                body.variables or {},
                body.style_preset_id,
                body.model_override,
                body.content_type,
                config_overrides=overrides,
            )
            job.prompt_template_id = tmpl.id
            job.model_used = result.model_used
        else:
            cfg = {}
            if body.temperature is not None:
                cfg["temperature"] = body.temperature
            if body.max_tokens is not None:
                cfg["max_tokens"] = body.max_tokens
            if body.top_p is not None:
                cfg["top_p"] = body.top_p
            result = await gen.generate(
                body.prompt or "",
                body.system_prompt,
                body.model_override,
                cfg,
                body.content_type,
            )
            job.model_used = result.model_used

        post = await moderator.moderate_text(result.text)
        if post.decision == "block":
            job.status = JobStatus.BLOCKED
            job.moderation_result = {"input": getattr(out_moderation, "__dict__", None), "output": post.__dict__}
            job.completed_at = datetime.now(timezone.utc)
            await db.flush()
            raise HTTPException(status_code=400, detail="Output blocked by moderation")

        job.status = JobStatus.COMPLETED
        job.output_text = result.text
        job.tokens_used = result.tokens_used
        job.cost_estimate = result.cost_estimate
        job.generation_time_ms = result.generation_time_ms
        job.moderation_result = {"output": post.__dict__}
        job.completed_at = datetime.now(timezone.utc)
        if body.template_id:
            opt = PromptOptimizer()
            await opt.record_template_usage(db, body.template_id, True)
        await increment_text_usage(db, user.id, result.tokens_used, result.cost_estimate)
    except HTTPException:
        raise
    except Exception as e:
        job.status = JobStatus.FAILED
        job.error_message = str(e)[:4000]
        job.completed_at = datetime.now(timezone.utc)
        await db.flush()
        raise HTTPException(status_code=500, detail=str(e)) from e

    await db.flush()
    return GenerateTextResponse(
        job_id=job.id,
        text=job.output_text or "",
        model_used=job.model_used,
        tokens_used=job.tokens_used,
        cost_estimate=job.cost_estimate,
        generation_time_ms=job.generation_time_ms,
        moderation=job.moderation_result,
    )


@router.post("/image", response_model=GenerateImageResponse)
async def generate_image(db: DbSession, user: CreatorUser, body: GenerateImageRequest) -> GenerateImageResponse:
    await check_image_quota(db, user.id, body.count)
    moderator = ContentModerator()
    pre = await moderator.moderate_prompt(body.prompt)
    if pre.decision == "block":
        raise HTTPException(status_code=400, detail="Prompt blocked by moderation")

    ig = ImageGenerator()
    paths: list[str] = []
    revised: list[str | None] = []
    model_used = body.model_override or ""

    job = GenerationJob(
        job_type=JobType.IMAGE,
        prompt_text=body.prompt,
        model_used=model_used or "image",
        status=JobStatus.GENERATING,
        created_by_id=user.id,
    )
    db.add(job)
    await db.flush()

    try:
        for _ in range(body.count):
            path, rev, m = await ig.generate(
                body.prompt,
                body.negative_prompt,
                body.size,
                body.style,
                body.quality,
                body.model_override,
                enhance=body.enhance_prompt,
            )
            model_used = m
            paths.append(path)
            revised.append(rev)
            db.add(
                ImageGeneration(
                    job_id=job.id,
                    prompt=body.prompt,
                    negative_prompt=body.negative_prompt,
                    model=m,
                    size=body.size,
                    style=body.style,
                    quality=body.quality,
                    image_path=path,
                    revised_prompt=rev,
                )
            )
        job.model_used = model_used
        job.status = JobStatus.COMPLETED
        job.output_image_path = paths[0] if paths else None
        job.output_metadata = {"paths": paths, "revised_prompts": revised}
        job.completed_at = datetime.now(timezone.utc)
        await increment_image_usage(db, user.id, body.count)
    except ImageGenerationError as e:
        job.status = JobStatus.FAILED
        job.error_message = str(e)
        job.completed_at = datetime.now(timezone.utc)
        await db.flush()
        raise HTTPException(status_code=502, detail=str(e)) from e

    await db.flush()
    return GenerateImageResponse(job_id=job.id, image_paths=paths, revised_prompts=revised, model_used=model_used)


@router.post("/code", response_model=GenerateCodeResponse)
async def generate_code_ep(db: DbSession, user: CreatorUser, body: GenerateCodeRequest) -> GenerateCodeResponse:
    await check_text_quota(db, user.id)
    cg = CodeGenerator()
    job = GenerationJob(
        job_type=JobType.CODE,
        prompt_text=body.description[:8000],
        model_used="",
        status=JobStatus.GENERATING,
        created_by_id=user.id,
    )
    db.add(job)
    await db.flush()
    try:
        out = await cg.generate_code(body.description, body.language, body.framework)
        job.status = JobStatus.COMPLETED
        job.model_used = out.model_used
        job.output_text = f"```\n{out.code}\n```\n\n{out.explanation}"
        job.tokens_used = out.tokens_used
        job.cost_estimate = out.cost_estimate
        job.generation_time_ms = out.generation_time_ms
        job.completed_at = datetime.now(timezone.utc)
        await increment_text_usage(db, user.id, out.tokens_used, out.cost_estimate)
    except Exception as e:
        job.status = JobStatus.FAILED
        job.error_message = str(e)
        job.completed_at = datetime.now(timezone.utc)
        await db.flush()
        raise HTTPException(status_code=500, detail=str(e)) from e
    await db.flush()
    return GenerateCodeResponse(
        job_id=job.id,
        code=out.code,
        explanation=out.explanation,
        model_used=out.model_used,
    )


@router.post("/batch", response_model=BatchGenerateResponse)
async def batch_generate(db: DbSession, user: CreatorUser, body: BatchGenerateRequest) -> BatchGenerateResponse:
    await check_batch_size(len(body.items))
    for it in body.items:
        if not it.prompt and not it.template_id:
            raise HTTPException(status_code=400, detail="Each item needs prompt or template_id")
    task = batch_generate_task.delay(
        user.id,
        [i.model_dump() for i in body.items],
        body.style_preset_id,
        body.model_override,
    )
    return BatchGenerateResponse(task_id=task.id, message="Batch queued for async processing")


@router.post("/stream")
async def stream_text(user: CreatorUser, body: StreamGenerateRequest):
    gen = TextGenerator()

    async def event_generator():
        async for chunk in gen.stream_generate(
            body.prompt,
            body.system_prompt,
            body.model_override,
            temperature=body.temperature or 0.7,
            max_tokens=body.max_tokens or 2048,
        ):
            yield {"data": chunk}

    return EventSourceResponse(event_generator())


@router.post("/structured")
async def generate_structured_ep(db: DbSession, user: CreatorUser, body: StructuredGenerateRequest) -> dict:
    await check_text_quota(db, user.id)
    gen = TextGenerator()
    data, meta = await gen.generate_structured(
        body.prompt,
        body.output_schema,
        system_prompt=body.system_prompt,
        model=body.model_override,
    )
    await increment_text_usage(db, user.id, meta.tokens_used, meta.cost_estimate)
    return {"data": data, "tokens_used": meta.tokens_used, "cost_estimate": meta.cost_estimate, "model_used": meta.model_used}


@router.post("/ab-inline")
async def ab_inline(user: CreatorUser, body: ABTestRequest) -> dict:
    opt = PromptOptimizer()
    gen = TextGenerator()
    r_a = await gen.generate(body.prompt_a + "\n\nInput:\n" + body.test_input, None, None, {})
    r_b = await gen.generate(body.prompt_b + "\n\nInput:\n" + body.test_input, None, None, {})
    winner, scores = await opt.ab_evaluate(r_a.text, r_b.text, body.evaluation_criteria)
    return {"winner": winner, "result_a": r_a.text, "result_b": r_b.text, "evaluation": scores}
