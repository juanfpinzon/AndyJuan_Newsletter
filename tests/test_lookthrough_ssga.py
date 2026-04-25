from decimal import Decimal
from pathlib import Path

import httpx
import pytest
import respx

from src.lookthrough.adapters.ssga import SsgaAdapter
from src.lookthrough.models import LookthroughFailure

FIXTURES = Path(__file__).parent / "fixtures" / "etf_holdings" / "ssga"


@pytest.mark.asyncio
@respx.mock
async def test_ssga_adapter_returns_top_ten_for_spyy() -> None:
    adapter = SsgaAdapter()
    payload = (FIXTURES / "spyy.csv").read_text(encoding="utf-8")
    respx.get("https://www.ssga.com/etfs/spyy/holdings.csv").mock(
        return_value=httpx.Response(200, text=payload)
    )

    holdings = await adapter.fetch("SPYY")

    assert len(holdings) == 10
    assert holdings[0].ticker == "NVDA"
    assert holdings[0].weight == Decimal("4.82")


@pytest.mark.asyncio
@respx.mock
async def test_ssga_adapter_wraps_http_errors() -> None:
    adapter = SsgaAdapter()
    respx.get("https://www.ssga.com/etfs/spyy/holdings.csv").mock(
        return_value=httpx.Response(503)
    )

    with pytest.raises(LookthroughFailure) as excinfo:
        await adapter.fetch("SPYY")

    assert excinfo.value.issuer == "ssga"
    assert excinfo.value.etf_id == "SPYY"
