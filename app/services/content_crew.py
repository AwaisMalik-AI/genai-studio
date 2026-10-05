"""Content crew: writer → editor → critic."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import settings


@dataclass
class CrewResult:
    crew: str = "content"
    used_llm: bool = False
    steps: list[dict[str, Any]] = field(default_factory=list)
    final: str = ""


def _llm(system: str, user: str) -> str | None:
    if not settings.LLM_API_KEY:
        return None
    try:
        url = "https://api.openai.com/v1/chat/completions"
        with httpx.Client(timeout=45.0) as client:
            resp = client.post(
                url,
                headers={"Authorization": f"Bearer {settings.LLM_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": settings.LLM_MODEL,
                    "temperature": 0.6,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
    except Exception:
        return None


class ContentCrew:
    def run(self, brief: str, style: str = "professional") -> CrewResult:
        draft = _llm(
            f"You write {style} content. Be specific and useful.",
            brief,
        ) or f"Draft ({style}): outline + 3 talking points for '{brief[:180]}'."
        edited = _llm(
            "You are an editor. Tighten structure, keep voice, cut fluff.",
            draft,
        ) or f"Edited: {draft} Add a clear CTA and shorter sentences."
        critique = _llm(
            "You are a critic. Score clarity, originality, brand risk.",
            edited,
        ) or "Critic: keep claims verifiable, vary sentence length, end with one CTA."
        return CrewResult(
            used_llm=bool(settings.LLM_API_KEY),
            steps=[
                {"agent": "writer", "output": draft},
                {"agent": "editor", "output": edited},
                {"agent": "critic", "output": critique},
            ],
            final=edited,
        )
