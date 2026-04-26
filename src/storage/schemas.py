"""SQLite schema definitions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TableSchema:
    columns: dict[str, type]
    pk: str | tuple[str, ...] | None = None


TABLE_SCHEMAS: dict[str, TableSchema] = {
    "runs": TableSchema(
        columns={
            "id": int,
            "mode": str,
            "started_at": str,
            "completed_at": str,
            "status": str,
            "error": str,
            "recipient_count": int,
            "tokens_in": int,
            "tokens_out": int,
            "cost_usd": float,
        },
        pk="id",
    ),
    "articles_seen": TableSchema(
        columns={
            "id": int,
            "article_id": str,
            "source_url": str,
            "published_at": str,
            "seen_at": str,
            "title": str,
            "body": str,
            "source": str,
            "raw_tags_json": str,
        },
        pk="id",
    ),
    "exposure_snapshots": TableSchema(
        columns={
            "id": int,
            "run_id": str,
            "entity": str,
            "composite_weight": float,
            "paths_json": str,
            "created_at": str,
        },
        pk="id",
    ),
    "etf_holdings_cache": TableSchema(
        columns={
            "id": int,
            "ticker": str,
            "source_etf_id": str,
            "issuer": str,
            "holdings_json": str,
            "fetched_at": str,
        },
        pk="id",
    ),
    "llm_calls": TableSchema(
        columns={
            "id": int,
            "model": str,
            "prompt": str,
            "tokens_in": int,
            "tokens_out": int,
            "cost_usd": float,
            "success": int,
            "error": str,
            "created_at": str,
        },
        pk="id",
    ),
}
