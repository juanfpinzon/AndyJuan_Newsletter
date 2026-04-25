from decimal import Decimal
from pathlib import Path

import httpx
import pytest
import respx

from src.lookthrough.adapters.ishares import IsharesAdapter
from src.lookthrough.models import LookthroughFailure

FIXTURES = Path(__file__).parent / "fixtures" / "etf_holdings" / "ishares"


@pytest.mark.asyncio
@respx.mock
async def test_ishares_adapter_returns_top_ten_for_iuit() -> None:
    adapter = IsharesAdapter()
    payload = (FIXTURES / "iuit.json").read_text(encoding="utf-8")
    respx.get("https://www.ishares.com/us/products/iuit/holdings.json").mock(
        return_value=httpx.Response(200, text=payload)
    )

    holdings = await adapter.fetch("IUIT")

    assert len(holdings) == 10
    assert holdings[0].ticker == "NVDA"
    assert holdings[0].weight == Decimal("23.01")


@pytest.mark.asyncio
@respx.mock
async def test_ishares_adapter_returns_top_ten_for_egln() -> None:
    adapter = IsharesAdapter()
    payload = (FIXTURES / "egln.json").read_text(encoding="utf-8")
    respx.get("https://www.ishares.com/us/products/egln/holdings.json").mock(
        return_value=httpx.Response(200, text=payload)
    )

    holdings = await adapter.fetch("EGLN")

    assert len(holdings) == 10
    assert all(holding.ticker == "GOLD" for holding in holdings)


@pytest.mark.asyncio
@respx.mock
async def test_ishares_adapter_wraps_http_errors() -> None:
    adapter = IsharesAdapter()
    respx.get("https://www.ishares.com/us/products/iuit/holdings.json").mock(
        return_value=httpx.Response(503)
    )

    with pytest.raises(LookthroughFailure) as excinfo:
        await adapter.fetch("IUIT")

    assert excinfo.value.issuer == "ishares"
    assert excinfo.value.etf_id == "IUIT"
