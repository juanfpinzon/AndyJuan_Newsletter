"""VanEck holdings adapter."""

from __future__ import annotations

import httpx

from src.lookthrough.adapters._csv import parse_csv_holdings
from src.lookthrough.adapters.base import BaseAdapter
from src.lookthrough.models import Holding, LookthroughFailure
from src.utils.http import get_async_client


class VaneckAdapter(BaseAdapter):
    issuer = "vaneck"
    base_url = "https://www.vaneck.com/etf"

    async def fetch(self, etf_id: str) -> list[Holding]:
        url = f"{self.base_url}/{etf_id.lower()}/holdings.csv"
        try:
            async with get_async_client() as client:
                response = await client.get(url)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LookthroughFailure(
                f"Unable to fetch VanEck holdings for {etf_id}",
                issuer=self.issuer,
                etf_id=etf_id,
            ) from exc

        holdings = parse_csv_holdings(response.text)
        if not holdings:
            raise LookthroughFailure(
                f"Unable to parse VanEck holdings for {etf_id}",
                issuer=self.issuer,
                etf_id=etf_id,
            )
        return holdings[:10]
