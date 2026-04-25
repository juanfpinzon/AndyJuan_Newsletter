"""Fail-closed fact checking for AI commentary blocks."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

from src.config import Settings, load_settings
from src.utils.llm import LLMResponse, call_openrouter
from src.utils.log import get_logger

from ._prompting import parse_json_response, render_prompt

MAX_FACT_CHECK_TOKENS = 400
INVALID_RESPONSE_CLAIM = "Invalid fact-checker response"
UNVERIFIED_CLAIM = "Unverified AI take"


@dataclass(frozen=True)
class FactCheckResult:
    ok: bool
    flagged_claims: tuple[str, ...]


LLMCaller = Callable[[str, str, int, str | None], LLMResponse]


def fact_check_ai_take(
    rendered_content: str,
    ai_take_text: str,
    *,
    llm_caller: LLMCaller = call_openrouter,
    settings: Settings | None = None,
) -> FactCheckResult:
    """Verify that an AI take does not introduce unsupported claims."""

    resolved_settings = settings or load_settings()
    prompt = render_prompt(
        "fact_checker.md",
        rendered_content=rendered_content,
        ai_take_text=ai_take_text,
    )
    response = llm_caller(
        prompt,
        resolved_settings.llm_fact_check_model,
        MAX_FACT_CHECK_TOKENS,
        resolved_settings.llm_fallback_model,
    )
    return _parse_fact_check_result(response.content)


def filter_ai_take(
    rendered_content: str,
    ai_take_text: str,
    *,
    llm_caller: LLMCaller = call_openrouter,
    settings: Settings | None = None,
) -> str | None:
    """Return the AI take when grounded; otherwise omit it and log a warning."""

    result = fact_check_ai_take(
        rendered_content,
        ai_take_text,
        llm_caller=llm_caller,
        settings=settings,
    )
    if result.ok:
        return ai_take_text

    get_logger("fact_checker").warning(
        "ai_take_blocked",
        flagged_claims=list(result.flagged_claims),
        ai_take_text=ai_take_text,
    )
    return None


def _parse_fact_check_result(content: str) -> FactCheckResult:
    try:
        payload = parse_json_response(content)
    except (TypeError, ValueError, json.JSONDecodeError):
        return FactCheckResult(ok=False, flagged_claims=(INVALID_RESPONSE_CLAIM,))

    if not isinstance(payload, dict):
        return FactCheckResult(ok=False, flagged_claims=(INVALID_RESPONSE_CLAIM,))

    ok = bool(payload.get("ok"))
    flagged_claims = _normalize_flagged_claims(payload.get("flagged_claims"))
    if not ok and not flagged_claims:
        flagged_claims = (UNVERIFIED_CLAIM,)

    return FactCheckResult(ok=ok, flagged_claims=flagged_claims)


def _normalize_flagged_claims(raw_value: object) -> tuple[str, ...]:
    if isinstance(raw_value, str):
        claim = raw_value.strip()
        return (claim,) if claim else ()
    if not isinstance(raw_value, list):
        return ()

    claims = tuple(str(item).strip() for item in raw_value if str(item).strip())
    return claims
