"""Code generation, review, conversion, and explanation via LLM."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings
from app.services.llm_client import LLMError, Timer, complete_chat, extract_token_usage, usage_to_cost


@dataclass
class CodeResult:
    code: str
    explanation: str
    model_used: str
    tokens_used: int
    cost_estimate: float
    generation_time_ms: int


class CodeGenerator:
    async def generate_code(self, description: str, language: str, framework: str | None) -> CodeResult:
        fw = f"\nPreferred framework/library: {framework}" if framework else ""
        prompt = (
            f"Write production-quality {language} code for the following specification.\n"
            f"{description}{fw}\n\n"
            "Return a single markdown code block for the code, then a short explanation section titled 'Explanation:'."
        )
        return await self._run(prompt, system_prompt="You are an expert software engineer. Be concise and correct.")

    async def review_code(self, code: str, language: str) -> CodeResult:
        prompt = (
            f"Review this {language} code for bugs, security, performance, and style.\n"
            "Provide bullet-point findings and concrete suggestions.\n\n"
            f"```\n{code}\n```"
        )
        return await self._run(
            prompt,
            system_prompt="You are a senior code reviewer. Prioritize correctness and security.",
        )

    async def convert_code(self, code: str, source_lang: str, target_lang: str) -> CodeResult:
        prompt = (
            f"Convert the following {source_lang} code to {target_lang}. "
            "Preserve behavior. Output markdown code block then brief notes.\n\n"
            f"```\n{code}\n```"
        )
        return await self._run(prompt, system_prompt="You are an expert polyglot engineer.")

    async def explain_code(self, code: str) -> CodeResult:
        prompt = f"Explain this code in plain English for a skilled developer.\n\n```\n{code}\n```"
        return await self._run(prompt, system_prompt="You clarify code behavior clearly and accurately.")

    async def _run(self, user_prompt: str, system_prompt: str) -> CodeResult:
        model = settings.LLM_MODEL
        timer = Timer()
        try:
            text, meta = await complete_chat(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=model,
                temperature=0.3,
                max_tokens=8192,
            )
        except LLMError:
            raise
        tokens = extract_token_usage(meta) or 0
        cost = usage_to_cost(model, meta)
        code, expl = self._split_code_explanation(text)
        return CodeResult(
            code=code or text,
            explanation=expl or "",
            model_used=model,
            tokens_used=tokens,
            cost_estimate=round(cost, 6),
            generation_time_ms=timer.ms(),
        )

    @staticmethod
    def _split_code_explanation(text: str) -> tuple[str, str]:
        if "Explanation:" in text:
            parts = text.split("Explanation:", 1)
            return parts[0].strip(), parts[1].strip()
        return text.strip(), ""
