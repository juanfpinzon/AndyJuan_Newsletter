"""HTML email rendering helpers."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from premailer import transform

from .theme_groups import (
    ConcentratedExposureRow,
    PositionCard,
    ThemeArticle,
    ThemeGroup,
)

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"
_TEMPLATE_ENV = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    undefined=StrictUndefined,
    autoescape=select_autoescape(enabled_extensions=("html", "j2")),
    trim_blocks=True,
    lstrip_blocks=True,
)
WORD_RE = re.compile(r"\b[\w']+\b")
_CSSUTILS_CONFIGURED = False


class RenderValidationError(RuntimeError):
    """Raised when renderer input is incomplete or invalid."""


@dataclass(frozen=True)
class RenderedEmail:
    html: str
    text: str
    word_count: int


def render_email(
    context: Mapping[str, Any],
    mode: str = "daily",
) -> RenderedEmail:
    """Render an HTML email plus a plain-text fallback."""

    template_name = _template_name(mode)
    template_context = _normalize_context(context)
    _validate_news_links(template_context)

    html = _TEMPLATE_ENV.get_template(template_name).render(**template_context).strip()
    inlined_html = _inline_css(html)
    text = _html_to_text(inlined_html)
    return RenderedEmail(
        html=inlined_html,
        text=text,
        word_count=_count_words(text),
    )


def _template_name(mode: str) -> str:
    if mode == "daily":
        return "daily_email.html.j2"
    if mode == "deep":
        return "saturday_deep.html.j2"
    raise RenderValidationError(f"Unsupported render mode: {mode}")


def _normalize_context(context: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(context)
    normalized["theme_groups"] = tuple(
        _normalize_theme_group(group) for group in context.get("theme_groups", ())
    )
    normalized["concentrated_exposures"] = tuple(
        _normalize_concentrated_exposure(row)
        for row in context.get("concentrated_exposures", ())
    )
    return normalized


def _validate_news_links(context: Mapping[str, Any]) -> None:
    theme_groups = context.get("theme_groups", ())
    for group in theme_groups:
        for article in _iter_mapping_items(group, "articles"):
            href = str(article.get("href", "")).strip()
            if not href:
                raise RenderValidationError(
                    "Every rendered news item must include an href"
                )

    for item in context.get("macro_items", ()):
        if not isinstance(item, Mapping):
            continue
        href = str(item.get("href", "")).strip()
        if not href:
            raise RenderValidationError("Every rendered news item must include an href")


def _normalize_theme_group(group: Any) -> Any:
    if isinstance(group, ThemeGroup):
        return {
            "name": group.name,
            "description": group.description,
            "cards": tuple(_normalize_position_card(card) for card in group.cards),
            "articles": tuple(
                _normalize_theme_article(article) for article in group.articles
            ),
            "flash_text": group.flash_text,
        }
    if isinstance(group, Mapping):
        normalized = dict(group)
        normalized["cards"] = tuple(
            _normalize_position_card(card) for card in group.get("cards", ())
        )
        normalized["articles"] = tuple(
            _normalize_theme_article(article) for article in group.get("articles", ())
        )
        return normalized
    return group


def _normalize_position_card(card: Any) -> Any:
    if isinstance(card, PositionCard):
        return {
            "ticker": card.ticker,
            "current_value_eur": _format_eur(card.current_value_eur),
            "total_pnl_pct": _format_percent(card.total_pnl_pct, places=1),
            "daily_change_pct": _format_percent(card.daily_change_pct, places=1),
        }
    return card


def _normalize_theme_article(article: Any) -> Any:
    if isinstance(article, ThemeArticle):
        return {
            "title": article.title,
            "source": article.source,
            "href": article.href,
            "published_at_label": _format_published_at_label(article.published_at),
            "primary_entity": article.primary_entity or "",
            "composite_weight_percent": _format_percent(
                article.composite_weight * Decimal("100"),
                places=2,
            ),
            "affects_themes": article.affects_themes,
        }
    if isinstance(article, Mapping):
        normalized = dict(article)
        if "published_at_label" not in normalized and "published_at" in normalized:
            normalized["published_at_label"] = _format_published_at_label(
                str(normalized["published_at"])
            )
        if (
            "composite_weight_percent" not in normalized
            and "composite_weight" in normalized
        ):
            normalized["composite_weight_percent"] = _format_percent(
                _to_decimal(normalized["composite_weight"]) * Decimal("100"),
                places=2,
            )
        return normalized
    return article


def _normalize_concentrated_exposure(row: Any) -> Any:
    if isinstance(row, ConcentratedExposureRow):
        return {
            "entity": row.entity,
            "composite_weight_percent": _format_percent(
                row.composite_weight * Decimal("100"),
                places=2,
            ),
            "path_count": row.path_count,
        }
    if isinstance(row, Mapping):
        normalized = dict(row)
        if (
            "composite_weight_percent" not in normalized
            and "composite_weight" in normalized
        ):
            normalized["composite_weight_percent"] = _format_percent(
                _to_decimal(normalized["composite_weight"]) * Decimal("100"),
                places=2,
            )
        return normalized
    return row


def _iter_mapping_items(group: Any, key: str) -> Sequence[Mapping[str, Any]]:
    if isinstance(group, Mapping):
        value = group.get(key, ())
        if isinstance(value, Sequence):
            return tuple(item for item in value if isinstance(item, Mapping))
    return ()


def _inline_css(html: str) -> str:
    _configure_cssutils_logging()
    return transform(html)


def _configure_cssutils_logging() -> None:
    global _CSSUTILS_CONFIGURED

    if _CSSUTILS_CONFIGURED:
        return
    logging.getLogger("CSSUTILS").setLevel(logging.CRITICAL)
    _CSSUTILS_CONFIGURED = True


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for line_break in soup.find_all("br"):
        line_break.replace_with("\n")

    sections: list[str] = []
    for section in soup.select("[data-section]"):
        text = section.get_text("\n", strip=True)
        if text:
            sections.append(text)
    if not sections:
        fallback = soup.get_text("\n", strip=True)
        return _normalize_whitespace(fallback)
    return "\n\n".join(_normalize_whitespace(section) for section in sections)


def _count_words(text: str) -> int:
    return len(WORD_RE.findall(text))


def _format_eur(value: Decimal) -> str:
    return f"€{value:,.2f}"


def _format_percent(value: Decimal, *, places: int) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.{places}f}%"


def _format_published_at_label(value: str) -> str:
    raw_value = value.strip()
    if not raw_value:
        return raw_value

    try:
        parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except ValueError:
        return raw_value

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).strftime("%H:%M UTC")


def _normalize_whitespace(text: str) -> str:
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))
