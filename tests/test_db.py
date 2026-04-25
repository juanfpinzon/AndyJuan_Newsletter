from pathlib import Path

from src.storage.db import init_db


def test_init_db_creates_all_expected_tables() -> None:
    db = init_db(":memory:")

    assert {
        "runs",
        "articles_seen",
        "exposure_snapshots",
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
            "('runs', 'articles_seen', 'exposure_snapshots', 'llm_calls')"
        )
    ]

    assert sorted(created_tables) == [
        "articles_seen",
        "exposure_snapshots",
        "llm_calls",
        "runs",
    ]
