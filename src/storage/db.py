"""Database helpers backed by sqlite-utils."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from sqlite_utils import Database

from .schemas import TABLE_SCHEMAS


def init_db(path: str | Path) -> Database:
    """Create the application database and all base tables idempotently."""

    database = _open_database(path)
    for table_name, schema in TABLE_SCHEMAS.items():
        database[table_name].create(
            schema.columns,
            pk=schema.pk,
            if_not_exists=True,
        )
    return database


def record_llm_call(
    db_path: str | Path,
    *,
    model: str,
    prompt: str,
    tokens_in: int,
    tokens_out: int,
    cost_usd: float,
    success: bool,
    error: str | None = None,
) -> None:
    """Persist a single LLM call attempt."""

    database = init_db(db_path)
    database["llm_calls"].insert(
        {
            "model": model,
            "prompt": prompt,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_usd": cost_usd,
            "success": int(success),
            "error": error,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )


def _open_database(path: str | Path) -> Database:
    if path == ":memory:":
        return Database(memory=True)

    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    return Database(connection)
