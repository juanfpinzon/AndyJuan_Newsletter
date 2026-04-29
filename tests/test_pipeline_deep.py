from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from src.sender.agentmail import SendResult
from src.storage.db import init_db
from tests._pipeline_helpers import (
    StubMacroRSSReader,
    StubMatcher,
    StubNewsDataClient,
    async_return,
    fake_generate_synthesis,
    fake_generate_theme_flash,
    fake_rank_news,
    make_news_article,
    make_position,
    make_price_snapshot,
)


def test_run_deep_requests_deep_synthesis_context(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import src.pipeline.daily as daily
    import src.pipeline.deep as deep
    from src.analyzer.synthesis import Synthesis

    db_path = tmp_path / "andyjuan.db"
    init_db(db_path)
    synthesis_calls: list[dict[str, object]] = []

    monkeypatch.setattr(daily, "load_portfolio", lambda path=None: [make_position()])
    monkeypatch.setattr(daily, "resolve_lookthrough", async_return({}))
    monkeypatch.setattr(
        daily,
        "fetch_prices",
        lambda tickers, base_currency="EUR", market_symbols=None: {
            "NVDA": make_price_snapshot()
        },
    )
    monkeypatch.setattr(
        daily,
        "NewsDataClient",
        lambda **kwargs: StubNewsDataClient(make_news_article(), []),
    )
    monkeypatch.setattr(daily, "MacroRSSReader", lambda **kwargs: StubMacroRSSReader())
    monkeypatch.setattr(
        daily,
        "EntityMatcher",
        SimpleNamespace(from_themes_file=lambda **kwargs: StubMatcher()),
    )
    monkeypatch.setattr(daily, "rank_news", fake_rank_news(db_path))
    monkeypatch.setattr(
        daily,
        "generate_theme_flash",
        fake_generate_theme_flash(db_path),
    )

    def synthesize(
        theme_flashes,
        ranked_articles,
        exposure_map,
        *,
        mode="daily",
        week_ahead_items=(),
        llm_caller=None,
        settings=None,
    ) -> Synthesis:
        del theme_flashes, ranked_articles, exposure_map, llm_caller, settings
        synthesis_calls.append(
            {
                "mode": mode,
                "week_ahead_items": tuple(week_ahead_items),
            }
        )
        paragraphs = (
            "Deep paragraph one.",
            "Deep paragraph two.",
            "Deep paragraph three.",
            "Watch Eurozone CPI flash and supplier earnings next week.",
        )
        return Synthesis(text="\n\n".join(paragraphs), paragraphs=paragraphs)

    monkeypatch.setattr(daily, "generate_synthesis", synthesize)
    monkeypatch.setattr(
        daily,
        "filter_ai_take",
        lambda rendered_content, ai_take_text, **kwargs: ai_take_text,
    )
    monkeypatch.setattr(
        daily,
        "send_email",
        lambda **kwargs: SendResult(message_id="unused"),
    )

    deep.run_deep(
        send=False,
        database_path=db_path,
        recipients_override=["juan@example.com"],
        from_addr="radar@example.com",
        week_ahead_items=(
            {"date_label": "Mon", "label": "Eurozone CPI flash", "kind": "Macro"},
        ),
        now=datetime(2026, 4, 26, 8, 0, tzinfo=timezone.utc),
    )

    assert synthesis_calls == [
        {
            "mode": "deep",
            "week_ahead_items": (
                {
                    "date_label": "Mon",
                    "label": "Eurozone CPI flash",
                    "kind": "Macro",
                },
            ),
        }
    ]

def test_run_deep_uses_deep_template_and_week_ahead_items(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import src.pipeline.daily as daily
    import src.pipeline.deep as deep

    db_path = tmp_path / "andyjuan.db"
    init_db(db_path)

    monkeypatch.setattr(daily, "load_portfolio", lambda path=None: [make_position()])
    monkeypatch.setattr(daily, "resolve_lookthrough", async_return({}))
    monkeypatch.setattr(
        daily,
        "fetch_prices",
        lambda tickers, base_currency="EUR", market_symbols=None: {
            "NVDA": make_price_snapshot()
        },
    )
    monkeypatch.setattr(
        daily,
        "NewsDataClient",
        lambda **kwargs: StubNewsDataClient(make_news_article(), []),
    )
    monkeypatch.setattr(daily, "MacroRSSReader", lambda **kwargs: StubMacroRSSReader())
    monkeypatch.setattr(
        daily,
        "EntityMatcher",
        SimpleNamespace(from_themes_file=lambda **kwargs: StubMatcher()),
    )
    monkeypatch.setattr(daily, "rank_news", fake_rank_news(db_path))
    monkeypatch.setattr(
        daily,
        "generate_theme_flash",
        fake_generate_theme_flash(db_path),
    )
    monkeypatch.setattr(daily, "generate_synthesis", fake_generate_synthesis(db_path))
    monkeypatch.setattr(
        daily,
        "filter_ai_take",
        lambda rendered_content, ai_take_text, **kwargs: ai_take_text,
    )
    monkeypatch.setattr(
        daily,
        "send_email",
        lambda **kwargs: SendResult(message_id="unused"),
    )

    result = deep.run_deep(
        send=False,
        database_path=db_path,
        recipients_override=["juan@example.com"],
        from_addr="radar@example.com",
        week_ahead_items=(
            {"date_label": "Mon", "label": "Eurozone CPI flash", "kind": "Macro"},
            {
                "date_label": "Wed",
                "label": "NVIDIA supplier earnings",
                "kind": "Earnings",
            },
        ),
        now=datetime(2026, 4, 26, 8, 0, tzinfo=timezone.utc),
    )

    assert result.send_result is None
    assert "Saturday Deep Portfolio Brief" in result.rendered_email.html
    assert 'data-section="week-ahead"' in result.rendered_email.html
    assert "Eurozone CPI flash" in result.rendered_email.html
    assert "Week Ahead" in result.rendered_email.text
