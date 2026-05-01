"""Typed article models for fetchers and downstream matching."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import langid

_SUPPORTED_LANGUAGE_CODES = {"en", "es", "ru"}
_AMBIGUOUS_LANGUAGE_CODES = {
    "",
    "auto",
    "mul",
    "n/a",
    "na",
    "none",
    "null",
    "und",
    "unk",
    "unknown",
    "zxx",
}
_LANGUAGE_ALIASES = {
    "en": "en",
    "eng": "en",
    "english": "en",
    "es": "es",
    "spa": "es",
    "spanish": "es",
    "espanol": "es",
    "español": "es",
    "ru": "ru",
    "rus": "ru",
    "russian": "ru",
}


@dataclass(frozen=True)
class Article:
    title: str
    body: str
    url: str
    source: str
    published_at: str
    raw_tags: tuple[str, ...]
    language: str = ""


def filter_supported_articles(articles: Sequence[Article]) -> list[Article]:
    return [article for article in articles if is_supported_article_language(article)]


def is_supported_article_language(article: Article) -> bool:
    metadata_language = normalize_article_language(article.language)
    if metadata_language and metadata_language not in _AMBIGUOUS_LANGUAGE_CODES:
        return metadata_language in _SUPPORTED_LANGUAGE_CODES

    detected_language = _detect_article_language(article)
    if detected_language:
        return detected_language in _SUPPORTED_LANGUAGE_CODES

    return not _has_predominantly_disallowed_script(f"{article.title}\n{article.body}")


def normalize_article_language(value: str) -> str:
    language = value.strip().lower().replace("_", "-")
    if not language:
        return ""
    if any(separator in language for separator in (",", ";", "/", "|")):
        return "und"
    if language in _LANGUAGE_ALIASES:
        return _LANGUAGE_ALIASES[language]
    primary_subtag = language.split("-", 1)[0]
    return _LANGUAGE_ALIASES.get(primary_subtag, primary_subtag)


def _detect_article_language(article: Article) -> str:
    sample = _build_detection_sample(article)
    if not sample:
        return ""
    return normalize_article_language(langid.classify(sample)[0])


def _build_detection_sample(article: Article) -> str:
    sample = " ".join(
        part.strip()
        for part in (article.title, article.body)
        if part and part.strip()
    )
    return sample if _count_alpha_characters(sample) >= 20 else ""


def _count_alpha_characters(text: str) -> int:
    return sum(1 for character in text if character.isalpha())


def _has_predominantly_disallowed_script(text: str) -> bool:
    alpha_characters = [character for character in text if character.isalpha()]
    if not alpha_characters:
        return False

    disallowed_count = sum(
        1 for character in alpha_characters if _is_disallowed_script(character)
    )
    return disallowed_count >= 8 or (
        disallowed_count / len(alpha_characters)
    ) >= 0.35


def _is_disallowed_script(character: str) -> bool:
    codepoint = ord(character)
    return (
        0x0600 <= codepoint <= 0x06FF
        or 0x0750 <= codepoint <= 0x077F
        or 0x08A0 <= codepoint <= 0x08FF
        or 0xFB50 <= codepoint <= 0xFDFF
        or 0xFE70 <= codepoint <= 0xFEFC
        or 0x0590 <= codepoint <= 0x05FF
        or 0x0370 <= codepoint <= 0x03FF
        or 0x3040 <= codepoint <= 0x30FF
        or 0x3400 <= codepoint <= 0x4DBF
        or 0x4E00 <= codepoint <= 0x9FFF
        or 0xAC00 <= codepoint <= 0xD7AF
        or 0xF900 <= codepoint <= 0xFAFF
    )
