"""Saturday deep-brief orchestration."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path

from .daily import (
    DEFAULT_RECIPIENTS_PATH,
    DEFAULT_THEMES_PATH,
    PipelineResult,
    run_daily,
)


def run_deep(
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
    now: datetime | None = None,
) -> PipelineResult:
    """Run the Saturday deep-brief pipeline."""

    return run_daily(
        send=send,
        recipients_override=recipients_override,
        from_addr=from_addr,
        database_path=database_path,
        settings_path=settings_path,
        recipients_path=recipients_path,
        themes_path=themes_path,
        reuse_seen_db=reuse_seen_db,
        ignore_seen_db=ignore_seen_db,
        week_ahead_items=week_ahead_items or (),
        mode="deep",
        now=now,
    )
