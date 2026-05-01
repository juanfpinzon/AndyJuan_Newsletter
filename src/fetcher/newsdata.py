"""NewsData.io client helpers."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.storage.db import init_db
from src.utils.http import get_async_client

from .models import Article


class NewsDataConfigError(RuntimeError):
    """Raised when NewsData client configuration is incomplete."""


class NewsDataClient:
    """Fetch portfolio news with pagination and SQLite-backed dedup."""

    def __init__(
        self,
        *,
        api_key: str,
        db_path: str | Path,
        base_url: str = "https://newsdata.io/api/1/news",
        backoff_seconds: float = 0.25,
        max_pages: int = 2,
    ) -> None:
        self.api_key = api_key
        self.db_path = db_path
        self.base_url = base_url
        self.backoff_seconds = backoff_seconds
        self.max_pages = max(1, max_pages)

    async def fetch_news(
        self,
        entity_query: str,
        hours: int = 24,
        *,
        ignore_seen_db: bool = False,
    ) -> list[Article]:
        database = init_db(self.db_path)
        seen_urls = set()
        if not ignore_seen_db:
            seen_urls = {
                row["source_url"]
                for row in database["articles_seen"].rows_where(
                    "source_url is not null", select="source_url"
                )
            }
        articles: list[Article] = []
        next_page: str | None = None
        cutoff = _utcnow() - timedelta(hours=hours)
        pages_fetched = 0

        async with get_async_client(
            retries=2,
            backoff_base=self.backoff_seconds,
        ) as client:
            while True:
                payload = await self._fetch_page(
                    client,
                    entity_query=entity_query,
                    next_page=next_page,
                )
                pages_fetched += 1
                page_crossed_cutoff = False
                for item in payload.get("results", []):
                    article = self._parse_article(item)
                    if not _is_within_window(article.published_at, cutoff):
                        page_crossed_cutoff = True
                        continue
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
                            "title": article.title,
                            "body": article.body,
                            "source": article.source,
                            "raw_tags_json": json.dumps(
                                list(article.raw_tags),
                                separators=(",", ":"),
                            ),
                            "language": article.language,
                        }
                    )

                next_page = payload.get("nextPage")
                # NewsData serves newest-first pages; once a page crosses the
                # cutoff, later pages are older and can be skipped.
                if (
                    not next_page
                    or page_crossed_cutoff
                    or pages_fetched >= self.max_pages
                ):
                    return articles

    def load_cached_articles(
        self,
        *,
        hours: int = 24,
        now: str | datetime | None = None,
    ) -> list[Article]:
        database = init_db(self.db_path)
        current_time = _coerce_now(now)
        cutoff = current_time - timedelta(hours=hours)
        rows = list(
            database["articles_seen"].rows_where(
                """
                published_at is not null
                and published_at >= :cutoff
                and title is not null
                and source_url is not null
                order by published_at desc
                """,
                {"cutoff": cutoff.isoformat()},
            )
        )
        return [self._parse_cached_article(row) for row in rows]

    async def _fetch_page(
        self,
        client,
        *,
        entity_query: str,
        next_page: str | None,
    ) -> dict[str, Any]:
        params = {
            "apikey": _require_api_key(self.api_key),
            "q": entity_query,
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
            language=str(item.get("language") or ""),
        )

    def _parse_cached_article(self, row: dict[str, Any]) -> Article:
        return Article(
            title=str(row.get("title") or ""),
            body=str(row.get("body") or ""),
            url=str(row.get("source_url") or ""),
            source=str(row.get("source") or ""),
            published_at=str(row.get("published_at") or ""),
            raw_tags=_parse_raw_tags_json(row.get("raw_tags_json")),
            language=str(row.get("language") or ""),
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


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_now(value: str | datetime | None) -> datetime:
    if value is None:
        return _utcnow()
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _parse_raw_tags_json(value: Any) -> tuple[str, ...]:
    if not value:
        return ()
    try:
        payload = json.loads(str(value))
    except json.JSONDecodeError:
        return ()
    if not isinstance(payload, list):
        return ()
    return tuple(str(item) for item in payload)


def _is_within_window(published_at: str, cutoff: datetime) -> bool:
    parsed = _parse_published_at(published_at)
    if parsed is None:
        return True
    return parsed >= cutoff


def _parse_published_at(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _require_api_key(value: str) -> str:
    api_key = value.strip()
    if not api_key:
        raise NewsDataConfigError("NEWSDATA_API_KEY is not set")
    return api_key
