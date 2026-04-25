"""Typed article models for fetchers and downstream matching."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Article:
    title: str
    body: str
    url: str
    source: str
    published_at: str
    raw_tags: tuple[str, ...]
