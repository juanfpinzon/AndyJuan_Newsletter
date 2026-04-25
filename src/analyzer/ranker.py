"""LLM-backed ranking for portfolio-relevant news."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable

from src.config import Settings, load_settings
from src.exposure.models import ExposureEntry
from src.fetcher.models import Article
from src.utils.llm import LLMResponse, call_openrouter

from ._prompting import parse_json_response, render_prompt

MAX_RANKER_TOKENS = 1200


class RankerResponseError(RuntimeError):
    """Raised when the ranker model returns unusable structured output."""


@dataclass(frozen=True)
class ArticleCandidate:
    article: Article
    matched_entities: tuple[str, ...]


@dataclass(frozen=True)
class RankedArticle:
    article: Article
    primary_entity: str | None
    matched_entities: tuple[str, ...]
    composite_weight: Decimal
    llm_score: int
    included_by: str
    rationale: str


LLMCaller = Callable[[str, str, int, str | None], LLMResponse]


def rank_news(
    articles: list[ArticleCandidate],
    exposure_map: dict[str, ExposureEntry],
    *,
    llm_caller: LLMCaller = call_openrouter,
    settings: Settings | None = None,
) -> list[RankedArticle]:
    """Rank candidate articles and enforce the exposure-threshold inclusion rule."""

    resolved_settings = settings or load_settings()
    prompt = render_prompt(
        "news_ranker.md",
        news_item_limit=resolved_settings.news_item_limit,
        exposure_threshold_percent=resolved_settings.exposure_threshold_percent,
        candidates_json=json.dumps(
            _serialize_candidates(articles, exposure_map),
            indent=2,
            sort_keys=True,
        ),
        exposure_map_json=json.dumps(
            _serialize_exposure_map(exposure_map),
            indent=2,
            sort_keys=True,
        ),
    )
    response = llm_caller(
        prompt,
        resolved_settings.llm_scoring_model,
        MAX_RANKER_TOKENS,
        resolved_settings.llm_fallback_model,
    )

    ranking = _parse_ranking_response(response.content, len(articles))
    ranked_window_ids = {
        record["article_id"]
        for record in ranking[: resolved_settings.news_item_limit]
    }
    threshold_weight = Decimal(str(resolved_settings.exposure_threshold_percent)) / 100
    ranking_lookup = {record["article_id"]: record for record in ranking}

    ranked_articles: list[RankedArticle] = []
    for index, candidate in enumerate(articles):
        article_id = str(index)
        primary_entity, composite_weight = _select_primary_entity(
            candidate.matched_entities,
            exposure_map,
        )
        record = ranking_lookup.get(
            article_id,
            {"score": 0, "rationale": "", "article_id": article_id},
        )
        included_by: str | None = None
        if article_id in ranked_window_ids:
            included_by = "rank"
        elif composite_weight >= threshold_weight:
            included_by = "threshold"

        if included_by is None:
            continue

        ranked_articles.append(
            RankedArticle(
                article=candidate.article,
                primary_entity=primary_entity,
                matched_entities=candidate.matched_entities,
                composite_weight=composite_weight,
                llm_score=record["score"],
                included_by=included_by,
                rationale=record["rationale"],
            )
        )

    ranked_articles.sort(
        key=lambda item: (
            -item.llm_score,
            -item.composite_weight,
            item.article.published_at,
            item.article.title,
        )
    )
    return ranked_articles


def _serialize_candidates(
    articles: list[ArticleCandidate],
    exposure_map: dict[str, ExposureEntry],
) -> list[dict[str, object]]:
    payload: list[dict[str, object]] = []
    for index, candidate in enumerate(articles):
        primary_entity, composite_weight = _select_primary_entity(
            candidate.matched_entities,
            exposure_map,
        )
        payload.append(
            {
                "article_id": str(index),
                "title": candidate.article.title,
                "body": candidate.article.body,
                "url": candidate.article.url,
                "source": candidate.article.source,
                "published_at": candidate.article.published_at,
                "matched_entities": list(candidate.matched_entities),
                "primary_entity": primary_entity,
                "composite_weight_percent": str(composite_weight * 100),
            }
        )
    return payload


def _serialize_exposure_map(
    exposure_map: dict[str, ExposureEntry]
) -> dict[str, dict[str, object]]:
    return {
        entity: {
            "composite_weight_percent": str(entry.composite_weight * 100),
            "paths": [
                {
                    "source": str(path["source"]),
                    "weight_percent": str(Decimal(str(path["weight"])) * 100),
                }
                for path in entry.paths
            ],
        }
        for entity, entry in exposure_map.items()
    }


def _parse_ranking_response(
    content: str,
    article_count: int,
) -> list[dict[str, object]]:
    try:
        payload = parse_json_response(content)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RankerResponseError("Ranker response was not valid JSON") from exc

    if not isinstance(payload, list):
        raise RankerResponseError("Ranker response must be a JSON list")

    ranking: list[dict[str, object]] = []
    for item in payload:
        if not isinstance(item, dict):
            raise RankerResponseError("Each ranker item must be an object")

        article_id = str(item.get("article_id", ""))
        if not article_id.isdigit():
            raise RankerResponseError("Ranker article_id must be a numeric string")
        if int(article_id) >= article_count:
            raise RankerResponseError(
                f"Unknown article_id returned by ranker: {article_id}"
            )

        ranking.append(
            {
                "article_id": article_id,
                "score": int(item.get("score", 0)),
                "rationale": str(item.get("rationale", "")).strip(),
            }
        )

    ranking.sort(
        key=lambda record: (-int(record["score"]), int(str(record["article_id"])))
    )
    return ranking


def _select_primary_entity(
    matched_entities: tuple[str, ...],
    exposure_map: dict[str, ExposureEntry],
) -> tuple[str | None, Decimal]:
    if not matched_entities:
        return None, Decimal("0")

    best_entity = matched_entities[0]
    best_weight = exposure_map.get(
        best_entity,
        _zero_exposure(best_entity),
    ).composite_weight
    for entity in matched_entities[1:]:
        weight = exposure_map.get(entity, _zero_exposure(entity)).composite_weight
        if weight > best_weight:
            best_entity = entity
            best_weight = weight
    return best_entity, best_weight


def _zero_exposure(entity: str) -> ExposureEntry:
    return ExposureEntry(entity=entity, composite_weight=Decimal("0"), paths=())
