"""LLM-assisted content moderation with category scores and allow/block/review decisions."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal

from app.core.config import settings
from app.services.llm_client import LLMError, complete_chat


Decision = Literal["allow", "block", "review"]


@dataclass
class ModerationResult:
    decision: Decision
    reasoning: str
    categories: dict[str, float]
    raw_response: str


class ContentModerator:
    _CATEGORIES = ("violence", "sexual", "hate", "self_harm", "illegal")

    async def moderate_text(self, text: str) -> ModerationResult:
        if not settings.CONTENT_MODERATION_ENABLED:
            return ModerationResult(
                decision="allow",
                reasoning="Moderation disabled via configuration.",
                categories={c: 0.0 for c in self._CATEGORIES},
                raw_response="",
            )
        return await self._analyze(text, context="user-facing generated or input text")

    async def moderate_prompt(self, prompt: str) -> ModerationResult:
        if not settings.CONTENT_MODERATION_ENABLED:
            return ModerationResult(
                decision="allow",
                reasoning="Moderation disabled via configuration.",
                categories={c: 0.0 for c in self._CATEGORIES},
                raw_response="",
            )
        return await self._analyze(prompt, context="prompt intended for a generative model")

    async def _analyze(self, content: str, context: str) -> ModerationResult:
        schema = {
            "decision": "allow | block | review",
            "reasoning": "short string",
            "scores": {c: "0.0-1.0 float" for c in self._CATEGORIES},
        }
        user = (
            f"Analyze the following {context} for policy risk.\n"
            f"Categories: {', '.join(self._CATEGORIES)}. "
            "Score each 0.0 (none) to 1.0 (severe). "
            "decision: 'block' if any serious policy violation is likely, "
            "'review' if uncertain or borderline, else 'allow'.\n\n"
            f"Content:\n---\n{content[:12000]}\n---\n\n"
            f"Respond with JSON only: {json.dumps(schema)}"
        )
        try:
            raw, _ = await complete_chat(
                system_prompt="You are a safety classifier. Be conservative for illegal and self-harm content.",
                user_prompt=user,
                temperature=0,
                max_tokens=600,
                json_mode=(settings.LLM_PROVIDER == "openai"),
            )
        except LLMError as e:
            return ModerationResult(
                decision="review",
                reasoning=f"Moderation service error: {e}",
                categories=dict.fromkeys(self._CATEGORIES, 0.5),
                raw_response=str(e),
            )
        data = self._parse_json(raw)
        decision = str(data.get("decision", "review")).lower()
        if decision not in ("allow", "block", "review"):
            decision = "review"
        scores_raw = data.get("scores") or {}
        categories = {}
        for c in self._CATEGORIES:
            try:
                categories[c] = float(scores_raw.get(c, 0.0))
            except (TypeError, ValueError):
                categories[c] = 0.0
        reasoning = str(data.get("reasoning", ""))[:2000]
        return ModerationResult(
            decision=decision,  # type: ignore[assignment]
            reasoning=reasoning,
            categories=categories,
            raw_response=raw,
        )

    @staticmethod
    def _parse_json(raw: str) -> dict[str, Any]:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            m = re.search(r"\{[\s\S]*\}", raw)
            if m:
                return json.loads(m.group(0))
            return {"decision": "review", "reasoning": "Unparseable moderation output", "scores": {}}
