import json
from pathlib import Path

from src.config import load_settings
from src.entity_match.matcher import Article, EntityMatcher

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "news"


def load_labeled_articles() -> list[dict[str, str]]:
    return json.loads(
        (FIXTURES_DIR / "labeled_30.json").read_text(encoding="utf-8")
    )


def test_matcher_supports_ticker_and_alias_forms() -> None:
    matcher = EntityMatcher.from_themes_file()

    ticker_article = Article(
        title="$NVDA extends gains after earnings",
        body="Traders said NVDA demand remained strong across AI servers.",
        url="https://example.com/nvda",
        source="Fixture",
        published_at="2026-04-25T08:00:00Z",
        raw_tags=("NVDA",),
    )
    alias_article = Article(
        title="NVIDIA Corporation ramps Blackwell output",
        body="Analysts said Nvidia could ship more AI accelerators this quarter.",
        url="https://example.com/nvidia-alias",
        source="Fixture",
        published_at="2026-04-25T09:00:00Z",
        raw_tags=("Nvidia",),
    )

    ticker_matches = matcher.match(ticker_article)
    alias_matches = matcher.match(alias_article)

    assert ticker_matches[0].entity == "NVDA"
    assert ticker_matches[0].method == "ticker"
    assert alias_matches[0].entity == "NVDA"
    assert alias_matches[0].method == "alias"


def test_matcher_threshold_is_tunable_from_settings(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.yaml"
    settings_path.write_text(
        "\n".join(
            [
                "llm_scoring_model: primary-model",
                "llm_synthesis_model: synthesis-model",
                "llm_fact_check_model: fact-check-model",
                "llm_fallback_model: fallback-model",
                "database_path: data/test.db",
                "log_file: data/logs/test.jsonl",
                "news_item_limit: 15",
                "exposure_threshold_percent: 5.0",
                "entity_match_threshold: 101.0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    settings = load_settings(settings_path)
    matcher = EntityMatcher.from_themes_file(threshold=settings.entity_match_threshold)
    article = Article(
        title="$NVDA pops on AI demand",
        body="",
        url="https://example.com/nvda-threshold",
        source="Fixture",
        published_at="2026-04-25T10:00:00Z",
        raw_tags=(),
    )

    assert matcher.match(article) == []


def test_labeled_fixture_hits_accuracy_target() -> None:
    matcher = EntityMatcher.from_themes_file(
        threshold=load_settings().entity_match_threshold
    )
    labeled_articles = load_labeled_articles()

    correct = 0
    for item in labeled_articles:
        article = Article(
            title=item["title"],
            body=item["body"],
            url=item["url"],
            source=item["source"],
            published_at=item["published_at"],
            raw_tags=tuple(item.get("raw_tags", [])),
        )
        matches = matcher.match(article)
        if matches and matches[0].entity == item["expected_entity"]:
            correct += 1

    accuracy = correct / len(labeled_articles)

    assert accuracy >= 0.8
