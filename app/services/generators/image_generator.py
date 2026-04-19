"""Multi-provider image generation (DALL-E 3, Stability AI, Replicate) with local storage."""

from __future__ import annotations

import asyncio
import base64
import json
import uuid
from pathlib import Path
from typing import Any

import httpx
import aiofiles

from app.core.config import settings
from app.services.llm_client import LLMError, complete_chat


class ImageGenerationError(RuntimeError):
    pass


class ImageGenerator:
    def __init__(self) -> None:
        self._storage = Path(settings.STORAGE_PATH)
        self._storage.mkdir(parents=True, exist_ok=True)

    async def enhance_prompt(self, prompt: str, style: str | None = None) -> str:
        sys = (
            "You rewrite image generation prompts to be vivid, specific, and visually rich. "
            "Return only the improved prompt text, no quotes."
        )
        user = f"Original prompt:\n{prompt}\n"
        if style:
            user += f"Desired style hint: {style}\n"
        user += "Improved prompt:"
        try:
            text, _ = await complete_chat(system_prompt=sys, user_prompt=user, temperature=0.6, max_tokens=300)
            return text.strip() or prompt
        except LLMError:
            return prompt

    async def generate(
        self,
        prompt: str,
        negative_prompt: str | None,
        size: str,
        style: str | None,
        quality: str,
        model: str | None,
        enhance: bool = True,
    ) -> tuple[str, str | None, str]:
        """Returns (local_image_path, revised_prompt, model_used)."""
        use_prompt = await self.enhance_prompt(prompt, style) if enhance else prompt
        provider = settings.IMAGE_GEN_PROVIDER
        if provider == "openai_dalle":
            path, revised, m = await self._generate_dalle(use_prompt, size, quality, model)
            return path, revised, m
        if provider == "stability_ai":
            path, m = await self._generate_stability(use_prompt, negative_prompt, size, style, model)
            return path, None, m
        if provider == "replicate":
            path, m = await self._generate_replicate(use_prompt, negative_prompt, size, model)
            return path, None, m
        raise ImageGenerationError(f"Unknown IMAGE_GEN_PROVIDER: {provider}")

    def _new_filename(self, ext: str = "png") -> Path:
        name = f"{uuid.uuid4().hex}.{ext}"
        return self._storage / name

    async def _write_bytes(self, path: Path, data: bytes) -> str:
        path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(path, "wb") as f:
            await f.write(data)
        return str(path.resolve())

    async def _write_metadata(self, image_path: str, meta: dict[str, Any]) -> None:
        p = Path(image_path).with_suffix(Path(image_path).suffix + ".json")
        async with aiofiles.open(p, "w", encoding="utf-8") as f:
            await f.write(json.dumps(meta, indent=2))

    async def _generate_dalle(
        self,
        prompt: str,
        size: str,
        quality: str,
        model: str | None,
    ) -> tuple[str, str | None, str]:
        key = settings.IMAGE_GEN_API_KEY or settings.LLM_API_KEY
        if not key:
            raise ImageGenerationError("IMAGE_GEN_API_KEY or LLM_API_KEY required for DALL-E")
        m = model or "dall-e-3"
        url = "https://api.openai.com/v1/images/generations"
        body = {
            "model": m,
            "prompt": prompt[:4000],
            "size": size if size in ("1024x1024", "1792x1024", "1024x1792") else "1024x1024",
            "quality": quality if quality in ("standard", "hd") else "standard",
            "n": 1,
        }
        async with httpx.AsyncClient(timeout=180.0) as client:
            r = await client.post(
                url,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=body,
            )
            if r.status_code >= 400:
                raise ImageGenerationError(f"DALL-E API {r.status_code}: {r.text}")
            data = r.json()
        item = data["data"][0]
        b64 = item.get("b64_json")
        revised = item.get("revised_prompt")
        path = self._new_filename("png")
        if b64:
            raw = base64.b64decode(b64)
            out = await self._write_bytes(path, raw)
        else:
            img_url = item.get("url")
            if not img_url:
                raise ImageGenerationError("No image data in DALL-E response")
            async with httpx.AsyncClient(timeout=120.0) as client:
                ir = await client.get(img_url)
                ir.raise_for_status()
            out = await self._write_bytes(path, ir.content)
        await self._write_metadata(
            out,
            {"provider": "openai_dalle", "model": m, "prompt": prompt, "revised_prompt": revised},
        )
        return out, revised, m

    async def _generate_stability(
        self,
        prompt: str,
        negative_prompt: str | None,
        size: str,
        style: str | None,
        model: str | None,
    ) -> tuple[str, str]:
        key = settings.IMAGE_GEN_API_KEY
        if not key:
            raise ImageGenerationError("IMAGE_GEN_API_KEY required for Stability AI")
        # SD3 core text-to-image
        url = "https://api.stability.ai/v2beta/stable-image/generate/core"
        m = model or "sd3"
        headers = {"Authorization": f"Bearer {key}", "Accept": "image/*"}
        w, h = 1024, 1024
        if "x" in size:
            try:
                w, h = map(int, size.lower().split("x", 1))
            except ValueError:
                pass
        data = {
            "prompt": prompt[:10000],
            "output_format": "png",
            "width": str(min(max(w, 512), 1536)),
            "height": str(min(max(h, 512), 1536)),
        }
        if negative_prompt:
            data["negative_prompt"] = negative_prompt[:10000]
        if style:
            data["style_preset"] = style[:256]
        async with httpx.AsyncClient(timeout=180.0) as client:
            r = await client.post(url, headers=headers, data=data)
            if r.status_code >= 400:
                raise ImageGenerationError(f"Stability API {r.status_code}: {r.text}")
            content = r.content
        path = self._new_filename("png")
        out = await self._write_bytes(path, content)
        await self._write_metadata(
            out,
            {"provider": "stability_ai", "model": m, "prompt": prompt, "negative_prompt": negative_prompt},
        )
        return out, m

    async def _generate_replicate(
        self,
        prompt: str,
        negative_prompt: str | None,
        size: str,
        model: str | None,
    ) -> tuple[str, str]:
        token = settings.IMAGE_GEN_API_KEY
        if not token:
            raise ImageGenerationError("IMAGE_GEN_API_KEY required for Replicate")
        version = settings.REPLICATE_MODEL_VERSION or model
        if not version:
            raise ImageGenerationError("Set REPLICATE_MODEL_VERSION or model_override to a version id")
        w, h = 1024, 1024
        if "x" in size:
            try:
                w, h = map(int, size.lower().split("x", 1))
            except ValueError:
                pass
        create_url = "https://api.replicate.com/v1/predictions"
        headers = {"Authorization": f"Token {token}", "Content-Type": "application/json"}
        input_body: dict[str, Any] = {"prompt": prompt, "width": w, "height": h}
        if negative_prompt:
            input_body["negative_prompt"] = negative_prompt
        body = {"version": version, "input": input_body}
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(create_url, headers=headers, json=body)
            if r.status_code >= 400:
                raise ImageGenerationError(f"Replicate create {r.status_code}: {r.text}")
            pred = r.json()
            pred_url = pred["urls"]["get"]
            for _ in range(90):
                pr = await client.get(pred_url, headers=headers)
                pr.raise_for_status()
                pj = pr.json()
                st = pj.get("status")
                if st == "succeeded":
                    out_url = (pj.get("output") or [None])[0] if isinstance(pj.get("output"), list) else pj.get("output")
                    if not out_url:
                        raise ImageGenerationError("Replicate: no output URL")
                    ir = await client.get(out_url)
                    ir.raise_for_status()
                    path = self._new_filename("png")
                    saved = await self._write_bytes(path, ir.content)
                    await self._write_metadata(saved, {"provider": "replicate", "prompt": prompt})
                    return saved, version
                if st in ("failed", "canceled"):
                    raise ImageGenerationError(pj.get("error") or "Replicate prediction failed")
                await asyncio.sleep(2)
        raise ImageGenerationError("Replicate prediction timed out")
