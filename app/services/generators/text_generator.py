"""Text generation: templates, structured JSON, streaming, and cost estimation."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

import tiktoken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.content import PromptTemplate, StylePreset
from app.services.llm_client import (
    LLMError,
    Timer,
    complete_chat,
    extract_token_usage,
    stream_openai_chat,
    usage_to_cost,
)
from app.services.template_render import render_template_text


@dataclass
class GeneratedText:
    text: str
    model_used: str
    tokens_used: int
    cost_estimate: float
    generation_time_ms: int
    raw_meta: dict[str, Any]


def _count_tokens_approx(text: str, model: str) -> int:
    try:
        enc = tiktoken.encoding_for_model(model)
    except Exception:
        enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text))


def _content_type_system_hint(content_type: str | None) -> str:
    if not content_type:
        return ""
    hints = {
        "blog_post": "Produce a well-structured blog post with headings and engaging flow.",
        "marketing_copy": "Produce concise, persuasive marketing copy with clear CTAs where appropriate.",
        "product_description": "Produce a clear, benefit-led product description suitable for e-commerce.",
        "email": "Produce a professional email draft with subject line suggestion if useful.",
        "social": "Produce punchy social media posts within platform-appropriate length.",
    }
    return hints.get(content_type.lower().replace(" ", "_"), "")


class TextGenerator:
    async def generate(
        self,
        prompt: str,
        system_prompt: str | None,
        model: str | None,
        config: dict[str, Any] | None = None,
        content_type: str | None = None,
    ) -> GeneratedText:
        cfg = config or {}
        temperature = float(cfg.get("temperature", 0.7))
        max_tokens = cfg.get("max_tokens")
        top_p = cfg.get("top_p")
        model_used = model or settings.LLM_MODEL
        extra = _content_type_system_hint(content_type)
        sys_parts = [p for p in (system_prompt, extra) if p]
        full_system = "\n\n".join(sys_parts) if sys_parts else None
        timer = Timer()
        try:
            text, meta = await complete_chat(
                system_prompt=full_system,
                user_prompt=prompt,
                model=model_used,
                temperature=temperature,
                max_tokens=int(max_tokens) if max_tokens is not None else 4096,
                top_p=float(top_p) if top_p is not None else None,
            )
        except LLMError:
            raise
        tokens = extract_token_usage(meta)
        if not tokens:
            tokens = _count_tokens_approx((full_system or "") + prompt + text, model_used)
        cost = usage_to_cost(model_used, meta)
        return GeneratedText(
            text=text,
            model_used=model_used,
            tokens_used=tokens,
            cost_estimate=round(cost, 6),
            generation_time_ms=timer.ms(),
            raw_meta=meta,
        )

    async def generate_with_template(
        self,
        db: AsyncSession,
        template_id: int,
        variables: dict[str, Any],
        style_preset_id: int | None,
        model_override: str | None = None,
        content_type: str | None = None,
        config_overrides: dict[str, Any] | None = None,
    ) -> tuple[GeneratedText, PromptTemplate]:
        result = await db.execute(select(PromptTemplate).where(PromptTemplate.id == template_id))
        tmpl = result.scalar_one_or_none()
        if not tmpl or not tmpl.is_active:
            raise ValueError("Template not found or inactive")
        rendered = render_template_text(tmpl.template_text, variables)
        sys_prompt = tmpl.system_prompt
        cfg = dict(tmpl.model_config_json or {})
        if config_overrides:
            cfg.update({k: v for k, v in config_overrides.items() if v is not None})
        if style_preset_id is not None:
            sp_result = await db.execute(select(StylePreset).where(StylePreset.id == style_preset_id))
            preset = sp_result.scalar_one_or_none()
            if preset and preset.config:
                mod = (preset.config.get("system_prompt_modifier") or "").strip()
                if mod:
                    sys_prompt = f"{sys_prompt or ''}\n\n{mod}".strip()
        gen = await self.generate(
            rendered,
            sys_prompt,
            model_override or cfg.get("model") or settings.LLM_MODEL,
            cfg,
            content_type=content_type,
        )
        return gen, tmpl

    async def generate_structured(
        self,
        prompt: str,
        output_schema: dict[str, Any],
        system_prompt: str | None = None,
        model: str | None = None,
    ) -> tuple[dict[str, Any], GeneratedText]:
        schema_str = json.dumps(output_schema, indent=2)
        sys = (system_prompt or "") + f"\n\nRespond with JSON only matching this schema:\n{schema_str}"
        model_used = model or settings.LLM_MODEL
        if settings.LLM_PROVIDER != "openai":
            sys += "\n\nOutput valid JSON object only, no markdown."
        timer = Timer()
        text, meta = await complete_chat(
            system_prompt=sys.strip(),
            user_prompt=prompt,
            model=model_used,
            temperature=0.2,
            max_tokens=4096,
            json_mode=(settings.LLM_PROVIDER == "openai"),
        )
        tokens = extract_token_usage(meta) or _count_tokens_approx(sys + prompt + text, model_used)
        cost = usage_to_cost(model_used, meta)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            start, end = text.find("{"), text.rfind("}")
            if start >= 0 and end > start:
                data = json.loads(text[start : end + 1])
            else:
                raise ValueError("Model did not return valid JSON") from None
        gen = GeneratedText(
            text=text,
            model_used=model_used,
            tokens_used=tokens,
            cost_estimate=round(cost, 6),
            generation_time_ms=timer.ms(),
            raw_meta=meta,
        )
        return data, gen

    async def stream_generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = 2048,
        top_p: float | None = None,
    ) -> AsyncGenerator[str, None]:
        model_used = model or settings.LLM_MODEL
        if settings.LLM_PROVIDER != "openai":
            full, _ = await complete_chat(
                system_prompt=system_prompt,
                user_prompt=prompt,
                model=model_used,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
            )
            yield full
            return
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        async for chunk in stream_openai_chat(messages, model_used, temperature, max_tokens, top_p):
            yield chunk
