"""Refresh live ETF holdings and cache successful results."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_DATABASE_PATH = Path(os.getenv("DATABASE_PATH", "data/andyjuan.db"))


async def refresh_holdings(db_path: str | Path = DEFAULT_DATABASE_PATH) -> int:
    from src.lookthrough.issuers import normalize_issuer
    from src.lookthrough.models import LookthroughFailure
    from src.lookthrough.resolver import build_default_adapters, load_fallback_config
    from src.portfolio.loader import load_portfolio
    from src.storage.db import cache_etf_holdings

    portfolio = load_portfolio()
    fallback_config = load_fallback_config()
    adapters = build_default_adapters()
    issuer_totals: dict[str, dict[str, int]] = {}

    for position in portfolio:
        if position.asset_type != "etf" or not position.issuer:
            continue

        issuer_key = normalize_issuer(position.issuer)
        if issuer_key is None:
            continue

        stats = issuer_totals.setdefault(issuer_key, {"ok": 0, "fail": 0})
        adapter = adapters[issuer_key]
        lookup_id = _lookup_id(position.ticker, fallback_config.get(position.ticker))
        try:
            holdings = await adapter.fetch(lookup_id)
        except LookthroughFailure:
            stats["fail"] += 1
            print(f"{issuer_key:<8} {position.ticker:<6} FAIL")
            continue

        cache_etf_holdings(
            db_path,
            ticker=position.ticker,
            source_etf_id=lookup_id,
            issuer=position.issuer,
            holdings=[
                {
                    "ticker": holding.ticker,
                    "isin": holding.isin,
                    "weight": str(holding.weight),
                }
                for holding in holdings
            ],
        )
        stats["ok"] += 1
        print(f"{issuer_key:<8} {position.ticker:<6} OK")

    print("")
    print("issuer   ok  fail")
    for issuer_key, stats in sorted(issuer_totals.items()):
        print(f"{issuer_key:<8} {stats['ok']:<3} {stats['fail']:<3}")

    if all(stats["ok"] == 0 for stats in issuer_totals.values()):
        return 1
    return 0


def _lookup_id(ticker: str, fallback_entry: object) -> str:
    if isinstance(fallback_entry, dict):
        aliases = fallback_entry.get("aliases")
        if isinstance(aliases, list) and aliases:
            alias = str(aliases[0]).strip()
            if alias:
                return alias
    return ticker


def main() -> int:
    return asyncio.run(refresh_holdings())


if __name__ == "__main__":
    raise SystemExit(main())
