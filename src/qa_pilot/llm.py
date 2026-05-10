"""LLM wrapper — provider-agnostic via litellm.

Why litellm: one call signature works against OpenAI, Anthropic, Gemini,
Groq, Cerebras, OpenRouter, Ollama, Together, and ~100 others. Users
bring their own key. We don't lock them in.

Two helpers:
  * complete(prompt, model)       — text → text
  * vision(prompt, image_path, model) — image + text → text
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
from pathlib import Path

from litellm import acompletion

logger = logging.getLogger("qa_pilot.llm")


DEFAULT_TEXT_MODEL = os.environ.get("QA_PILOT_TEXT_MODEL", "gpt-4o-mini")
DEFAULT_VISION_MODEL = os.environ.get("QA_PILOT_VISION_MODEL", "gpt-4o-mini")


async def complete(
    prompt: str,
    *,
    model: str | None = None,
    system: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 1500,
    timeout_sec: int = 60,
) -> str:
    """Single-shot completion. Returns the assistant's text content."""
    model = model or DEFAULT_TEXT_MODEL
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    try:
        resp = await asyncio.wait_for(
            acompletion(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            ),
            timeout=timeout_sec,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        logger.warning("complete(%s) failed: %s", model, e)
        return f"[LLM error: {type(e).__name__}: {e}]"


async def vision(
    prompt: str,
    image_path: Path | str,
    *,
    model: str | None = None,
    system: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 1500,
    timeout_sec: int = 60,
) -> str:
    """Vision completion: image + prompt → text. Used by Iris + Sage."""
    model = model or DEFAULT_VISION_MODEL
    p = Path(image_path)
    img_bytes = p.read_bytes()
    img_b64 = base64.b64encode(img_bytes).decode("ascii")
    suffix = (p.suffix or ".png").lstrip(".").lower()
    if suffix == "jpg":
        suffix = "jpeg"
    data_url = f"data:image/{suffix};base64,{img_b64}"

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({
        "role": "user",
        "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": data_url}},
        ],
    })

    try:
        resp = await asyncio.wait_for(
            acompletion(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            ),
            timeout=timeout_sec,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        logger.warning("vision(%s) failed: %s", model, e)
        return f"[LLM vision error: {type(e).__name__}: {e}]"
