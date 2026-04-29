from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from src.analyzer.theme_flash import ThemeFlash
from src.exposure.models import ExposureEntry
from src.renderer import build_concentrated_exposures, build_theme_groups
from src.renderer.render import RenderValidationError, render_email


def test_render_email_renders_all_sections_with_plain_text() -> None:
    rendered = render_email(_sample_context(), mode="daily")

    soup = BeautifulSoup(rendered.html, "html.parser")
    sections = [
        element["data-section"]
        for element in soup.select("[data-section]")
        if element.name == "section"
    ]

    assert sections == [
        "hero",
        "pnl-scoreboard",
        "concentrated-exposures",
        "theme-groups",
        "ai-synthesis",
        "macro-footer",
    ]
    assert rendered.word_count <= 1000
    assert rendered.text
    assert "Daily Portfolio Radar" in rendered.text
    assert "AI-generated" in rendered.text

    article_links = soup.select(".news-item a")
    assert article_links
    assert all(link.get("href") for link in article_links)
    assert rendered.html.count("🤖 AI-generated · not investment advice") == 3
    assert "Affects" in rendered.html


def test_render_email_accepts_renderer_dataclasses(tmp_path: Path) -> None:
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
    context = _sample_context()
    context["theme_groups"] = build_theme_groups(
        ranked_articles=[
            _make_theme_group_article(
                title="Nvidia suppliers signal firm AI demand",
                primary_entity="NVDA",
                composite_weight="0.13",
            )
        ],
        position_snapshots={"NVDA": _make_snapshot("NVDA")},
        theme_flashes=[
            ThemeFlash(
                theme="AI/Semis",
                text="AI hardware demand remains broadening across the supply chain.",
                sentence_count=1,
            )
        ],
        themes_path=themes_path,
    )
    context["concentrated_exposures"] = build_concentrated_exposures(
        {
            "NVDA": ExposureEntry(
                entity="NVDA",
                composite_weight=Decimal("0.13"),
                paths=(
                    {"source": "direct", "weight": Decimal("0.10")},
                    {"source": "etf:QDVE", "weight": Decimal("0.03")},
                ),
            )
        },
        threshold_percent=Decimal("5"),
    )

    rendered = render_email(context, mode="daily")

    assert "07:30 UTC" in rendered.html
    assert "13.00%" in rendered.html
    assert "€112.50" in rendered.html


def test_render_email_rejects_blank_news_href() -> None:
    context = _sample_context()
    context["theme_groups"][0]["articles"][0]["href"] = ""

    with pytest.raises(RenderValidationError, match="href"):
        render_email(context, mode="daily")


def test_render_email_rejects_blank_macro_href() -> None:
    context = _sample_context()
    context["macro_items"][0]["href"] = ""

    with pytest.raises(RenderValidationError, match="href"):
        render_email(context, mode="daily")


def test_render_email_rejects_unsupported_mode() -> None:
    with pytest.raises(RenderValidationError, match="Unsupported render mode"):
        render_email(_sample_context(), mode="weekly")


def test_render_email_shows_macro_fallback_when_items_are_missing() -> None:
    context = _sample_context()
    context["macro_items"] = []
    fallback = "No fresh macro items cleared the last 24h window."

    rendered = render_email(context, mode="daily")

    soup = BeautifulSoup(rendered.html, "html.parser")
    macro_section = soup.select_one("[data-section='macro-footer']")

    assert macro_section is not None
    assert fallback in rendered.text
    assert fallback in macro_section.get_text(" ", strip=True)


def test_render_email_supports_deep_mode_week_ahead_section() -> None:
    rendered = render_email(_sample_context(), mode="deep")

    soup = BeautifulSoup(rendered.html, "html.parser")
    week_ahead = soup.select_one("[data-section='week-ahead']")

    assert week_ahead is not None
    assert "Week Ahead" in week_ahead.get_text(" ", strip=True)
    assert "Saturday deep mode extends the synthesis" in rendered.text


def test_render_email_deep_mode_shows_week_ahead_fallback() -> None:
    context = _sample_context()
    context["week_ahead_items"] = []

    rendered = render_email(context, mode="deep")

    soup = BeautifulSoup(rendered.html, "html.parser")
    week_ahead = soup.select_one("[data-section='week-ahead']")

    assert week_ahead is not None
    assert "No week-ahead items were supplied for this Saturday run." in rendered.text
    assert (
        "No week-ahead items were supplied for this Saturday run."
        in week_ahead.get_text(" ", strip=True)
    )


def _sample_context() -> dict[str, object]:
    return {
        "title": "Daily Portfolio Radar",
        "subtitle": "Position-aware brief for Juan and Andrea",
        "mode_label": "Daily",
        "generated_for_date": "April 26, 2026",
        "total_pnl": {
            "current_value_total_eur": "€2,760.68",
            "total_pnl_eur": "+€67.52",
            "total_pnl_pct": "+2.51%",
            "daily_pnl_eur": "+€0.14",
        },
        "position_rows": [
            {
                "ticker": "NVDA",
                "current_value_eur": "€412.12",
                "total_pnl_pct": "+14.2%",
                "daily_change_pct": "+1.1%",
                "theme": "AI/Semis",
            },
            {
                "ticker": "GOOGL",
                "current_value_eur": "€389.40",
                "total_pnl_pct": "+6.4%",
                "daily_change_pct": "+0.3%",
                "theme": "US Megacaps",
            },
        ],
        "concentrated_exposures": [
            {
                "entity": "NVDA",
                "composite_weight_percent": "13.00%",
                "path_count": 2,
            },
            {
                "entity": "GOOGL",
                "composite_weight_percent": "9.10%",
                "path_count": 1,
            },
        ],
        "theme_groups": [
            {
                "name": "AI/Semis",
                "description": (
                    "Semiconductor leaders and AI infrastructure beneficiaries."
                ),
                "cards": [
                    {
                        "ticker": "NVDA",
                        "current_value_eur": "€412.12",
                        "total_pnl_pct": "+14.2%",
                        "daily_change_pct": "+1.1%",
                    }
                ],
                "articles": [
                    {
                        "title": "Nvidia suppliers signal firm AI demand",
                        "source": "Reuters",
                        "href": "https://example.com/nvda-demand",
                        "published_at_label": "07:15 UTC",
                        "primary_entity": "NVDA",
                        "composite_weight_percent": "13.00%",
                        "affects_themes": ["US Megacaps"],
                    }
                ],
                "flash_text": (
                    "AI hardware demand remains broadening across the supply chain."
                ),
            },
            {
                "name": "US Megacaps",
                "description": (
                    "Large-cap U.S. platform and index-heavy equity exposure."
                ),
                "cards": [
                    {
                        "ticker": "GOOGL",
                        "current_value_eur": "€389.40",
                        "total_pnl_pct": "+6.4%",
                        "daily_change_pct": "+0.3%",
                    }
                ],
                "articles": [
                    {
                        "title": "Alphabet leans into cloud efficiency",
                        "source": "FT",
                        "href": "https://example.com/googl-cloud",
                        "published_at_label": "06:40 UTC",
                        "primary_entity": "GOOGL",
                        "composite_weight_percent": "9.10%",
                        "affects_themes": [],
                    }
                ],
                "flash_text": (
                    "Megacap cash generation still cushions valuation pressure."
                ),
            },
        ],
        "synthesis_paragraphs": [
            (
                "AI and platform exposure remain the main drivers of portfolio "
                "sensitivity."
            ),
            "Cross-theme spillovers still cluster around mega-cap demand signals.",
            "Watch whether macro rate repricing changes the breadth of leadership.",
        ],
        "deep_synthesis_paragraphs": [
            (
                "Saturday deep mode extends the synthesis with more context on "
                "where portfolio sensitivity is clustering."
            ),
            (
                "The current balance still leans on AI infrastructure demand, "
                "but the macro hedge role of metals matters more when rate "
                "pricing shifts."
            ),
            (
                "Into next week, the key question is whether leadership broadens "
                "or whether conviction remains concentrated in the same growth "
                "factors."
            ),
        ],
        "macro_items": [
            {
                "title": "ECB speakers keep rate path data-dependent",
                "source": "ECB",
                "href": "https://example.com/ecb-rates",
                "published_at_label": "05:50 UTC",
            }
        ],
        "week_ahead_items": [
            {
                "date_label": "Mon",
                "label": "Eurozone CPI flash",
                "kind": "Macro",
            }
        ],
    }


def _make_theme_group_article(
    *,
    title: str,
    primary_entity: str,
    composite_weight: str,
):
    from src.analyzer.ranker import RankedArticle
    from src.fetcher.models import Article

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
        matched_entities=(primary_entity,),
        composite_weight=Decimal(composite_weight),
        llm_score=90,
        included_by="rank",
        rationale="Grounded by exposure",
    )


def _make_snapshot(ticker: str):
    from src.pnl.models import DailyDelta, PnLSnapshot

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
