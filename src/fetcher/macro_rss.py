"""Macro RSS feed reader with conditional request caching."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from time import struct_time
from typing import Any
from urllib.parse import urlparse
from xml.etree import ElementTree

import feedparser
import httpx
import yaml

from src.utils.http import get_async_client
from src.utils.log import get_logger

from .models import Article

DEFAULT_MACRO_FEEDS_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "macro_feeds.yaml"
)
SITEMAP_NS = {
    "news": "http://www.google.com/schemas/sitemap-news/0.9",
    "sitemap": "http://www.sitemaps.org/schemas/sitemap/0.9",
}


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
                articles.extend(
                    self._recent_feed_articles(
                        feed=feed,
                        payload=response.text,
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

    def _recent_feed_articles(
        self,
        *,
        feed: dict[str, Any],
        payload: str,
        cutoff: datetime,
    ) -> list[Article]:
        feed_format = str(feed.get("format") or "rss").strip().lower()
        if feed_format == "news_sitemap":
            return self._recent_sitemap_articles(
                feed=feed,
                payload=payload,
                cutoff=cutoff,
            )

        parsed_feed = feedparser.parse(payload)
        return self._recent_rss_articles(
            feed=feed,
            parsed_feed=parsed_feed,
            cutoff=cutoff,
        )

    def _recent_rss_articles(
        self,
        *,
        feed: dict[str, Any],
        parsed_feed: feedparser.FeedParserDict,
        cutoff: datetime,
    ) -> list[Article]:
        articles: list[Article] = []
        max_items = _coerce_max_items(feed.get("max_items"))
        feed_language = str(parsed_feed.feed.get("language") or "")
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
                    language=str(entry.get("language") or feed_language),
                )
            )
            if max_items is not None and len(articles) >= max_items:
                break
        return articles

    def _recent_sitemap_articles(
        self,
        *,
        feed: dict[str, Any],
        payload: str,
        cutoff: datetime,
    ) -> list[Article]:
        try:
            root = ElementTree.fromstring(payload)
        except ElementTree.ParseError:
            return []

        include_url_prefixes = _coerce_url_prefixes(feed.get("include_url_prefixes"))
        max_items = _coerce_max_items(feed.get("max_items"))
        articles: list[Article] = []

        for url_node in root.findall("sitemap:url", SITEMAP_NS):
            article_url = _xml_text(url_node.find("sitemap:loc", SITEMAP_NS))
            if not article_url:
                continue
            if include_url_prefixes and not _matches_url_prefix(
                article_url,
                include_url_prefixes,
            ):
                continue

            published_at = _sitemap_entry_datetime(url_node)
            if published_at is None or published_at < cutoff:
                continue

            title = _xml_text(url_node.find("news:news/news:title", SITEMAP_NS))
            if not title:
                continue

            articles.append(
                Article(
                    title=title,
                    body="",
                    url=article_url,
                    source=str(feed.get("name") or ""),
                    published_at=published_at.isoformat(),
                    raw_tags=(str(feed.get("theme") or ""),),
                    language=_xml_text(
                        url_node.find("news:news/news:language", SITEMAP_NS)
                    ),
                )
            )
            if max_items is not None and len(articles) >= max_items:
                break

        return articles


def _load_feeds(path: Path) -> list[dict[str, Any]]:
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


def _sitemap_entry_datetime(url_node: ElementTree.Element) -> datetime | None:
    value = _xml_text(url_node.find("news:news/news:publication_date", SITEMAP_NS))
    if not value:
        value = _xml_text(url_node.find("sitemap:lastmod", SITEMAP_NS))
    return _parse_iso_datetime(value)


def _parse_iso_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _xml_text(node: ElementTree.Element | None) -> str:
    if node is None or node.text is None:
        return ""
    return node.text.strip()


def _coerce_url_prefixes(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def _coerce_max_items(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _matches_url_prefix(article_url: str, prefixes: tuple[str, ...]) -> bool:
    path = urlparse(article_url).path
    return any(path.startswith(prefix) for prefix in prefixes)
