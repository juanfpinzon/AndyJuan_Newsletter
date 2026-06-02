from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from src.portfolio.models import Position
from src.storage.db import (
    cache_position_snapshot,
    init_db,
    load_latest_position_snapshot,
)


def test_init_db_creates_all_expected_tables() -> None:
    db = init_db(":memory:")

    assert {
        "runs",
        "articles_seen",
        "etf_holdings_cache",
        "exposure_snapshots",
        "position_snapshots",
        "llm_calls",
    }.issubset(set(db.table_names()))


def test_init_db_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "andyjuan.db"

    init_db(db_path)
    db = init_db(db_path)

    created_tables = [
        row[0]
        for row in db.conn.execute(
            "select name from sqlite_master where type = 'table' and name in "
            "('runs', 'articles_seen', 'etf_holdings_cache', 'position_snapshots', "
            "'exposure_snapshots', 'llm_calls')"
        )
    ]

    assert sorted(created_tables) == [
        "articles_seen",
        "etf_holdings_cache",
        "exposure_snapshots",
        "llm_calls",
        "position_snapshots",
        "runs",
    ]


def test_position_snapshot_roundtrip_preserves_live_metadata(tmp_path: Path) -> None:
    db_path = tmp_path / "andyjuan.db"
    snapshot_time = datetime(2026, 5, 15, 8, 30, tzinfo=UTC)

    cache_position_snapshot(
        db_path,
        source="snaptrade",
        positions=[
            Position(
                ticker="NVDA",
                isin="US67066G1040",
                asset_type="stock",
                issuer="NVIDIA Corporation",
                shares=Decimal("2.5"),
                cost_basis_eur=Decimal("155.10"),
                currency="USD",
                market_symbol=None,
                source="snaptrade",
                last_updated=snapshot_time,
            )
        ],
    )

    cached = load_latest_position_snapshot(db_path, source="snaptrade")

    assert cached == [
        Position(
            ticker="NVDA",
            isin="US67066G1040",
            asset_type="stock",
            issuer="NVIDIA Corporation",
            shares=Decimal("2.5"),
            cost_basis_eur=Decimal("155.10"),
            currency="USD",
            market_symbol=None,
            source="snaptrade",
            last_updated=snapshot_time,
        )
    ]
