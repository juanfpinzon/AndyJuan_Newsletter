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
