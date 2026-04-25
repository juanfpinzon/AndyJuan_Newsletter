import json
from decimal import Decimal
from pathlib import Path

import pytest

from src.analyzer.ranker import ArticleCandidate, RankerResponseError, rank_news
from src.config import Settings
from src.exposure.models import ExposureEntry
from src.fetcher.models import Article
from src.utils.llm import LLMResponse

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "llm" / "ranker"


class FakeLLMCaller:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[dict[str, object]] = []

    def __call__(
        self,
        prompt: str,
        model: str,
        max_tokens: int,
        fallback_model: str | None = None,
    ) -> LLMResponse:
        self.calls.append(
            {
                "prompt": prompt,
                "model": model,
                "max_tokens": max_tokens,
                "fallback_model": fallback_model,
            }
        )
        return LLMResponse(
            content=self.content,
            model=model,
            tokens_in=0,
            tokens_out=0,
            cost_usd=0.0,
        )


def load_input(name: str) -> dict[str, object]:
    path = FIXTURES_DIR / name / "input.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_response(name: str) -> str:
    return (FIXTURES_DIR / name / "response.txt").read_text(encoding="utf-8")


def make_settings(
    *,
    news_item_limit: int = 2,
    exposure_threshold_percent: float = 5.0,
) -> Settings:
    return Settings(
        llm_scoring_model="anthropic/claude-haiku-4.5",
        llm_synthesis_model="anthropic/claude-sonnet-4-6",
        llm_fact_check_model="anthropic/claude-haiku-4.5",
        llm_fallback_model="anthropic/claude-haiku-4.5",
        database_path="data/test.db",
        log_file="data/logs/test.jsonl",
        news_item_limit=news_item_limit,
        exposure_threshold_percent=exposure_threshold_percent,
        entity_match_threshold=85.0,
    )


def make_candidates(items: list[dict[str, object]]) -> list[ArticleCandidate]:
    return [
        ArticleCandidate(
            article=Article(
                title=str(item["title"]),
                body=str(item["body"]),
                url=str(item["url"]),
                source=str(item["source"]),
                published_at=str(item["published_at"]),
                raw_tags=tuple(str(tag) for tag in item.get("raw_tags", [])),
            ),
            matched_entities=tuple(
                str(entity) for entity in item.get("matched_entities", [])
            ),
        )
        for item in items
    ]


def make_exposure_map(
    payload: dict[str, dict[str, object]]
) -> dict[str, ExposureEntry]:
    return {
        entity: ExposureEntry(
            entity=entity,
            composite_weight=Decimal(str(entry["composite_weight"])),
            paths=tuple(
                {
                    "source": str(path["source"]),
                    "weight": Decimal(str(path["weight"])),
                }
                for path in entry["paths"]
            ),
        )
        for entity, entry in payload.items()
    }


def serialize_ranked_articles(items) -> list[dict[str, object]]:
    return [
        {
            "title": item.article.title,
            "primary_entity": item.primary_entity,
            "matched_entities": list(item.matched_entities),
            "composite_weight": str(item.composite_weight),
            "llm_score": item.llm_score,
            "included_by": item.included_by,
            "rationale": item.rationale,
        }
        for item in items
    ]


def test_rank_news_keeps_high_exposure_articles_outside_rank_window() -> None:
    scenario = load_input("threshold_boundary")
    llm = FakeLLMCaller(load_response("threshold_boundary"))

    ranked = rank_news(
        make_candidates(scenario["articles"]),
        make_exposure_map(scenario["exposure_map"]),
        llm_caller=llm,
        settings=make_settings(news_item_limit=2),
    )

    assert serialize_ranked_articles(ranked) == [
        {
            "title": "Nvidia suppliers rally on AI server demand",
            "primary_entity": "NVDA",
            "matched_entities": ["NVDA"],
            "composite_weight": "0.04",
            "llm_score": 92,
            "included_by": "rank",
            "rationale": "Direct AI exposure keeps this headline most material.",
        },
        {
            "title": "Gold miners slip despite firmer bullion",
            "primary_entity": "GDX",
            "matched_entities": ["GDX"],
            "composite_weight": "0.02",
            "llm_score": 78,
            "included_by": "rank",
            "rationale": "Gold miners matter, but the portfolio weight is smaller.",
        },
        {
            "title": "European banks extend gains on rates repricing",
            "primary_entity": "BNKE",
            "matched_entities": ["BNKE"],
            "composite_weight": "0.06",
            "llm_score": 40,
            "included_by": "threshold",
            "rationale": "Banks matter mainly because the ETF is concentrated.",
        },
    ]
    assert "top 2" in str(llm.calls[0]["prompt"])
    assert "Nvidia suppliers rally on AI server demand" in str(llm.calls[0]["prompt"])


def test_rank_news_limits_output_to_rank_window_when_threshold_adds_nothing() -> None:
    scenario = load_input("top_window_only")
    llm = FakeLLMCaller(load_response("top_window_only"))

    ranked = rank_news(
        make_candidates(scenario["articles"]),
        make_exposure_map(scenario["exposure_map"]),
        llm_caller=llm,
        settings=make_settings(news_item_limit=2),
    )

    assert serialize_ranked_articles(ranked) == [
        {
            "title": "Alphabet ad rebound steadies megacap sentiment",
            "primary_entity": "GOOGL",
            "matched_entities": ["GOOGL"],
            "composite_weight": "0.045",
            "llm_score": 95,
            "included_by": "rank",
            "rationale": "Megacap ad data matters immediately for direct exposure.",
        },
        {
            "title": "Nvidia software partners extend AI momentum",
            "primary_entity": "NVDA",
            "matched_entities": ["NVDA"],
            "composite_weight": "0.04",
            "llm_score": 89,
            "included_by": "rank",
            "rationale": "The headline reinforces the biggest AI-linked position.",
        },
    ]


def test_rank_news_rejects_invalid_json() -> None:
    scenario = load_input("threshold_boundary")

    with pytest.raises(RankerResponseError):
        rank_news(
            make_candidates(scenario["articles"]),
            make_exposure_map(scenario["exposure_map"]),
            llm_caller=FakeLLMCaller("not-json"),
            settings=make_settings(),
        )
