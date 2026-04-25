import json
from pathlib import Path

import httpx
import pytest
import respx

from src.fetcher.newsdata import NewsDataClient
from src.storage.db import init_db

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "news" / "newsdata"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


@pytest.mark.asyncio
async def test_fetch_news_paginates_dedups_and_persists_seen_urls(
    tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
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


@pytest.mark.asyncio
async def test_fetch_news_retries_once_on_rate_limit(
    tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
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
