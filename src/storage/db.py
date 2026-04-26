"""Database helpers backed by sqlite-utils."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
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
        _ensure_columns(database, table_name, schema.columns)
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


def cache_etf_holdings(
    db_path: str | Path,
    *,
    ticker: str,
    source_etf_id: str,
    issuer: str,
    holdings: list[dict[str, str | None]],
) -> None:
    """Persist a successful ETF holdings fetch."""

    database = init_db(db_path)
    database["etf_holdings_cache"].insert(
        {
            "ticker": ticker,
            "source_etf_id": source_etf_id,
            "issuer": issuer,
            "holdings_json": json.dumps(holdings),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
    )


def summarize_llm_costs(
    db_path: str | Path,
    *,
    limit: int = 20,
) -> dict[str, Decimal]:
    """Summarize recent LLM costs."""

    database = init_db(db_path)
    rows = list(
        database.conn.execute(
            """
            select cost_usd
            from llm_calls
            order by created_at desc
            limit ?
            """,
            (limit,),
        )
    )
    total_usd = sum((Decimal(str(row[0] or 0)) for row in rows), start=Decimal("0"))
    return {
        "calls": Decimal(len(rows)),
        "total_usd": total_usd,
    }


def _open_database(path: str | Path) -> Database:
    if path == ":memory:":
        return Database(memory=True)

    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    return Database(connection)


def _ensure_columns(
    database: Database,
    table_name: str,
    columns: dict[str, type],
) -> None:
    existing = {column.name for column in database[table_name].columns}
    for column_name, column_type in columns.items():
        if column_name in existing:
            continue
        database[table_name].add_column(column_name, column_type)
