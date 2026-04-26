"""Theme grouping helpers for renderer assembly."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import yaml

from src.analyzer.ranker import RankedArticle
from src.analyzer.theme_flash import ThemeFlash
from src.config import Settings, load_settings
from src.exposure.models import ExposureEntry
from src.pnl.models import PnLSnapshot

DEFAULT_THEMES_PATH = Path(__file__).resolve().parents[2] / "config" / "themes.yaml"


@dataclass(frozen=True)
class PositionCard:
    ticker: str
    current_value_eur: Decimal
    total_pnl_pct: Decimal
    daily_change_pct: Decimal


@dataclass(frozen=True)
class ThemeArticle:
    title: str
    source: str
    href: str
    published_at: str
    primary_entity: str | None
    composite_weight: Decimal
    affects_themes: tuple[str, ...]


@dataclass(frozen=True)
class ThemeGroup:
    name: str
    description: str
    cards: tuple[PositionCard, ...]
    articles: tuple[ThemeArticle, ...]
    flash_text: str | None = None


@dataclass(frozen=True)
class ConcentratedExposureRow:
    entity: str
    composite_weight: Decimal
    path_count: int


@dataclass(frozen=True)
class _ThemeDefinition:
    name: str
    description: str


@dataclass(frozen=True)
class _EntityTheme:
    primary_theme: str
    secondary_themes: tuple[str, ...]


def build_theme_groups(
    *,
    ranked_articles: list[RankedArticle],
    position_snapshots: Mapping[str, PnLSnapshot],
    theme_flashes: list[ThemeFlash],
    themes_path: str | Path = DEFAULT_THEMES_PATH,
    theme_item_cap: int | None = None,
    settings: Settings | None = None,
) -> tuple[ThemeGroup, ...]:
    """Group portfolio cards and ranked news under configured themes."""

    theme_definitions, entity_themes = _load_theme_catalog(themes_path)
    resolved_settings = settings or load_settings()
    item_cap = (
        theme_item_cap
        if theme_item_cap is not None
        else resolved_settings.theme_item_cap
    )
    flash_lookup = {flash.theme: flash.text for flash in theme_flashes}

    cards_by_theme = {theme.name: [] for theme in theme_definitions}
    for ticker, snapshot in position_snapshots.items():
        entity_theme = entity_themes.get(ticker)
        if entity_theme is None:
            continue
        cards_by_theme[entity_theme.primary_theme].append(
            PositionCard(
                ticker=ticker,
                current_value_eur=snapshot.current_value_eur,
                total_pnl_pct=snapshot.total_pnl_pct,
                daily_change_pct=snapshot.daily_delta.change_pct,
            )
        )

    articles_by_theme = {theme.name: [] for theme in theme_definitions}
    theme_order = {theme.name: index for index, theme in enumerate(theme_definitions)}
    for article in ranked_articles:
        primary_theme = _resolve_primary_theme(article, entity_themes)
        if primary_theme is None:
            continue
        articles_by_theme[primary_theme].append(
            ThemeArticle(
                title=article.article.title,
                source=article.article.source,
                href=article.article.url,
                published_at=article.article.published_at,
                primary_entity=article.primary_entity,
                composite_weight=article.composite_weight,
                affects_themes=_resolve_affects_themes(
                    article.matched_entities,
                    primary_theme=primary_theme,
                    entity_themes=entity_themes,
                    theme_order=theme_order,
                ),
            )
        )

    theme_groups: list[ThemeGroup] = []
    for theme in theme_definitions:
        cards = tuple(
            sorted(
                cards_by_theme[theme.name],
                key=lambda item: (-item.current_value_eur, item.ticker),
            )
        )
        articles = tuple(articles_by_theme[theme.name][:item_cap])
        flash_text = flash_lookup.get(theme.name)
        if not cards and not articles and flash_text is None:
            continue
        theme_groups.append(
            ThemeGroup(
                name=theme.name,
                description=theme.description,
                cards=cards,
                articles=articles,
                flash_text=flash_text,
            )
        )

    return tuple(theme_groups)


def build_concentrated_exposures(
    exposure_map: Mapping[str, ExposureEntry],
    *,
    threshold_percent: Decimal | None = None,
    settings: Settings | None = None,
) -> tuple[ConcentratedExposureRow, ...]:
    """Return entities whose composite exposure clears the configured threshold."""

    resolved_threshold = threshold_percent
    if resolved_threshold is None:
        resolved_settings = settings or load_settings()
        resolved_threshold = Decimal(str(resolved_settings.exposure_threshold_percent))

    threshold = resolved_threshold / Decimal("100")
    rows = [
        ConcentratedExposureRow(
            entity=entry.entity,
            composite_weight=entry.composite_weight,
            path_count=len(entry.paths),
        )
        for entry in exposure_map.values()
        if entry.composite_weight >= threshold
    ]
    rows.sort(key=lambda row: (-row.composite_weight, row.entity))
    return tuple(rows)


def _load_theme_catalog(
    path: str | Path,
) -> tuple[tuple[_ThemeDefinition, ...], dict[str, _EntityTheme]]:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    theme_payload = payload.get("themes", {})
    entity_payload = payload.get("entities", {})

    themes = tuple(
        _ThemeDefinition(
            name=name,
            description=str(config.get("description", "")).strip(),
        )
        for name, config in theme_payload.items()
    )
    entities = {
        entity: _EntityTheme(
            primary_theme=str(config.get("primary_theme", "")).strip(),
            secondary_themes=tuple(config.get("secondary_themes", [])),
        )
        for entity, config in entity_payload.items()
    }
    return themes, entities


def _resolve_primary_theme(
    article: RankedArticle,
    entity_themes: Mapping[str, _EntityTheme],
) -> str | None:
    if article.primary_entity and article.primary_entity in entity_themes:
        return entity_themes[article.primary_entity].primary_theme
    for entity in article.matched_entities:
        if entity in entity_themes:
            return entity_themes[entity].primary_theme
    return None


def _resolve_affects_themes(
    matched_entities: tuple[str, ...],
    *,
    primary_theme: str,
    entity_themes: Mapping[str, _EntityTheme],
    theme_order: Mapping[str, int],
) -> tuple[str, ...]:
    affects: set[str] = set()
    for entity in matched_entities:
        theme_info = entity_themes.get(entity)
        if theme_info is None:
            continue
        affects.add(theme_info.primary_theme)
        affects.update(theme_info.secondary_themes)
    affects.discard(primary_theme)
    return tuple(
        sorted(affects, key=lambda theme: (theme_order.get(theme, 10**9), theme))
    )
