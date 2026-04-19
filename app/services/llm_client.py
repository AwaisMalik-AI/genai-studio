"""LLM clients (OpenAI / Anthropic SDKs) + shared helpers for generators and moderation."""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from app.core.config import settings


class LLMError(RuntimeError):
    """Raised when an LLM provider returns an error or invalid response."""


def get_openai_client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=settings.LLM_API_KEY)


def get_anthropic_client() -> AsyncAnthropic:
    return AsyncAnthropic(api_key=settings.LLM_API_KEY)


async def chat_completion_openai(
    messages: list[dict[str, str]],
    model: str,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    top_p: float = 1.0,
    response_format: dict[str, str] | None = None,
) -> tuple[str, dict[str, Any] | None]:
    client = get_openai_client()
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "top_p": top_p,
    }
    if response_format:
        kwargs["response_format"] = response_format
    resp = await client.chat.completions.create(**kwargs)
    text = resp.choices[0].message.content or ""
    usage = None
    if resp.usage:
        usage = {
            "prompt_tokens": resp.usage.prompt_tokens,
            "completion_tokens": resp.usage.completion_tokens,
            "total_tokens": resp.usage.total_tokens,
        }
    return text, usage


async def chat_completion_anthropic(
    messages: list[dict[str, str]],
    model: str,
    system: str | None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    top_p: float = 1.0,
) -> tuple[str, dict[str, Any] | None]:
    client = get_anthropic_client()
    user_parts = []
    for m in messages:
        if m["role"] == "user":
            user_parts.append({"type": "text", "text": m["content"]})
    if not user_parts:
        user_parts = [{"type": "text", "text": ""}]
    resp = await client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
        system=system or "",
        messages=[{"role": "user", "content": user_parts}],
    )
    text = ""
    for block in resp.content:
        if hasattr(block, "text"):
            text += block.text
    usage = None
    if resp.usage:
        usage = {
            "input_tokens": resp.usage.input_tokens,
            "output_tokens": resp.usage.output_tokens,
            "total_tokens": resp.usage.input_tokens + resp.usage.output_tokens,
        }
    return text, usage


async def stream_openai(
    messages: list[dict[str, str]],
    model: str,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    top_p: float = 1.0,
) -> AsyncIterator[str]:
    client = get_openai_client()
    stream = await client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=top_p,
        stream=True,
    )
    async for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


async def stream_anthropic(
    messages: list[dict[str, str]],
    model: str,
    system: str | None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    top_p: float = 1.0,
) -> AsyncIterator[str]:
    client = get_anthropic_client()
    user_text = "\n".join(m["content"] for m in messages if m["role"] == "user")
    async with client.messages.stream(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
        system=system or "",
        messages=[{"role": "user", "content": user_text}],
    ) as stream:
        async for text in stream.text_stream:
            yield text


async def complete_chat(
    *,
    system_prompt: str | None,
    user_prompt: str,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int | None = 4096,
    top_p: float | None = None,
    json_mode: bool = False,
) -> tuple[str, dict[str, Any]]:
    model_used = model or settings.LLM_MODEL
    mt = max_tokens if max_tokens is not None else 4096
    tp = top_p if top_p is not None else 1.0
    try:
        if settings.LLM_PROVIDER == "openai":
            messages: list[dict[str, str]] = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": user_prompt})
            fmt = {"type": "json_object"} if json_mode else None
            text, usage = await chat_completion_openai(
                messages, model_used, temperature, mt, tp, fmt
            )
            return text, {"usage": usage or {}, "raw": {}}
        if settings.LLM_PROVIDER == "anthropic":
            text, usage = await chat_completion_anthropic(
                [{"role": "user", "content": user_prompt}],
                model_used,
                system_prompt,
                temperature,
                mt,
                tp,
            )
            if json_mode:
                text = text.strip()
            return text, {"usage": usage or {}, "raw": {}}
    except Exception as e:
        raise LLMError(str(e)) from e
    raise LLMError(f"Unsupported LLM_PROVIDER: {settings.LLM_PROVIDER}")


async def stream_openai_chat(
    messages: list[dict[str, str]],
    model: str,
    temperature: float,
    max_tokens: int | None,
    top_p: float | None,
) -> AsyncIterator[str]:
    mt = max_tokens if max_tokens is not None else 4096
    tp = top_p if top_p is not None else 1.0
    async for chunk in stream_openai(messages, model, temperature, mt, tp):
        yield chunk


def extract_token_usage(meta: dict[str, Any]) -> int:
    u = meta.get("usage") or {}
    if u.get("total_tokens") is not None:
        return int(u["total_tokens"])
    return int(u.get("prompt_tokens", 0) or u.get("input_tokens", 0)) + int(
        u.get("completion_tokens", 0) or u.get("output_tokens", 0)
    )


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    rates: dict[str, tuple[float, float]] = {
        "gpt-4o-mini": (0.15 / 1e6, 0.60 / 1e6),
        "gpt-4o": (2.50 / 1e6, 10.0 / 1e6),
        "claude-3-5-sonnet-20241022": (3.0 / 1e6, 15.0 / 1e6),
    }
    inp_r, out_r = rates.get(model, (0.5 / 1e6, 1.5 / 1e6))
    return prompt_tokens * inp_r + completion_tokens * out_r


def usage_to_cost(model: str, meta: dict[str, Any]) -> float:
    u = meta.get("usage") or {}
    pt = int(u.get("prompt_tokens") or u.get("input_tokens") or 0)
    ct = int(u.get("completion_tokens") or u.get("output_tokens") or 0)
    if not pt and not ct and u.get("total_tokens"):
        total = int(u["total_tokens"])
        pt, ct = total // 2, total - total // 2
    return estimate_cost_usd(model, pt, ct)


class Timer:
    def __init__(self) -> None:
        self._t0 = time.perf_counter()

    def ms(self) -> int:
        return int((time.perf_counter() - self._t0) * 1000)


async def http_post_json(url: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(url, headers=headers, json=payload)
        r.raise_for_status()
        return r.json()
