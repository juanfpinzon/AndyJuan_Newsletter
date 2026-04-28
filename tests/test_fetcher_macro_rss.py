from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
import respx
import yaml

from src.fetcher.macro_rss import MacroRSSReader

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "news" / "rss"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.asyncio
async def test_fetch_macro_filters_recent_items_and_uses_cached_validators(
    tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    config_path = tmp_path / "macro_feeds.yaml"
    config_path.write_text(
        "\n".join(
            [
                "feeds:",
                "  - key: macro_fixture",
                "    name: Macro Fixture",
                "    url: https://feeds.example.com/macro.xml",
                "    theme: Macro/FX",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    xml_body = (FIXTURES_DIR / "macro_fixture.xml").read_text(encoding="utf-8")
    route = respx_mock.get("https://feeds.example.com/macro.xml").mock(
        side_effect=[
            httpx.Response(
                200,
                text=xml_body,
                headers={
                    "ETag": '"macro-v1"',
                    "Last-Modified": "Fri, 24 Apr 2026 10:00:00 GMT",
                },
            ),
            httpx.Response(304),
        ]
    )

    reader = MacroRSSReader(
        config_path=config_path,
        backoff_seconds=0,
    )
    now = datetime(2026, 4, 25, 12, 0, tzinfo=timezone.utc)

    first_articles = await reader.fetch_macro(now=now)
    second_articles = await reader.fetch_macro(now=now)

    assert [article.title for article in first_articles] == [
        "ECB signals patience on rate path"
    ]
    assert first_articles[0].source == "Macro Fixture"
    assert second_articles == []
    assert route.call_count == 2
    assert route.calls[1].request.headers["if-none-match"] == '"macro-v1"'
    assert (
        route.calls[1].request.headers["if-modified-since"]
        == "Fri, 24 Apr 2026 10:00:00 GMT"
    )


@pytest.mark.asyncio
async def test_fetch_macro_skips_unreachable_feed_and_continues(
    tmp_path: Path,
    respx_mock: respx.MockRouter,
) -> None:
    config_path = tmp_path / "macro_feeds.yaml"
    config_path.write_text(
        "\n".join(
            [
                "feeds:",
                "  - key: broken_feed",
                "    name: Broken Feed",
                "    url: https://feeds.example.com/broken.xml",
                "    theme: Macro/FX",
                "  - key: working_feed",
                "    name: Working Feed",
                "    url: https://feeds.example.com/macro.xml",
                "    theme: Macro/FX",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    xml_body = (FIXTURES_DIR / "macro_fixture.xml").read_text(encoding="utf-8")
    respx_mock.get("https://feeds.example.com/broken.xml").mock(
        side_effect=httpx.ConnectError("dns failed")
    )
    respx_mock.get("https://feeds.example.com/macro.xml").mock(
        return_value=httpx.Response(200, text=xml_body)
    )

    reader = MacroRSSReader(
        config_path=config_path,
        backoff_seconds=0,
    )
    now = datetime(2026, 4, 25, 12, 0, tzinfo=timezone.utc)

    articles = await reader.fetch_macro(now=now)

    assert [article.title for article in articles] == [
        "ECB signals patience on rate path"
    ]
    assert articles[0].source == "Working Feed"


@pytest.mark.asyncio
async def test_fetch_macro_supports_reuters_news_sitemap_with_prefix_filters(
    tmp_path: Path,
    respx_mock: respx.MockRouter,
) -> None:
    config_path = tmp_path / "macro_feeds.yaml"
    config_path.write_text(
        "\n".join(
            [
                "feeds:",
                "  - key: reuters_business",
                "    name: Reuters business news",
                "    url: https://feeds.example.com/reuters-news-sitemap.xml",
                "    theme: Macro/FX",
                "    format: news_sitemap",
                "    include_url_prefixes:",
                "      - /business/",
                "      - /markets/",
                "    max_items: 2",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    xml_body = (FIXTURES_DIR / "reuters_news_sitemap.xml").read_text(
        encoding="utf-8"
    )
    respx_mock.get("https://feeds.example.com/reuters-news-sitemap.xml").mock(
        return_value=httpx.Response(200, text=xml_body)
    )

    reader = MacroRSSReader(config_path=config_path, backoff_seconds=0)
    now = datetime(2026, 4, 28, 12, 0, tzinfo=timezone.utc)

    articles = await reader.fetch_macro(now=now)

    assert [article.title for article in articles] == [
        "HSBC sees limited near-term impact on OPEC+ from UAE's departure",
        "Robinhood's quarterly profit misses estimates on weak transaction revenue",
    ]
    assert [article.url for article in articles] == [
        "https://www.reuters.com/business/energy/hsbc-sees-limited-near-term-impact-opec-uaes-departure-2026-04-28/",
        "https://www.reuters.com/business/robinhood-quarterly-profit-rises-trading-strength-2026-04-28/",
    ]
    assert all(article.source == "Reuters business news" for article in articles)


def test_repository_macro_feed_config_uses_live_ft_and_reuters_sources() -> None:
    payload = yaml.safe_load(
        (REPOSITORY_ROOT / "config" / "macro_feeds.yaml").read_text(encoding="utf-8")
    )
    feeds = {feed["key"]: feed for feed in payload["feeds"]}

    assert feeds["ft_alphaville"]["url"] == "https://www.ft.com/alphaville?format=rss"
    assert feeds["reuters_business"]["url"] == (
        "https://www.reuters.com/arc/outboundfeeds/news-sitemap/?outputType=xml"
    )
    assert feeds["reuters_business"]["format"] == "news_sitemap"
