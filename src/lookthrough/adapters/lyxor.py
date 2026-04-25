"""Lyxor / Amundi holdings adapter."""

from __future__ import annotations

from decimal import Decimal

import httpx
from bs4 import BeautifulSoup

from src.lookthrough.adapters.base import BaseAdapter
from src.lookthrough.models import Holding, LookthroughFailure
from src.utils.http import get_async_client


class LyxorAdapter(BaseAdapter):
    issuer = "lyxor"
    base_url = "https://www.amundietf.com/products"

    async def fetch(self, etf_id: str) -> list[Holding]:
        url = f"{self.base_url}/{etf_id.lower()}/holdings"
        try:
            async with get_async_client() as client:
                response = await client.get(url)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LookthroughFailure(
                f"Unable to fetch Lyxor holdings for {etf_id}",
                issuer=self.issuer,
                etf_id=etf_id,
            ) from exc

        holdings = _parse_table(response.text)
        if not holdings:
            raise LookthroughFailure(
                f"Lyxor holdings unavailable for {etf_id}",
                issuer=self.issuer,
                etf_id=etf_id,
            )
        return holdings[:10]


def _parse_table(payload: str) -> list[Holding]:
    soup = BeautifulSoup(payload, "html.parser")
    table = soup.find("table", attrs={"data-test": "top-holdings"})
    if table is None:
        table = soup.find("table")
    if table is None:
        return []

    rows = table.find_all("tr")
    holdings: list[Holding] = []
    for row in rows[1:]:
        columns = row.find_all("td")
        if len(columns) < 3:
            continue

        holdings.append(
            Holding(
                ticker=columns[0].get_text(strip=True),
                isin=_optional_text(columns[1].get_text(strip=True)),
                weight=_parse_weight(columns[2].get_text(strip=True)),
            )
        )
    return holdings


def _optional_text(value: str) -> str | None:
    return value or None


def _parse_weight(value: str) -> Decimal:
    return Decimal(value.replace("%", "").strip())
