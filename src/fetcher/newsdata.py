"""NewsData.io client helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.storage.db import init_db
from src.utils.http import get_async_client

from .models import Article


class NewsDataClient:
    """Fetch portfolio news with pagination and SQLite-backed dedup."""

    def __init__(
        self,
        *,
        api_key: str,
        db_path: str | Path,
        base_url: str = "https://newsdata.io/api/1/news",
        backoff_seconds: float = 0.25,
    ) -> None:
        self.api_key = api_key
        self.db_path = db_path
        self.base_url = base_url
        self.backoff_seconds = backoff_seconds

    async def fetch_news(self, entity_query: str, hours: int = 24) -> list[Article]:
        database = init_db(self.db_path)
        seen_urls = {
            row["source_url"]
            for row in database["articles_seen"].rows_where(
                "source_url is not null", select="source_url"
            )
        }
        articles: list[Article] = []
        next_page: str | None = None
        from_date = datetime.now(timezone.utc) - timedelta(hours=hours)

        async with get_async_client(
            retries=2,
            backoff_base=self.backoff_seconds,
        ) as client:
            while True:
                payload = await self._fetch_page(
                    client,
                    entity_query=entity_query,
                    from_date=from_date,
                    next_page=next_page,
                )
                for item in payload.get("results", []):
                    article = self._parse_article(item)
                    if article.url in seen_urls:
                        continue
                    seen_urls.add(article.url)
                    articles.append(article)
                    database["articles_seen"].insert(
                        {
                            "article_id": item.get("article_id") or article.url,
                            "source_url": article.url,
                            "published_at": article.published_at,
                            "seen_at": datetime.now(timezone.utc).isoformat(),
                        }
                    )

                next_page = payload.get("nextPage")
                if not next_page:
                    return articles

    async def _fetch_page(
        self,
        client,
        *,
        entity_query: str,
        from_date: datetime,
        next_page: str | None,
    ) -> dict[str, Any]:
        params = {
            "apikey": self.api_key,
            "q": entity_query,
            "from_date": from_date.date().isoformat(),
        }
        if next_page:
            params["page"] = next_page

        response = await client.get(self.base_url, params=params)
        response.raise_for_status()
        return response.json()

    def _parse_article(self, item: dict[str, Any]) -> Article:
        return Article(
            title=str(item.get("title") or ""),
            body=str(item.get("description") or item.get("content") or ""),
            url=str(item.get("link") or ""),
            source=str(item.get("source_name") or item.get("source_id") or ""),
            published_at=_normalize_newsdata_timestamp(item.get("pubDate")),
            raw_tags=tuple(str(tag) for tag in item.get("keywords") or ()),
        )


def _normalize_newsdata_timestamp(value: Any) -> str:
    if not value:
        return ""
    text = str(value)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        return parsed.replace(tzinfo=timezone.utc).isoformat()
    return text
