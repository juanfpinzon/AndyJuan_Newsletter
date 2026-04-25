"""OpenRouter-backed LLM utilities."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openai import OpenAI

from src.storage.db import record_llm_call

DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_DATABASE_PATH = Path("data/andyjuan.db")


@dataclass(frozen=True)
class LLMResponse:
    content: str
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: float


def call_openrouter(
    prompt: str,
    model: str,
    max_tokens: int,
    fallback_model: str | None = None,
    *,
    client: Any | None = None,
    db_path: str | Path | None = None,
) -> LLMResponse:
    """Call OpenRouter, optionally retrying once with a fallback model."""

    resolved_client = client or get_openrouter_client()
    resolved_db_path = Path(
        db_path or os.getenv("DATABASE_PATH", str(DEFAULT_DATABASE_PATH))
    )

    models_to_try = [model]
    if fallback_model and fallback_model != model:
        models_to_try.append(fallback_model)

    last_error: Exception | None = None
    for selected_model in models_to_try:
        try:
            completion = resolved_client.chat.completions.create(
                model=selected_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
            )
        except Exception as exc:  # noqa: BLE001
            record_llm_call(
                resolved_db_path,
                model=selected_model,
                prompt=prompt,
                tokens_in=0,
                tokens_out=0,
                cost_usd=0.0,
                success=False,
                error=str(exc),
            )
            last_error = exc
            continue

        response = _build_response(completion)
        record_llm_call(
            resolved_db_path,
            model=response.model,
            prompt=prompt,
            tokens_in=response.tokens_in,
            tokens_out=response.tokens_out,
            cost_usd=response.cost_usd,
            success=True,
        )
        return response

    if last_error is not None:
        raise last_error
    raise RuntimeError("OpenRouter call failed without a captured exception")


def get_openrouter_client() -> OpenAI:
    """Construct the OpenRouter client."""

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    base_url = os.getenv("OPENROUTER_BASE_URL", DEFAULT_OPENROUTER_BASE_URL)
    return OpenAI(api_key=api_key, base_url=base_url)


def _build_response(completion: Any) -> LLMResponse:
    usage = getattr(completion, "usage", None)
    return LLMResponse(
        content=_extract_content(completion),
        model=str(getattr(completion, "model", "")),
        tokens_in=int(getattr(usage, "prompt_tokens", 0) or 0),
        tokens_out=int(getattr(usage, "completion_tokens", 0) or 0),
        cost_usd=float(_extract_cost_usd(usage)),
    )


def _extract_content(completion: Any) -> str:
    choices = getattr(completion, "choices", [])
    if not choices:
        return ""

    message = getattr(choices[0], "message", None)
    if message is None:
        return ""

    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in content
        )
    return str(content)


def _extract_cost_usd(usage: Any) -> float:
    if usage is None:
        return 0.0

    for attribute in ("cost", "cost_usd"):
        value = getattr(usage, attribute, None)
        if value is not None:
            return float(value)
    return 0.0
