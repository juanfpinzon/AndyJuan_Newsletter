"""Daily pipeline orchestration."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from src.analyzer import (
    ArticleCandidate,
    Synthesis,
    ThemeFlash,
    filter_ai_take,
    generate_synthesis,
    generate_theme_flash,
    rank_news,
)
from src.config import Settings, load_settings
from src.entity_match.matcher import EntityMatcher
from src.exposure.resolver import compute_exposure
from src.fetcher.macro_rss import MacroRSSReader
from src.fetcher.models import Article
from src.fetcher.newsdata import NewsDataClient
from src.lookthrough.resolver import resolve_lookthrough
from src.pnl import compute_pnl, compute_total
from src.portfolio.loader import load_portfolio
from src.portfolio.models import Position
from src.pricing import fetch_prices
from src.renderer import build_concentrated_exposures, build_theme_groups, render_email
from src.renderer.render import RenderedEmail
from src.sender import SendResult, send_email
from src.storage.db import init_db
from src.utils.log import get_logger

DEFAULT_RECIPIENTS_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "recipients.yaml"
)
DEFAULT_THEMES_PATH = Path(__file__).resolve().parents[2] / "config" / "themes.yaml"
MAX_NEWS_QUERY_TERMS = 6
# Precious-metals aliases generate broad macro/news noise for the current matcher.
NOISE_NEWS_QUERY_TERMS = {"GOLD", "SILVER"}


@dataclass(frozen=True)
class PipelineResult:
    mode: str
    rendered_email: RenderedEmail
    send_result: SendResult | None
    run_id: int


def run_daily(
    *,
    send: bool = True,
    recipients_override: Sequence[str] | None = None,
    from_addr: str | None = None,
    database_path: str | Path | None = None,
    settings_path: str | Path | None = None,
    recipients_path: str | Path = DEFAULT_RECIPIENTS_PATH,
    themes_path: str | Path = DEFAULT_THEMES_PATH,
    reuse_seen_db: bool = False,
    ignore_seen_db: bool = False,
    week_ahead_items: Sequence[Mapping[str, str]] | None = None,
    mode: str = "daily",
    now: datetime | None = None,
) -> PipelineResult:
    """Run the daily portfolio radar pipeline."""

    resolved_now = _resolve_now(now)
    settings = load_settings(settings_path)
    db_path = Path(database_path or settings.database_path)
    init_db(db_path)
    run_id = _insert_run_start(db_path, mode=mode, started_at=resolved_now)
    llm_call_baseline = _last_llm_call_id(db_path)

    try:
        result = asyncio.run(
            _run_pipeline_async(
                mode=mode,
                send=send,
                settings=settings,
                db_path=db_path,
                recipients_override=recipients_override,
                recipients_path=recipients_path,
                themes_path=themes_path,
                from_addr=from_addr,
                reuse_seen_db=reuse_seen_db,
                ignore_seen_db=ignore_seen_db,
                week_ahead_items=week_ahead_items,
                now=resolved_now,
                run_id=run_id,
            )
        )
    except Exception as exc:  # noqa: BLE001
        completed_at = _resolve_now()
        usage = _summarize_llm_usage_since(db_path, baseline_id=llm_call_baseline)
        _update_run(
            db_path,
            run_id=run_id,
            completed_at=completed_at,
            status="failed",
            error=str(exc),
            recipient_count=0,
            usage=usage,
        )
        raise

    completed_at = _resolve_now()
    usage = _summarize_llm_usage_since(db_path, baseline_id=llm_call_baseline)
    _update_run(
        db_path,
        run_id=run_id,
        completed_at=completed_at,
        status="success",
        error=None,
        recipient_count=(len(result.recipients) if send else 0),
        usage=usage,
    )
    return PipelineResult(
        mode=mode,
        rendered_email=result.rendered_email,
        send_result=result.send_result,
        run_id=run_id,
    )


@dataclass(frozen=True)
class _PipelineState:
    rendered_email: RenderedEmail
    send_result: SendResult | None
    recipients: tuple[str, ...]


async def _run_pipeline_async(
    *,
    mode: str,
    send: bool,
    settings: Settings,
    db_path: Path,
    recipients_override: Sequence[str] | None,
    recipients_path: str | Path,
    themes_path: str | Path,
    from_addr: str | None,
    reuse_seen_db: bool,
    ignore_seen_db: bool,
    week_ahead_items: Sequence[Mapping[str, str]] | None,
    now: datetime,
    run_id: int,
) -> _PipelineState:
    positions = load_portfolio()
    lookthrough = await resolve_lookthrough(positions)
    exposure_map = compute_exposure(positions, lookthrough)
    prices = fetch_prices(
        [position.ticker for position in positions],
        base_currency="EUR",
        market_symbols=_build_market_symbols(positions),
    )
    position_snapshots = compute_pnl(positions, prices)
    total_pnl = compute_total(position_snapshots)

    news_client = NewsDataClient(
        api_key=os.getenv("NEWSDATA_API_KEY", ""),
        db_path=db_path,
    )
    if reuse_seen_db:
        news_articles = news_client.load_cached_articles(hours=24, now=now)
    else:
        news_articles = await _fetch_news_batches(
            news_client,
            queries=_build_news_queries(positions, exposure_map),
            ignore_seen_db=ignore_seen_db,
        )

    macro_reader = MacroRSSReader()
    macro_articles = await macro_reader.fetch_macro(hours=24, now=now)
    matcher = EntityMatcher.from_themes_file(themes_path=themes_path)
    candidates = _build_article_candidates(news_articles, matcher)
    ranked_articles = (
        rank_news(candidates, exposure_map, settings=settings) if candidates else []
    )

    theme_flashes = _generate_theme_flashes(
        ranked_articles,
        themes_path=themes_path,
        settings=settings,
    )
    synthesis = _generate_synthesis(
        theme_flashes,
        ranked_articles,
        exposure_map,
        mode=mode,
        week_ahead_items=week_ahead_items or (),
        settings=settings,
    )

    base_context = _build_context(
        mode=mode,
        now=now,
        positions=positions,
        position_snapshots=position_snapshots,
        total_pnl=total_pnl,
        exposure_map=exposure_map,
        ranked_articles=ranked_articles,
        theme_flashes=[],
        synthesis_paragraphs=(),
        macro_articles=macro_articles,
        themes_path=themes_path,
        week_ahead_items=week_ahead_items or (),
    )
    rendered_factual = render_email(base_context, mode=mode)

    filtered_theme_flashes = _filter_theme_flashes(
        theme_flashes,
        rendered_content=rendered_factual.text,
        settings=settings,
    )
    synthesis_paragraphs = _filter_synthesis(
        synthesis,
        rendered_content=rendered_factual.text,
        settings=settings,
    )

    final_context = _build_context(
        mode=mode,
        now=now,
        positions=positions,
        position_snapshots=position_snapshots,
        total_pnl=total_pnl,
        exposure_map=exposure_map,
        ranked_articles=ranked_articles,
        theme_flashes=filtered_theme_flashes,
        synthesis_paragraphs=synthesis_paragraphs,
        macro_articles=macro_articles,
        themes_path=themes_path,
        week_ahead_items=week_ahead_items or (),
    )
    rendered_email = render_email(final_context, mode=mode)

    recipients = _resolve_recipients(recipients_path, recipients_override)
    send_result = None
    if send:
        send_result = send_email(
            to=list(recipients),
            subject=_build_subject(mode, now),
            html=rendered_email.html,
            text=rendered_email.text,
            from_addr=from_addr or os.getenv("EMAIL_FROM", ""),
        )
        get_logger("pipeline").info(
            "pipeline_email_sent",
            mode=mode,
            run_id=run_id,
            recipient_count=len(recipients),
        )

    return _PipelineState(
        rendered_email=rendered_email,
        send_result=send_result,
        recipients=recipients,
    )


def _build_article_candidates(
    articles: Sequence[Article],
    matcher: EntityMatcher,
) -> list[ArticleCandidate]:
    return [
        ArticleCandidate(
            article=article,
            matched_entities=tuple(match.entity for match in matcher.match(article)),
        )
        for article in articles
    ]


async def _fetch_news_batches(
    news_client: NewsDataClient,
    *,
    queries: Sequence[str],
    ignore_seen_db: bool,
) -> list[Article]:
    seen_urls: set[str] = set()
    articles: list[Article] = []
    for query in queries:
        batch = await news_client.fetch_news(
            query,
            hours=24,
            ignore_seen_db=ignore_seen_db,
        )
        for article in batch:
            if article.url in seen_urls:
                continue
            seen_urls.add(article.url)
            articles.append(article)
    return articles


def _generate_theme_flashes(
    ranked_articles,
    *,
    themes_path: str | Path,
    settings: Settings,
) -> list[ThemeFlash]:
    grouped_articles = _group_articles_by_theme(ranked_articles, themes_path)
    flashes: list[ThemeFlash] = []
    for theme, articles in grouped_articles.items():
        flashes.append(generate_theme_flash(theme, articles, settings=settings))
    return flashes


def _generate_synthesis(
    theme_flashes: Sequence[ThemeFlash],
    ranked_articles,
    exposure_map,
    *,
    mode: str,
    week_ahead_items: Sequence[Mapping[str, str]],
    settings: Settings,
) -> Synthesis | None:
    if not ranked_articles:
        return None
    return generate_synthesis(
        list(theme_flashes),
        list(ranked_articles),
        exposure_map,
        mode=mode,
        week_ahead_items=week_ahead_items,
        settings=settings,
    )


def _filter_theme_flashes(
    theme_flashes: Sequence[ThemeFlash],
    *,
    rendered_content: str,
    settings: Settings,
) -> list[ThemeFlash]:
    filtered: list[ThemeFlash] = []
    for flash in theme_flashes:
        filtered_text = filter_ai_take(
            rendered_content,
            flash.text,
            settings=settings,
        )
        if filtered_text is None:
            continue
        filtered.append(
            ThemeFlash(
                theme=flash.theme,
                text=filtered_text,
                sentence_count=flash.sentence_count,
            )
        )
    return filtered


def _filter_synthesis(
    synthesis: Synthesis | None,
    *,
    rendered_content: str,
    settings: Settings,
) -> tuple[str, ...]:
    if synthesis is None:
        return ()

    filtered_text = filter_ai_take(
        rendered_content,
        synthesis.text,
        settings=settings,
    )
    if filtered_text is None:
        return ()
    # The fact-checker contract is binary today: pass through the original text or
    # reject it entirely. If it starts returning partial redactions, this helper
    # must rebuild paragraphs from filtered_text instead of synthesis.paragraphs.
    return synthesis.paragraphs


def _build_context(
    *,
    mode: str,
    now: datetime,
    positions: Sequence[Position],
    position_snapshots,
    total_pnl,
    exposure_map,
    ranked_articles,
    theme_flashes: Sequence[ThemeFlash],
    synthesis_paragraphs: Sequence[str],
    macro_articles: Sequence[Article],
    themes_path: str | Path,
    week_ahead_items: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    theme_groups = build_theme_groups(
        ranked_articles=list(ranked_articles),
        position_snapshots=position_snapshots,
        theme_flashes=list(theme_flashes),
        themes_path=themes_path,
    )
    concentrated_exposures = build_concentrated_exposures(exposure_map)
    entity_themes = _load_entity_primary_themes(themes_path)

    return {
        "title": (
            "Saturday Deep Portfolio Brief"
            if mode == "deep"
            else "Daily Portfolio Radar"
        ),
        "subtitle": "Position-aware brief for Juan and Andrea",
        "mode_label": "Saturday Deep" if mode == "deep" else "Daily",
        "generated_for_date": _format_display_date(now),
        "total_pnl": {
            "current_value_total_eur": _format_eur(total_pnl.current_value_total_eur),
            "total_pnl_eur": _format_signed_eur(total_pnl.total_pnl_eur),
            "total_pnl_pct": _format_percent(total_pnl.total_pnl_pct, places=2),
            "daily_pnl_eur": _format_signed_eur(total_pnl.daily_pnl_eur),
        },
        "position_rows": _build_position_rows(
            positions,
            position_snapshots,
            entity_themes=entity_themes,
        ),
        "concentrated_exposures": concentrated_exposures,
        "theme_groups": theme_groups,
        "synthesis_paragraphs": tuple(synthesis_paragraphs),
        "deep_synthesis_paragraphs": tuple(synthesis_paragraphs),
        "macro_items": _build_macro_items(macro_articles),
        "week_ahead_items": tuple(dict(item) for item in week_ahead_items),
    }


def _build_position_rows(
    positions: Sequence[Position],
    position_snapshots,
    *,
    entity_themes: Mapping[str, str],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for position in positions:
        snapshot = position_snapshots[position.ticker]
        rows.append(
            {
                "ticker": position.ticker,
                "current_value_eur": _format_eur(snapshot.current_value_eur),
                "total_pnl_pct": _format_percent(snapshot.total_pnl_pct, places=1),
                "daily_change_pct": _format_percent(
                    snapshot.daily_delta.change_pct,
                    places=1,
                ),
                "theme": entity_themes.get(position.ticker, ""),
            }
        )
    rows.sort(key=lambda row: row["ticker"])
    return rows


def _build_macro_items(macro_articles: Sequence[Article]) -> list[dict[str, str]]:
    return [
        {
            "title": article.title,
            "source": article.source,
            "href": article.url,
            "published_at_label": _format_published_at_label(article.published_at),
        }
        for article in macro_articles
    ]


def _build_news_queries(positions: Sequence[Position], exposure_map) -> tuple[str, ...]:
    portfolio_tickers = {position.ticker for position in positions}
    direct_tickers = [
        position.ticker for position in positions if position.asset_type == "stock"
    ]
    exposure_entities = [
        entry.entity
        for entry in sorted(
            exposure_map.values(),
            key=lambda item: (-item.composite_weight, item.entity),
        )
        if entry.entity not in portfolio_tickers
        and entry.entity not in NOISE_NEWS_QUERY_TERMS
    ]
    query_terms: list[str] = []
    for term in [*direct_tickers, *exposure_entities]:
        if term not in query_terms:
            query_terms.append(term)
        if len(query_terms) >= MAX_NEWS_QUERY_TERMS:
            break
    return tuple(query_terms)


def _build_market_symbols(positions: Sequence[Position]) -> dict[str, str]:
    return {
        position.ticker: position.market_symbol
        for position in positions
        if position.market_symbol
    }


def _load_entity_primary_themes(path: str | Path) -> dict[str, str]:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    entities = payload.get("entities", {})
    return {
        entity: str(config.get("primary_theme", "")).strip()
        for entity, config in entities.items()
    }


def _group_articles_by_theme(
    ranked_articles, themes_path: str | Path
) -> dict[str, list[Any]]:
    entity_themes = _load_entity_primary_themes(themes_path)
    grouped: dict[str, list[Any]] = {}
    for article in ranked_articles:
        theme = _resolve_primary_theme(article, entity_themes)
        if not theme:
            continue
        grouped.setdefault(theme, []).append(article)
    return grouped


def _resolve_primary_theme(article, entity_themes: Mapping[str, str]) -> str | None:
    if article.primary_entity and article.primary_entity in entity_themes:
        return entity_themes[article.primary_entity]
    for entity in article.matched_entities:
        if entity in entity_themes:
            return entity_themes[entity]
    return None


def _resolve_recipients(
    recipients_path: str | Path,
    recipients_override: Sequence[str] | None,
) -> tuple[str, ...]:
    if recipients_override is not None:
        return tuple(
            str(value).strip() for value in recipients_override if str(value).strip()
        )

    payload = yaml.safe_load(Path(recipients_path).read_text(encoding="utf-8")) or {}
    recipients = payload.get("recipients", {})
    emails = [
        str(config.get("email", "")).strip()
        for config in recipients.values()
        if str(config.get("email", "")).strip()
    ]
    return tuple(emails)


def _build_subject(mode: str, now: datetime) -> str:
    prefix = (
        "Saturday Deep Portfolio Brief"
        if mode == "deep"
        else "Daily Portfolio Radar"
    )
    return f"{prefix} - {now.date().isoformat()}"


def _insert_run_start(db_path: Path, *, mode: str, started_at: datetime) -> int:
    database = init_db(db_path)
    cursor = database.conn.execute(
        """
        insert into runs (
            mode,
            started_at,
            completed_at,
            status,
            error,
            recipient_count,
            tokens_in,
            tokens_out,
            cost_usd
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            mode,
            started_at.isoformat(),
            None,
            "running",
            None,
            0,
            0,
            0,
            0.0,
        ),
    )
    database.conn.commit()
    return int(cursor.lastrowid)


def _update_run(
    db_path: Path,
    *,
    run_id: int,
    completed_at: datetime,
    status: str,
    error: str | None,
    recipient_count: int,
    usage: dict[str, Decimal],
) -> None:
    database = init_db(db_path)
    database.conn.execute(
        """
        update runs
        set completed_at = ?,
            status = ?,
            error = ?,
            recipient_count = ?,
            tokens_in = ?,
            tokens_out = ?,
            cost_usd = ?
        where id = ?
        """,
        (
            completed_at.isoformat(),
            status,
            error,
            recipient_count,
            int(usage["tokens_in"]),
            int(usage["tokens_out"]),
            float(usage["cost_usd"]),
            run_id,
        ),
    )
    database.conn.commit()


def _last_llm_call_id(db_path: Path) -> int:
    database = init_db(db_path)
    row = database.conn.execute("select coalesce(max(id), 0) from llm_calls").fetchone()
    assert row is not None
    return int(row[0] or 0)


def _summarize_llm_usage_since(
    db_path: Path,
    *,
    baseline_id: int,
) -> dict[str, Decimal]:
    database = init_db(db_path)
    row = database.conn.execute(
        """
        select
            coalesce(sum(tokens_in), 0),
            coalesce(sum(tokens_out), 0),
            coalesce(sum(cost_usd), 0)
        from llm_calls
        where id > ?
        """,
        (baseline_id,),
    ).fetchone()
    assert row is not None
    return {
        "tokens_in": Decimal(str(row[0] or 0)),
        "tokens_out": Decimal(str(row[1] or 0)),
        "cost_usd": Decimal(str(row[2] or 0)),
    }


def _format_eur(value: Decimal) -> str:
    return f"€{value:,.2f}"


def _format_signed_eur(value: Decimal) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}€{value:,.2f}"


def _format_percent(value: Decimal, *, places: int) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.{places}f}%"


def _format_display_date(value: datetime) -> str:
    return f"{value.strftime('%B')} {value.day}, {value.year}"


def _format_published_at_label(value: str) -> str:
    if not value.strip():
        return ""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).strftime("%H:%M UTC")


def _resolve_now(value: datetime | None = None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
