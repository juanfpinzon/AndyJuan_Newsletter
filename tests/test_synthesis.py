import json
from decimal import Decimal
from pathlib import Path

import pytest

from src.analyzer.ranker import RankedArticle
from src.analyzer.synthesis import SynthesisFormatError, generate_synthesis
from src.analyzer.theme_flash import ThemeFlash
from src.config import Settings
from src.exposure.models import ExposureEntry
from src.fetcher.models import Article
from src.utils.llm import LLMResponse

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "llm" / "synthesis"


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
    return (FIXTURES_DIR / name / "response.txt").read_text(encoding="utf-8").strip()


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


def make_theme_flashes(items: list[dict[str, object]]) -> list[ThemeFlash]:
    return [
        ThemeFlash(
            theme=str(item["theme"]),
            text=str(item["text"]),
            sentence_count=int(item["sentence_count"]),
        )
        for item in items
    ]


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


def test_generate_synthesis_returns_cross_theme_paragraphs_and_suggestions() -> None:
    scenario = load_input("balanced_day")
    llm = FakeLLMCaller(load_response("balanced_day"))

    synthesis = generate_synthesis(
        make_theme_flashes(scenario["theme_flashes"]),
        make_ranked_articles(scenario["ranked_articles"]),
        make_exposure_map(scenario["exposure_map"]),
        llm_caller=llm,
        settings=make_settings(),
    )

    assert synthesis.text == load_response("balanced_day")
    assert synthesis.paragraphs == (
        "AI/Semis stayed in control of the tape, with Nvidia-linked demand "
        "headlines still driving the largest single-name exposure in the book.",
        "EU Banks added a separate rate-sensitive thread, so the day was not "
        "just about megacap tech.",
        "Watch Nvidia follow-through after supplier commentary, and Note that "
        "another move in European rate expectations can keep BNKE-sensitive "
        "names active.",
    )
    assert "no novel facts" in str(llm.calls[0]["prompt"]).lower()


def test_generate_synthesis_handles_a_second_fixture_shape() -> None:
    scenario = load_input("crowded_day")

    synthesis = generate_synthesis(
        make_theme_flashes(scenario["theme_flashes"]),
        make_ranked_articles(scenario["ranked_articles"]),
        make_exposure_map(scenario["exposure_map"]),
        llm_caller=FakeLLMCaller(load_response("crowded_day")),
        settings=make_settings(),
    )

    assert len(synthesis.paragraphs) == 3
    assert synthesis.paragraphs[-1].startswith("Watch")


def test_generate_synthesis_requires_watch_or_note_in_final_paragraph() -> None:
    scenario = load_input("balanced_day")

    with pytest.raises(SynthesisFormatError):
        generate_synthesis(
            make_theme_flashes(scenario["theme_flashes"]),
            make_ranked_articles(scenario["ranked_articles"]),
            make_exposure_map(scenario["exposure_map"]),
            llm_caller=FakeLLMCaller(
                "Paragraph one.\n\nParagraph two.\n\nFinal paragraph without "
                "the required keyword."
            ),
            settings=make_settings(),
        )
