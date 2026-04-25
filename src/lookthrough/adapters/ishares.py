"""iShares holdings adapter.

UCITS funds in the seeded portfolio still rely on YAML fallback until a validated
international holdings endpoint is added. See ADR 0003.
"""

from __future__ import annotations

import json
from decimal import Decimal

import httpx

from src.lookthrough.adapters.base import BaseAdapter
from src.lookthrough.models import Holding, LookthroughFailure
from src.utils.http import get_async_client


class IsharesAdapter(BaseAdapter):
    issuer = "ishares"
    base_url = "https://www.ishares.com/us/products"

    async def fetch(self, etf_id: str) -> list[Holding]:
        url = f"{self.base_url}/{etf_id.lower()}/holdings.json"
        try:
            async with get_async_client() as client:
                response = await client.get(url)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LookthroughFailure(
                f"Unable to fetch iShares holdings for {etf_id}",
                issuer=self.issuer,
                etf_id=etf_id,
            ) from exc

        try:
            payload = json.loads(response.text)
            holdings = [
                Holding(
                    ticker=str(row["ticker"]).strip(),
                    isin=_optional_text(row.get("isin")),
                    weight=Decimal(str(row["weight"])),
                )
                for row in payload["topHoldings"]
            ]
        except (KeyError, TypeError, ValueError) as exc:
            raise LookthroughFailure(
                f"Unable to parse iShares holdings for {etf_id}",
                issuer=self.issuer,
                etf_id=etf_id,
            ) from exc

        return holdings[:10]


def _optional_text(value: object) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    return text or None
