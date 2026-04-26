"""Macro RSS feed reader with conditional request caching."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from time import struct_time
from typing import Any

import feedparser
import httpx
import yaml

from src.utils.http import get_async_client
from src.utils.log import get_logger

from .models import Article

DEFAULT_MACRO_FEEDS_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "macro_feeds.yaml"
)


@dataclass
class FeedValidators:
    etag: str | None = None
    last_modified: str | None = None


class MacroRSSReader:
    """Fetch macro RSS items and reuse cache validators across calls."""

    def __init__(
        self,
        *,
        config_path: str | Path | None = None,
        backoff_seconds: float = 0.25,
    ) -> None:
        self.config_path = (
            Path(config_path)
            if config_path is not None
            else DEFAULT_MACRO_FEEDS_PATH
        )
        self.backoff_seconds = backoff_seconds
        self._validators: dict[str, FeedValidators] = {}

    async def fetch_macro(
        self,
        *,
        hours: int = 24,
        now: datetime | None = None,
    ) -> list[Article]:
        current_time = now or datetime.now(timezone.utc)
        cutoff = current_time - timedelta(hours=hours)
        articles: list[Article] = []
        logger = get_logger("macro_rss")

        async with get_async_client(backoff_base=self.backoff_seconds) as client:
            for feed in _load_feeds(self.config_path):
                try:
                    response = await client.get(
                        feed["url"],
                        headers=self._request_headers(feed["url"]),
                    )
                    if response.status_code == 304:
                        continue
                    response.raise_for_status()
                except httpx.HTTPError as exc:
                    logger.warning(
                        "macro_feed_fetch_failed",
                        feed_key=feed.get("key", ""),
                        feed_name=feed.get("name", ""),
                        url=feed.get("url", ""),
                        error=str(exc),
                    )
                    continue

                self._store_validators(feed["url"], response.headers)
                parsed_feed = feedparser.parse(response.text)
                articles.extend(
                    self._recent_articles(
                        feed=feed,
                        parsed_feed=parsed_feed,
                        cutoff=cutoff,
                    )
                )

        return articles

    def _request_headers(self, url: str) -> dict[str, str]:
        validators = self._validators.get(url)
        if validators is None:
            return {}

        headers: dict[str, str] = {}
        if validators.etag:
            headers["If-None-Match"] = validators.etag
        if validators.last_modified:
            headers["If-Modified-Since"] = validators.last_modified
        return headers

    def _store_validators(self, url: str, headers: Any) -> None:
        self._validators[url] = FeedValidators(
            etag=headers.get("ETag"),
            last_modified=headers.get("Last-Modified"),
        )

    def _recent_articles(
        self,
        *,
        feed: dict[str, str],
        parsed_feed: feedparser.FeedParserDict,
        cutoff: datetime,
    ) -> list[Article]:
        articles: list[Article] = []
        for entry in parsed_feed.entries:
            published_at = _entry_datetime(entry)
            if published_at is None or published_at < cutoff:
                continue
            articles.append(
                Article(
                    title=str(entry.get("title") or ""),
                    body=str(entry.get("description") or ""),
                    url=str(entry.get("link") or ""),
                    source=feed["name"],
                    published_at=published_at.isoformat(),
                    raw_tags=(feed.get("theme") or "",),
                )
            )
        return articles


def _load_feeds(path: Path) -> list[dict[str, str]]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return list(payload.get("feeds", []))


def _entry_datetime(entry: feedparser.FeedParserDict) -> datetime | None:
    published = entry.get("published")
    if published:
        return parsedate_to_datetime(published).astimezone(timezone.utc)

    published_parsed = entry.get("published_parsed")
    if isinstance(published_parsed, struct_time):
        return datetime(*published_parsed[:6], tzinfo=timezone.utc)

    return None
