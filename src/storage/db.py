"""Database helpers backed by sqlite-utils."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from sqlite_utils import Database

from src.portfolio.models import Position

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


POSITION_SNAPSHOT_RETENTION = 30


def cache_position_snapshot(
    db_path: str | Path,
    *,
    source: str,
    positions: Sequence[Position],
    retain: int = POSITION_SNAPSHOT_RETENTION,
) -> None:
    """Persist a portfolio snapshot for live-source fallback.

    Only the most recent ``retain`` snapshots per source are kept; older rows
    are pruned so the append-only table cannot grow without bound. Keeping the
    newest N (rather than a time window) guarantees the latest snapshot always
    survives for fallback even after a long live-source outage.
    """

    database = init_db(db_path)
    captured_at = datetime.now(timezone.utc).isoformat()
    database["position_snapshots"].insert(
        {
            "source": source,
            "positions_json": json.dumps(
                [_serialize_position(position) for position in positions]
            ),
            "captured_at": captured_at,
        }
    )
    _prune_position_snapshots(database, source=source, retain=retain)


def _prune_position_snapshots(
    database: Database,
    *,
    source: str,
    retain: int,
) -> None:
    database.conn.execute(
        """
        delete from position_snapshots
        where source = ?
          and id not in (
            select id
            from position_snapshots
            where source = ?
            order by captured_at desc, id desc
            limit ?
          )
        """,
        (source, source, max(retain, 1)),
    )
    database.conn.commit()


def load_latest_position_snapshot(
    db_path: str | Path,
    *,
    source: str,
) -> list[Position]:
    """Return the newest cached position snapshot for a given live source."""

    database = init_db(db_path)
    row = database.conn.execute(
        """
        select positions_json, captured_at
        from position_snapshots
        where source = ?
        order by captured_at desc
        limit 1
        """,
        (source,),
    ).fetchone()
    if row is None:
        return []

    payload = json.loads(row[0] or "[]")
    if not isinstance(payload, list):
        return []

    return [
        _deserialize_position(item, fallback_captured_at=row[1]) for item in payload
    ]


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


def _serialize_position(position: Position) -> dict[str, str | None]:
    return {
        "ticker": position.ticker,
        "isin": position.isin,
        "asset_type": position.asset_type,
        "issuer": position.issuer,
        "shares": str(position.shares),
        "cost_basis_eur": str(position.cost_basis_eur),
        "currency": position.currency,
        "market_symbol": position.market_symbol,
        "source": position.source,
        "last_updated": (
            position.last_updated.astimezone(timezone.utc).isoformat()
            if position.last_updated is not None
            else None
        ),
    }


def _deserialize_position(
    payload: object,
    *,
    fallback_captured_at: str | None,
) -> Position:
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid cached position payload: {payload!r}")

    last_updated_raw = payload.get("last_updated") or fallback_captured_at
    last_updated = (
        datetime.fromisoformat(last_updated_raw) if last_updated_raw else None
    )
    return Position(
        ticker=str(payload["ticker"]),
        isin=_optional_string(payload.get("isin")),
        asset_type=str(payload["asset_type"]),
        issuer=_optional_string(payload.get("issuer")),
        shares=Decimal(str(payload["shares"])),
        cost_basis_eur=Decimal(str(payload["cost_basis_eur"])),
        currency=str(payload["currency"]),
        market_symbol=_optional_string(payload.get("market_symbol")),
        source=str(payload.get("source") or "snaptrade"),
        last_updated=last_updated,
    )


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
