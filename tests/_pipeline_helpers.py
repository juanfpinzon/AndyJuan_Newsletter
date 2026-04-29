from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from src.analyzer.ranker import ArticleCandidate, RankedArticle
from src.analyzer.synthesis import Synthesis
from src.analyzer.theme_flash import ThemeFlash
from src.fetcher.models import Article
from src.portfolio.models import Position
from src.pricing import PriceSnapshot
from src.storage.db import record_llm_call


@dataclass
class StubNewsDataClient:
    article: Article
    fetch_calls: list[dict[str, object]]

    async def fetch_news(
        self,
        entity_query: str,
        hours: int = 24,
        *,
        ignore_seen_db: bool = False,
    ) -> list[Article]:
        self.fetch_calls.append(
            {
                "entity_query": entity_query,
                "hours": hours,
                "ignore_seen_db": ignore_seen_db,
            }
        )
        return [self.article]

    def load_cached_articles(
        self,
        *,
        hours: int = 24,
        now: str | datetime | None = None,
    ) -> list[Article]:
        return [self.article]


class StubMacroRSSReader:
    async def fetch_macro(
        self,
        *,
        hours: int = 24,
        now: datetime | None = None,
    ) -> list[Article]:
        return [
            Article(
                title="ECB speakers keep rate path data-dependent",
                body="",
                url="https://example.com/ecb-rates",
                source="ECB",
                published_at="2026-04-26T05:50:00+00:00",
                raw_tags=("Macro/FX",),
            )
        ]


class StubMatcher:
    def match(self, article: Article) -> list[SimpleNamespace]:
        return [SimpleNamespace(entity="NVDA", score=100.0, method="ticker")]


def make_position() -> Position:
    return Position(
        ticker="NVDA",
        isin="US67066G1040",
        asset_type="stock",
        issuer="NVIDIA",
        shares=Decimal("2"),
        cost_basis_eur=Decimal("100"),
        currency="USD",
    )


def make_price_snapshot() -> PriceSnapshot:
    return PriceSnapshot(
        ticker="NVDA",
        last=Decimal("125"),
        previous_close=Decimal("120"),
        currency_native="USD",
        last_eur=Decimal("112.5"),
        change_pct=Decimal("4.1667"),
        fx_rate_to_eur=Decimal("1.1111111111"),
    )


def make_news_article() -> Article:
    return Article(
        title="Nvidia suppliers signal firm AI demand",
        body="Suppliers still report broad AI server demand.",
        url="https://example.com/nvda-demand",
        source="Reuters",
        published_at="2026-04-26T07:30:00+00:00",
        raw_tags=("NVDA", "AI"),
    )


def async_return(value: object):
    async def runner(*args, **kwargs):
        return value

    return runner


def fake_rank_news(db_path: Path):
    def runner(
        articles: list[ArticleCandidate],
        exposure_map,
        *,
        llm_caller=None,
        settings=None,
    ) -> list[RankedArticle]:
        del exposure_map, llm_caller, settings
        record_llm_call(
            db_path,
            model="ranker",
            prompt="prompt",
            tokens_in=10,
            tokens_out=5,
            cost_usd=0.01,
            success=True,
        )
        return [
            RankedArticle(
                article=articles[0].article,
                primary_entity="NVDA",
                matched_entities=("NVDA",),
                composite_weight=Decimal("1"),
                llm_score=95,
                included_by="rank",
                rationale="High exposure",
            )
        ]

    return runner


def fake_generate_theme_flash(db_path: Path):
    def runner(theme: str, articles, *, llm_caller=None, settings=None) -> ThemeFlash:
        del theme, articles, llm_caller, settings
        record_llm_call(
            db_path,
            model="theme-flash",
            prompt="prompt",
            tokens_in=10,
            tokens_out=5,
            cost_usd=0.02,
            success=True,
        )
        return ThemeFlash(
            theme="AI/Semis",
            text="AI hardware demand remains broadening across the supply chain.",
            sentence_count=1,
        )

    return runner


def fake_generate_synthesis(db_path: Path):
    def runner(
        theme_flashes,
        ranked_articles,
        exposure_map,
        *,
        mode="daily",
        week_ahead_items=(),
        llm_caller=None,
        settings=None,
    ) -> Synthesis:
        del (
            theme_flashes,
            ranked_articles,
            exposure_map,
            week_ahead_items,
            llm_caller,
            settings,
        )
        record_llm_call(
            db_path,
            model="synthesis",
            prompt="prompt",
            tokens_in=10,
            tokens_out=5,
            cost_usd=0.03,
            success=True,
        )
        if mode == "deep":
            paragraphs = (
                (
                    "AI and platform exposure remain the main drivers "
                    "of portfolio sensitivity."
                ),
                "Cross-theme spillovers still cluster around mega-cap demand signals.",
                (
                    "Saturday deep mode keeps the focus on whether breadth can "
                    "expand beyond the same leaders."
                ),
                "Watch whether macro rate repricing changes the breadth of leadership.",
            )
        else:
            paragraphs = (
                (
                    "AI and platform exposure remain the main drivers "
                    "of portfolio sensitivity."
                ),
                "Cross-theme spillovers still cluster around mega-cap demand signals.",
                "Watch whether macro rate repricing changes the breadth of leadership.",
            )
        return Synthesis(text="\n\n".join(paragraphs), paragraphs=paragraphs)

    return runner
