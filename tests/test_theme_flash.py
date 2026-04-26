import json
from decimal import Decimal
from pathlib import Path

from src.analyzer.ranker import RankedArticle
from src.analyzer.theme_flash import generate_theme_flash
from src.config import Settings
from src.fetcher.models import Article
from src.utils.llm import LLMResponse

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "llm" / "theme_flash"


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


def make_settings() -> Settings:
    return Settings(
        llm_scoring_model="anthropic/claude-haiku-4.5",
        llm_synthesis_model="anthropic/claude-sonnet-4-6",
        llm_fact_check_model="anthropic/claude-haiku-4.5",
        llm_fallback_model="anthropic/claude-haiku-4.5",
        database_path="data/test.db",
        log_file="data/logs/test.jsonl",
        news_item_limit=15,
        exposure_threshold_percent=5.0,
        entity_match_threshold=85.0,
    )


def make_ranked_articles(items: list[dict[str, object]]) -> list[RankedArticle]:
    return [
        RankedArticle(
            article=Article(
                title=str(item["title"]),
                body=str(item.get("body", "")),
                url=str(item.get("url", f"https://example.com/{index}")),
                source=str(item.get("source", "Fixture")),
                published_at=str(item.get("published_at", "2026-04-25T00:00:00Z")),
                raw_tags=tuple(str(tag) for tag in item.get("raw_tags", [])),
            ),
            primary_entity=str(item.get("primary_entity") or ""),
            matched_entities=(str(item.get("primary_entity") or ""),),
            composite_weight=Decimal(str(item["composite_weight"])),
            llm_score=int(item.get("llm_score", 80)),
            included_by=str(item.get("included_by", "rank")),
            rationale=str(item.get("rationale", "Fixture rationale.")),
        )
        for index, item in enumerate(items)
    ]


def test_generate_theme_flash_returns_one_or_two_sentences() -> None:
    scenario = load_input("ai_semis")
    llm = FakeLLMCaller(load_response("ai_semis"))

    flash = generate_theme_flash(
        str(scenario["theme"]),
        make_ranked_articles(scenario["articles"]),
        llm_caller=llm,
        settings=make_settings(),
    )

    assert flash.theme == "AI/Semis"
    assert flash.text == (
        "AI and semiconductor exposure stayed in focus after fresh demand and "
        "spending headlines. Nvidia remains the clearest read-through for the book."
    )
    assert flash.sentence_count == 2
    assert "AI/Semis" in str(llm.calls[0]["prompt"])


def test_generate_theme_flash_handles_single_sentence_output() -> None:
    scenario = load_input("defense_macro_mix")

    flash = generate_theme_flash(
        str(scenario["theme"]),
        make_ranked_articles(scenario["articles"]),
        llm_caller=FakeLLMCaller(load_response("defense_macro_mix")),
        settings=make_settings(),
    )

    assert flash.theme == "Defense"
    assert flash.sentence_count == 1


def test_generate_theme_flash_truncates_three_sentences_to_two() -> None:
    scenario = load_input("ai_semis")

    flash = generate_theme_flash(
        str(scenario["theme"]),
        make_ranked_articles(scenario["articles"]),
        llm_caller=FakeLLMCaller("One sentence. Two sentence. Three sentence."),
        settings=make_settings(),
    )

    assert flash.text == "One sentence. Two sentence."
    assert flash.sentence_count == 2
