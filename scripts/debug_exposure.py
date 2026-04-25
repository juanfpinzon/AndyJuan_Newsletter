"""Print composite exposures and optional recent LLM cost totals."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from decimal import Decimal
from pathlib import Path

import yfinance as yf

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_DATABASE_PATH = Path(os.getenv("DATABASE_PATH", "data/andyjuan.db"))


async def render_exposure(costs: bool) -> None:
    from src.exposure.resolver import compute_exposure
    from src.lookthrough.resolver import resolve_lookthrough
    from src.portfolio.loader import load_portfolio
    from src.storage.db import summarize_llm_costs

    portfolio = load_portfolio()
    lookthrough = await resolve_lookthrough(portfolio)
    exposure = compute_exposure(portfolio, lookthrough)

    print("entity   weight    paths")
    for entry in exposure.values():
        paths = ", ".join(
            f"{path['source']}={_format_percent(path['weight'])}"
            for path in entry.paths
        )
        print(f"{entry.entity:<7} {_format_percent(entry.composite_weight):<8} {paths}")

    if not costs:
        return

    summary = summarize_llm_costs(DEFAULT_DATABASE_PATH)
    usd_total = summary["total_usd"]
    eurusd = _fetch_eurusd_rate()
    total_eur = usd_total / eurusd if eurusd else Decimal("0")
    print("")
    print(
        "Recent LLM costs: "
        f"USD {usd_total.quantize(Decimal('0.0001'))} | "
        f"EUR {total_eur.quantize(Decimal('0.0001'))}"
    )


def _format_percent(weight: Decimal) -> str:
    return f"{(weight * Decimal('100')).quantize(Decimal('0.01'))}%"


def _fetch_eurusd_rate() -> Decimal:
    history = yf.Ticker("EURUSD=X").history(period="5d")
    if history.empty:
        raise RuntimeError("EURUSD=X returned no FX history")
    close = history["Close"].dropna().iloc[-1]
    return Decimal(str(close))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--costs", action="store_true")
    args = parser.parse_args()
    asyncio.run(render_exposure(args.costs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
