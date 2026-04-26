from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from src.analyzer.ranker import RankedArticle
from src.analyzer.theme_flash import ThemeFlash
from src.exposure.models import ExposureEntry
from src.fetcher.models import Article
from src.pnl.models import DailyDelta, PnLSnapshot
from src.renderer.theme_groups import (
    ConcentratedExposureRow,
    build_concentrated_exposures,
    build_theme_groups,
)


def test_build_theme_groups_caps_articles_and_uses_primary_theme(
    tmp_path: Path,
) -> None:
    themes_path = tmp_path / "themes.yaml"
    themes_path.write_text(
        "\n".join(
            [
                "themes:",
                "  AI/Semis:",
                "    description: Chips and AI infrastructure.",
                "  US Megacaps:",
                "    description: Large platform companies.",
                "entities:",
                "  NVDA:",
                "    primary_theme: AI/Semis",
                "    secondary_themes:",
                "      - US Megacaps",
                "  GOOGL:",
                "    primary_theme: US Megacaps",
                "    secondary_themes:",
                "      - AI/Semis",
                "  SPYY:",
                "    primary_theme: US Megacaps",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    ranked_articles = [
        _make_ranked_article(
            title=f"NVDA item {index}",
            primary_entity="NVDA",
            matched_entities=("NVDA",),
            composite_weight="0.08",
            llm_score=90 - index,
        )
        for index in range(6)
    ] + [
        _make_ranked_article(
            title="Alphabet spillover into chips",
            primary_entity="GOOGL",
            matched_entities=("GOOGL", "NVDA"),
            composite_weight="0.06",
            llm_score=81,
        )
    ]
    theme_groups = build_theme_groups(
        ranked_articles=ranked_articles,
        position_snapshots={
            "NVDA": _make_snapshot("NVDA"),
            "GOOGL": _make_snapshot("GOOGL"),
            "SPYY": _make_snapshot("SPYY"),
        },
        theme_flashes=[
            ThemeFlash(
                theme="AI/Semis", text="Semis are driving the tape.", sentence_count=1
            ),
            ThemeFlash(
                theme="US Megacaps",
                text="Megacaps remain bid on earnings resilience.",
                sentence_count=1,
            ),
        ],
        themes_path=themes_path,
        theme_item_cap=5,
    )

    assert [group.name for group in theme_groups] == ["AI/Semis", "US Megacaps"]
    ai_group = theme_groups[0]
    megacap_group = theme_groups[1]

    assert len(ai_group.articles) == 5
    assert "NVDA item 5" not in [article.title for article in ai_group.articles]

    assert [card.ticker for card in ai_group.cards] == ["NVDA"]
    assert [card.ticker for card in megacap_group.cards] == ["GOOGL", "SPYY"]

    assert "Alphabet spillover into chips" not in {
        article.title for article in ai_group.articles
    }
    assert [article.title for article in megacap_group.articles] == [
        "Alphabet spillover into chips"
    ]
    assert megacap_group.articles[0].affects_themes == ("AI/Semis",)
    assert megacap_group.flash_text == "Megacaps remain bid on earnings resilience."


def test_build_theme_groups_honors_zero_item_cap(tmp_path: Path) -> None:
    themes_path = tmp_path / "themes.yaml"
    themes_path.write_text(
        "\n".join(
            [
                "themes:",
                "  AI/Semis:",
                "    description: Chips and AI infrastructure.",
                "entities:",
                "  NVDA:",
                "    primary_theme: AI/Semis",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    theme_groups = build_theme_groups(
        ranked_articles=[
            _make_ranked_article(
                title="NVDA item",
                primary_entity="NVDA",
                matched_entities=("NVDA",),
                composite_weight="0.08",
                llm_score=90,
            )
        ],
        position_snapshots={"NVDA": _make_snapshot("NVDA")},
        theme_flashes=[],
        themes_path=themes_path,
        theme_item_cap=0,
    )

    assert len(theme_groups) == 1
    assert theme_groups[0].articles == ()
    assert [card.ticker for card in theme_groups[0].cards] == ["NVDA"]


def test_build_concentrated_exposures_uses_threshold_and_path_count() -> None:
    exposure_map = {
        "NVDA": ExposureEntry(
            entity="NVDA",
            composite_weight=Decimal("0.052"),
            paths=(
                {"source": "direct", "weight": Decimal("0.04")},
                {"source": "etf:QDVE", "weight": Decimal("0.012")},
            ),
        ),
        "AAPL": ExposureEntry(
            entity="AAPL",
            composite_weight=Decimal("0.031"),
            paths=({"source": "etf:SPYY", "weight": Decimal("0.031")},),
        ),
    }

    rows = build_concentrated_exposures(exposure_map, threshold_percent=Decimal("5"))

    assert rows == (
        ConcentratedExposureRow(
            entity="NVDA",
            composite_weight=Decimal("0.052"),
            path_count=2,
        ),
    )


def _make_ranked_article(
    *,
    title: str,
    primary_entity: str,
    matched_entities: tuple[str, ...],
    composite_weight: str,
    llm_score: int,
) -> RankedArticle:
    return RankedArticle(
        article=Article(
            title=title,
            body=f"{title} body",
            url=f"https://example.com/{title.lower().replace(' ', '-')}",
            source="Reuters",
            published_at="2026-04-26T07:30:00+00:00",
            raw_tags=(),
        ),
        primary_entity=primary_entity,
        matched_entities=matched_entities,
        composite_weight=Decimal(composite_weight),
        llm_score=llm_score,
        included_by="rank",
        rationale="Grounded by exposure",
    )


def _make_snapshot(ticker: str) -> PnLSnapshot:
    return PnLSnapshot(
        ticker=ticker,
        shares=Decimal("1"),
        cost_basis_total_eur=Decimal("100"),
        current_value_eur=Decimal("112.50"),
        total_pnl_eur=Decimal("12.50"),
        total_pnl_pct=Decimal("12.5"),
        daily_delta=DailyDelta(
            amount_eur=Decimal("1.25"),
            change_pct=Decimal("1.123"),
        ),
    )
