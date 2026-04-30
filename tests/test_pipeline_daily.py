from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.exposure.models import ExposureEntry
from src.portfolio.models import Position
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


def test_run_daily_orchestrates_and_persists_run_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import src.pipeline.daily as daily

    db_path = tmp_path / "andyjuan.db"
    init_db(db_path)
    now = datetime(2026, 4, 26, 8, 0, tzinfo=timezone.utc)
    news_client = StubNewsDataClient(make_news_article(), [])
    sent: list[dict[str, object]] = []

    monkeypatch.setattr(daily, "load_portfolio", lambda path=None: [make_position()])
    monkeypatch.setattr(daily, "resolve_lookthrough", async_return({}))
    monkeypatch.setattr(
        daily,
        "fetch_prices",
        lambda tickers, base_currency="EUR", market_symbols=None: {
            "NVDA": make_price_snapshot()
        },
    )
    monkeypatch.setattr(daily, "NewsDataClient", lambda **kwargs: news_client)
    monkeypatch.setattr(daily, "MacroRSSReader", lambda **kwargs: StubMacroRSSReader())
    monkeypatch.setattr(
        daily,
        "EntityMatcher",
        SimpleNamespace(from_themes_file=lambda **kwargs: StubMatcher()),
    )
    monkeypatch.setattr(
        daily,
        "rank_news",
        fake_rank_news(db_path),
    )
    monkeypatch.setattr(
        daily,
        "generate_theme_flash",
        fake_generate_theme_flash(db_path),
    )
    monkeypatch.setattr(
        daily,
        "generate_synthesis",
        fake_generate_synthesis(db_path),
    )
    monkeypatch.setattr(
        daily,
        "filter_ai_take",
        lambda rendered_content, ai_take_text, **kwargs: ai_take_text,
    )
    monkeypatch.setattr(
        daily,
        "send_email",
        lambda **kwargs: sent.append(kwargs) or SendResult(message_id="msg_123"),
    )

    result = daily.run_daily(
        send=True,
        recipients_override=["juan@example.com", "andrea@example.com"],
        from_addr="radar@example.com",
        database_path=db_path,
        now=now,
    )

    assert result.send_result == SendResult(message_id="msg_123")
    assert news_client.fetch_calls == [
        {
            "entity_query": "NVDA",
            "hours": 24,
            "ignore_seen_db": False,
        }
    ]
    assert len(sent) == 1
    assert sent[0]["subject"].startswith("Daily Portfolio Radar")
    assert "Daily Portfolio Radar" in result.rendered_email.html
    assert 'data-section="ai-synthesis"' in result.rendered_email.html
    assert (
        "AI hardware demand remains broadening across the supply chain."
        in result.rendered_email.html
    )

    runs = list(init_db(db_path)["runs"].rows)
    assert len(runs) == 1
    assert runs[0]["mode"] == "daily"
    assert runs[0]["status"] == "success"
    assert runs[0]["recipient_count"] == 2
    assert runs[0]["tokens_in"] == 30
    assert runs[0]["tokens_out"] == 15
    assert runs[0]["cost_usd"] == 0.06


def test_run_daily_omits_ai_take_when_fact_check_blocks_it(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import src.pipeline.daily as daily

    db_path = tmp_path / "andyjuan.db"
    init_db(db_path)
    sent: list[dict[str, object]] = []

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
        daily, "generate_theme_flash", fake_generate_theme_flash(db_path)
    )
    monkeypatch.setattr(daily, "generate_synthesis", fake_generate_synthesis(db_path))
    monkeypatch.setattr(
        daily, "filter_ai_take", lambda rendered_content, ai_take_text, **kwargs: None
    )
    monkeypatch.setattr(
        daily,
        "send_email",
        lambda **kwargs: sent.append(kwargs) or SendResult(message_id="msg_456"),
    )

    result = daily.run_daily(
        send=True,
        recipients_override=["juan@example.com"],
        from_addr="radar@example.com",
        database_path=db_path,
        now=datetime(2026, 4, 26, 8, 0, tzinfo=timezone.utc),
    )

    assert result.send_result == SendResult(message_id="msg_456")
    assert len(sent) == 1
    assert 'data-section="ai-synthesis"' not in result.rendered_email.html
    assert "🤖 AI-generated" not in result.rendered_email.html


def test_run_daily_with_juan_only_sends_to_juan_only(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import src.pipeline.daily as daily

    db_path = tmp_path / "andyjuan.db"
    init_db(db_path)
    now = datetime(2026, 4, 26, 8, 0, tzinfo=timezone.utc)
    sent: list[dict[str, object]] = []

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
        lambda **kwargs: sent.append(kwargs) or SendResult(message_id="msg_789"),
    )

    result = daily.run_daily(
        send=True,
        juan_only=True,
        from_addr="radar@example.com",
        database_path=db_path,
        now=now,
    )

    assert result.send_result == SendResult(message_id="msg_789")
    assert len(sent) == 1
    assert sent[0]["to"] == ["juancho704@gmail.com"]

    runs = list(init_db(db_path)["runs"].rows)
    assert len(runs) == 1
    assert runs[0]["recipient_count"] == 1


def test_build_news_queries_prioritize_direct_stocks_and_cap_terms() -> None:
    import src.pipeline.daily as daily

    queries = daily._build_news_queries(
        [
            make_position(),
            Position(
                ticker="GOOGL",
                isin="US02079K3059",
                asset_type="stock",
                issuer="Alphabet Inc.",
                shares=Decimal("1"),
                cost_basis_eur=Decimal("100"),
                currency="USD",
            ),
            Position(
                ticker="BNKE",
                isin="LU1829219390",
                asset_type="etf",
                issuer="Amundi ETF",
                shares=Decimal("1"),
                cost_basis_eur=Decimal("100"),
                currency="EUR",
            ),
        ],
        {
            "AAPL": ExposureEntry("AAPL", Decimal("0.18"), ()),
            "MSFT": ExposureEntry("MSFT", Decimal("0.16"), ()),
            "AVGO": ExposureEntry("AVGO", Decimal("0.12"), ()),
            "GOLD": ExposureEntry("GOLD", Decimal("0.10"), ()),
            "SILVER": ExposureEntry("SILVER", Decimal("0.09"), ()),
            "WPM": ExposureEntry("WPM", Decimal("0.08"), ()),
            "BNKE": ExposureEntry("BNKE", Decimal("0.07"), ()),
        },
    )

    assert queries == ("NVDA", "GOOGL", "AAPL", "MSFT", "AVGO", "WPM")


def test_build_market_symbols_uses_portfolio_config() -> None:
    import src.pipeline.daily as daily

    market_symbols = daily._build_market_symbols(
        [
            make_position(),
            Position(
                ticker="QDVE",
                isin="IE00B3WJKG14",
                asset_type="etf",
                issuer="iShares",
                shares=Decimal("1"),
                cost_basis_eur=Decimal("35.183007"),
                currency="EUR",
                market_symbol="IITU.L",
            ),
            Position(
                ticker="BNKE",
                isin="LU1829219390",
                asset_type="etf",
                issuer="Amundi ETF",
                shares=Decimal("1"),
                cost_basis_eur=Decimal("301.551302"),
                currency="EUR",
                market_symbol="BNKE.PA",
            ),
        ]
    )

    assert market_symbols == {
        "QDVE": "IITU.L",
        "BNKE": "BNKE.PA",
    }


def test_resolve_recipients_skips_placeholder_config_addresses(tmp_path: Path) -> None:
    import src.pipeline.daily as daily

    recipients_path = tmp_path / "recipients.yaml"
    recipients_path.write_text(
        "\n".join(
            [
                "recipients:",
                "  juan:",
                "    name: Juan",
                "    email: juan@gmail.com",
                "  andrea:",
                "    name: Andrea",
                "    email: andrea.placeholder@example.com",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    recipients = daily._resolve_recipients(recipients_path, recipients_override=None)

    assert recipients == ("juan@gmail.com",)


def test_resolve_recipients_raises_when_only_placeholders_remain(
    tmp_path: Path,
) -> None:
    import src.pipeline.daily as daily

    recipients_path = tmp_path / "recipients.yaml"
    recipients_path.write_text(
        "\n".join(
            [
                "recipients:",
                "  andrea:",
                "    name: Andrea",
                "    email: andrea.placeholder@example.com",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="No deliverable recipients configured"):
        daily._resolve_recipients(recipients_path, recipients_override=None)
