from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import respx

from src.sender.agentmail import SendResult
from src.storage.db import init_db
from tests._pipeline_helpers import (
    CI_TEST_LLM_USAGES,
    CI_TEST_TICKER,
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

EXPECTED_TOKENS_IN = sum(usage.tokens_in for usage in CI_TEST_LLM_USAGES)
EXPECTED_TOKENS_OUT = sum(usage.tokens_out for usage in CI_TEST_LLM_USAGES)
EXPECTED_COST_USD = sum(usage.cost_usd for usage in CI_TEST_LLM_USAGES)


def test_run_radar_daily_dry_run_uses_mocked_provider_clients(
    tmp_path: Path,
    monkeypatch,
    respx_mock: respx.MockRouter,
) -> None:
    import src.main as main
    import src.pipeline.daily as daily

    db_path = tmp_path / "andyjuan.db"
    init_db(db_path)
    now = datetime(2026, 4, 26, 8, 0, tzinfo=timezone.utc)
    news_client = StubNewsDataClient(make_news_article(), [])
    send_calls: list[dict[str, object]] = []
    captured_result: dict[str, object] = {}

    monkeypatch.setattr(daily, "load_portfolio", lambda path=None: [make_position()])
    monkeypatch.setattr(daily, "resolve_lookthrough", async_return({}))
    monkeypatch.setattr(
        daily,
        "fetch_prices",
        lambda tickers, base_currency="EUR", market_symbols=None: {
            CI_TEST_TICKER: make_price_snapshot()
        },
    )
    monkeypatch.setattr(daily, "NewsDataClient", lambda **kwargs: news_client)
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
        lambda **kwargs: send_calls.append(kwargs) or SendResult(message_id="msg_123"),
    )

    def run_daily_for_ci(**kwargs):
        result = daily.run_daily(
            database_path=db_path,
            recipients_override=["juan@example.com"],
            from_addr="radar@example.com",
            now=now,
            **kwargs,
        )
        captured_result["value"] = result
        return result

    monkeypatch.setattr(main, "run_daily", run_daily_for_ci)
    monkeypatch.setattr(
        main,
        "run_deep",
        lambda **kwargs: pytest.fail("run-radar CI check should stay on daily mode"),
    )

    exit_code = main.main(["--mode", "daily", "--dry-run"])

    assert exit_code == 0
    assert news_client.fetch_calls == [
        {
            "entity_query": CI_TEST_TICKER,
            "hours": 24,
            "ignore_seen_db": False,
        }
    ]
    assert send_calls == []
    assert len(respx_mock.calls) == 0
    assert "Daily Portfolio Radar" in captured_result["value"].rendered_email.html

    runs = list(init_db(db_path)["runs"].rows)
    assert len(runs) == 1
    assert runs[0]["mode"] == "daily"
    assert runs[0]["status"] == "success"
    assert runs[0]["recipient_count"] == 0
    assert runs[0]["tokens_in"] == EXPECTED_TOKENS_IN
    assert runs[0]["tokens_out"] == EXPECTED_TOKENS_OUT
    assert runs[0]["cost_usd"] == pytest.approx(EXPECTED_COST_USD)


@pytest.mark.parametrize("argv", [["--mode"], ["--mode", "weekly"]])
def test_run_radar_cli_exits_nonzero_for_invalid_args(argv: list[str]) -> None:
    import src.main as main

    with pytest.raises(SystemExit) as excinfo:
        main.main(argv)

    assert excinfo.value.code != 0
