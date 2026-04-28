import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
import respx

from src.fetcher.models import Article
from src.fetcher.newsdata import NewsDataClient
from src.storage.db import init_db

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "news" / "newsdata"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def _freeze_news_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.fetcher.newsdata as newsdata

    monkeypatch.setattr(
        newsdata,
        "_utcnow",
        lambda: datetime(2026, 4, 26, 5, 30, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_fetch_news_paginates_dedups_and_persists_seen_urls(
    tmp_path: Path,
    respx_mock: respx.MockRouter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _freeze_news_clock(monkeypatch)
    db_path = tmp_path / "newsdata.db"
    database = init_db(db_path)
    database["articles_seen"].insert(
        {
            "article_id": "seen-before",
            "source_url": "https://example.com/already-seen",
            "published_at": "2026-04-24T06:00:00Z",
            "seen_at": "2026-04-24T07:00:00Z",
        }
    )

    route = respx_mock.get("https://newsdata.example/api/1/news").mock(
        side_effect=[
            httpx.Response(200, json=load_fixture("page_1.json")),
            httpx.Response(200, json=load_fixture("page_2.json")),
        ]
    )

    client = NewsDataClient(
        api_key="test-key",
        db_path=db_path,
        base_url="https://newsdata.example/api/1/news",
        backoff_seconds=0,
    )

    articles = await client.fetch_news("NVDA", hours=24)

    assert [article.url for article in articles] == [
        "https://example.com/nvidia-demand",
        "https://example.com/alphabet-ad-rebound",
    ]
    assert [article.source for article in articles] == ["Reuters", "Bloomberg"]
    assert route.call_count == 2

    seen_urls = {
        row["source_url"]
        for row in database["articles_seen"].rows_where(
            "source_url is not null", select="source_url"
        )
    }
    assert seen_urls == {
        "https://example.com/already-seen",
        "https://example.com/nvidia-demand",
        "https://example.com/alphabet-ad-rebound",
    }
    stored_rows = list(
        database["articles_seen"].rows_where(
            "source_url = :url",
            {"url": "https://example.com/nvidia-demand"},
        )
    )
    assert stored_rows[0]["title"] == "Nvidia demand lifts AI server spending"
    assert stored_rows[0]["source"] == "Reuters"
    assert stored_rows[0]["raw_tags_json"] == '["NVDA","AI"]'


@pytest.mark.asyncio
async def test_fetch_news_retries_once_on_rate_limit(
    tmp_path: Path,
    respx_mock: respx.MockRouter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _freeze_news_clock(monkeypatch)
    route = respx_mock.get("https://newsdata.example/api/1/news").mock(
        side_effect=[
            httpx.Response(429),
            httpx.Response(200, json=load_fixture("single_page.json")),
        ]
    )

    client = NewsDataClient(
        api_key="test-key",
        db_path=tmp_path / "rate-limit.db",
        base_url="https://newsdata.example/api/1/news",
        backoff_seconds=0,
    )

    articles = await client.fetch_news("NVDA", hours=24)

    assert [article.url for article in articles] == [
        "https://example.com/nvidia-demand"
    ]
    assert route.call_count == 2


@pytest.mark.asyncio
async def test_fetch_news_stops_at_configured_page_limit(
    tmp_path: Path,
    respx_mock: respx.MockRouter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _freeze_news_clock(monkeypatch)
    route = respx_mock.get("https://newsdata.example/api/1/news").mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "status": "success",
                    "nextPage": "page-2",
                    "results": [
                        {
                            "article_id": "article-1",
                            "title": "First page result",
                            "description": "First page body",
                            "link": "https://example.com/page-1",
                            "source_id": "reuters",
                            "source_name": "Reuters",
                            "pubDate": "2026-04-25 09:00:00",
                            "keywords": ["NVDA"],
                        }
                    ],
                },
            ),
            httpx.Response(
                200,
                json={
                    "status": "success",
                    "nextPage": "page-3",
                    "results": [
                        {
                            "article_id": "article-2",
                            "title": "Second page result",
                            "description": "Second page body",
                            "link": "https://example.com/page-2",
                            "source_id": "bloomberg",
                            "source_name": "Bloomberg",
                            "pubDate": "2026-04-25 08:30:00",
                            "keywords": ["NVDA"],
                        }
                    ],
                },
            ),
            httpx.Response(
                200,
                json={
                    "status": "success",
                    "results": [
                        {
                            "article_id": "article-3",
                            "title": "Third page result",
                            "description": "Third page body",
                            "link": "https://example.com/page-3",
                            "source_id": "ft",
                            "source_name": "Financial Times",
                            "pubDate": "2026-04-25 08:00:00",
                            "keywords": ["NVDA"],
                        }
                    ],
                },
            ),
        ]
    )

    client = NewsDataClient(
        api_key="test-key",
        db_path=tmp_path / "page-limit.db",
        base_url="https://newsdata.example/api/1/news",
        backoff_seconds=0,
        max_pages=2,
    )

    articles = await client.fetch_news("NVDA", hours=24)

    assert [article.url for article in articles] == [
        "https://example.com/page-1",
        "https://example.com/page-2",
    ]
    assert route.call_count == 2


@pytest.mark.asyncio
async def test_fetch_news_ignore_seen_db_refetches_previous_urls(
    tmp_path: Path,
    respx_mock: respx.MockRouter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _freeze_news_clock(monkeypatch)
    db_path = tmp_path / "newsdata.db"
    database = init_db(db_path)
    database["articles_seen"].insert(
        {
            "article_id": "seen-before",
            "source_url": "https://example.com/nvidia-demand",
            "published_at": "2026-04-24T06:00:00Z",
            "seen_at": "2026-04-24T07:00:00Z",
            "title": "Older cached title",
            "body": "Older cached body",
            "source": "Reuters",
            "raw_tags_json": '["NVDA"]',
        }
    )
    respx_mock.get("https://newsdata.example/api/1/news").mock(
        return_value=httpx.Response(200, json=load_fixture("single_page.json"))
    )

    client = NewsDataClient(
        api_key="test-key",
        db_path=db_path,
        base_url="https://newsdata.example/api/1/news",
        backoff_seconds=0,
    )

    articles = await client.fetch_news("NVDA", hours=24, ignore_seen_db=True)

    assert [article.url for article in articles] == [
        "https://example.com/nvidia-demand"
    ]


@pytest.mark.asyncio
async def test_fetch_news_uses_bare_query_and_filters_window_locally(
    tmp_path: Path,
    respx_mock: respx.MockRouter,
    monkeypatch,
) -> None:
    import src.fetcher.newsdata as newsdata

    monkeypatch.setattr(
        newsdata,
        "_utcnow",
        lambda: datetime(2026, 4, 26, 8, 0, tzinfo=timezone.utc),
    )

    route = respx_mock.get("https://newsdata.example/api/1/news").mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "status": "success",
                    "nextPage": "page-2",
                    "results": [
                        {
                            "article_id": "article-1",
                            "title": "Nvidia demand lifts AI server spending",
                            "description": (
                                "Customers kept ordering Blackwell hardware."
                            ),
                            "link": "https://example.com/nvidia-demand",
                            "source_id": "reuters",
                            "source_name": "Reuters",
                            "pubDate": "2026-04-25 12:00:00",
                            "keywords": ["NVDA", "AI"],
                        },
                        {
                            "article_id": "article-old",
                            "title": "Older article should be filtered",
                            "description": "Outside the requested lookback window.",
                            "link": "https://example.com/old-story",
                            "source_id": "reuters",
                            "source_name": "Reuters",
                            "pubDate": "2026-04-25 07:00:00",
                            "keywords": ["NVDA"],
                        },
                    ],
                },
            )
        ]
    )

    client = NewsDataClient(
        api_key="test-key",
        db_path=tmp_path / "local-filter.db",
        base_url="https://newsdata.example/api/1/news",
        backoff_seconds=0,
    )

    articles = await client.fetch_news("NVDA", hours=24)

    assert [article.url for article in articles] == [
        "https://example.com/nvidia-demand"
    ]
    assert route.call_count == 1
    request = route.calls[0].request
    assert request.url.params["q"] == "NVDA"
    assert "from_date" not in request.url.params
    assert "timeframe" not in request.url.params


def test_load_cached_articles_returns_recent_article_payloads(tmp_path: Path) -> None:
    db_path = tmp_path / "newsdata.db"
    database = init_db(db_path)
    database["articles_seen"].insert_all(
        [
            {
                "article_id": "recent-1",
                "source_url": "https://example.com/nvidia-demand",
                "published_at": "2026-04-25T10:30:00+00:00",
                "seen_at": "2026-04-25T10:45:00+00:00",
                "title": "Nvidia suppliers signal firm AI demand",
                "body": "Demand commentary",
                "source": "Reuters",
                "raw_tags_json": '["NVDA","AI"]',
            },
            {
                "article_id": "stale-1",
                "source_url": "https://example.com/old-story",
                "published_at": "2026-04-20T10:30:00+00:00",
                "seen_at": "2026-04-20T10:45:00+00:00",
                "title": "Old story",
                "body": "Old body",
                "source": "Reuters",
                "raw_tags_json": '["OLD"]',
            },
        ]
    )
    client = NewsDataClient(
        api_key="test-key",
        db_path=db_path,
        base_url="https://newsdata.example/api/1/news",
        backoff_seconds=0,
    )

    articles = client.load_cached_articles(
        hours=24,
        now="2026-04-26T00:00:00+00:00",
    )

    assert articles == [
        Article(
            title="Nvidia suppliers signal firm AI demand",
            body="Demand commentary",
            url="https://example.com/nvidia-demand",
            source="Reuters",
            published_at="2026-04-25T10:30:00+00:00",
            raw_tags=("NVDA", "AI"),
        )
    ]
