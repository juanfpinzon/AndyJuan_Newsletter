"""Per-theme AI flash generation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

from src.config import Settings, load_settings
from src.utils.llm import LLMResponse, call_openrouter

from ._prompting import count_sentences, render_prompt
from .ranker import RankedArticle

MAX_THEME_FLASH_TOKENS = 300


class ThemeFlashFormatError(RuntimeError):
    """Raised when the theme flash is not 1-2 sentences."""


@dataclass(frozen=True)
class ThemeFlash:
    theme: str
    text: str
    sentence_count: int


LLMCaller = Callable[[str, str, int, str | None], LLMResponse]


def generate_theme_flash(
    theme: str,
    articles: list[RankedArticle],
    *,
    llm_caller: LLMCaller = call_openrouter,
    settings: Settings | None = None,
) -> ThemeFlash:
    """Generate a short, grounded AI flash for a single theme."""

    resolved_settings = settings or load_settings()
    prompt = render_prompt(
        "theme_flash.md",
        theme=theme,
        articles_json=json.dumps(_serialize_ranked_articles(articles), indent=2),
    )
    response = llm_caller(
        prompt,
        resolved_settings.llm_synthesis_model,
        MAX_THEME_FLASH_TOKENS,
        resolved_settings.llm_fallback_model,
    )

    text = response.content.strip()
    sentence_count = count_sentences(text)
    if sentence_count not in (1, 2):
        raise ThemeFlashFormatError("Theme flash must be exactly 1 or 2 sentences")

    return ThemeFlash(theme=theme, text=text, sentence_count=sentence_count)


def _serialize_ranked_articles(
    articles: list[RankedArticle],
) -> list[dict[str, object]]:
    return [
        {
            "title": item.article.title,
            "primary_entity": item.primary_entity,
            "matched_entities": list(item.matched_entities),
            "composite_weight_percent": str(item.composite_weight * 100),
            "llm_score": item.llm_score,
            "rationale": item.rationale,
        }
        for item in articles
    ]
