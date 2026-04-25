"""Bottom-of-email AI synthesis generation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Callable

from src.config import Settings, load_settings
from src.exposure.models import ExposureEntry
from src.utils.llm import LLMResponse, call_openrouter

from ._prompting import render_prompt, split_paragraphs
from .ranker import RankedArticle
from .theme_flash import ThemeFlash

MAX_SYNTHESIS_TOKENS = 700
SUGGESTION_RE = re.compile(r"\b(?:Watch|Note)\b", re.IGNORECASE)


class SynthesisFormatError(RuntimeError):
    """Raised when the synthesis output does not match the expected shape."""


@dataclass(frozen=True)
class Synthesis:
    text: str
    paragraphs: tuple[str, ...]


LLMCaller = Callable[[str, str, int, str | None], LLMResponse]


def generate_synthesis(
    theme_flashes: list[ThemeFlash],
    ranked_articles: list[RankedArticle],
    exposure_map: dict[str, ExposureEntry],
    *,
    llm_caller: LLMCaller = call_openrouter,
    settings: Settings | None = None,
) -> Synthesis:
    """Generate grounded, cross-theme synthesis paragraphs."""

    resolved_settings = settings or load_settings()
    prompt = render_prompt(
        "ai_synthesis.md",
        theme_flashes_json=json.dumps(
            _serialize_theme_flashes(theme_flashes),
            indent=2,
        ),
        ranked_articles_json=json.dumps(
            _serialize_ranked_articles(ranked_articles),
            indent=2,
        ),
        exposure_map_json=json.dumps(
            _serialize_exposure_map(exposure_map),
            indent=2,
            sort_keys=True,
        ),
    )
    response = llm_caller(
        prompt,
        resolved_settings.llm_synthesis_model,
        MAX_SYNTHESIS_TOKENS,
        resolved_settings.llm_fallback_model,
    )

    text = response.content.strip()
    paragraphs = split_paragraphs(text)
    if len(paragraphs) < 3:
        raise SynthesisFormatError("Synthesis must contain at least 3 paragraphs")
    if not SUGGESTION_RE.search(paragraphs[-1]):
        raise SynthesisFormatError(
            "Final synthesis paragraph must contain a Watch or Note suggestion"
        )

    return Synthesis(text=text, paragraphs=paragraphs)


def _serialize_theme_flashes(
    theme_flashes: list[ThemeFlash],
) -> list[dict[str, object]]:
    return [
        {
            "theme": item.theme,
            "text": item.text,
            "sentence_count": item.sentence_count,
        }
        for item in theme_flashes
    ]


def _serialize_ranked_articles(
    ranked_articles: list[RankedArticle],
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
        for item in ranked_articles
    ]


def _serialize_exposure_map(
    exposure_map: dict[str, ExposureEntry]
) -> dict[str, dict[str, object]]:
    return {
        entity: {
            "composite_weight_percent": str(entry.composite_weight * 100),
            "paths": [
                {
                    "source": str(path["source"]),
                    "weight_percent": str(path["weight"] * 100),
                }
                for path in entry.paths
            ],
        }
        for entity, entry in exposure_map.items()
    }
