from decimal import Decimal
from pathlib import Path

import httpx
import pytest
import respx

from src.lookthrough.adapters.vaneck import VaneckAdapter
from src.lookthrough.models import LookthroughFailure

FIXTURES = Path(__file__).parent / "fixtures" / "etf_holdings" / "vaneck"


@pytest.mark.asyncio
@respx.mock
async def test_vaneck_adapter_returns_top_ten_for_dfns() -> None:
    adapter = VaneckAdapter()
    payload = (FIXTURES / "dfns.csv").read_text(encoding="utf-8")
    respx.get("https://www.vaneck.com/etf/dfns/holdings.csv").mock(
        return_value=httpx.Response(200, text=payload)
    )

    holdings = await adapter.fetch("DFNS")

    assert len(holdings) == 10
    assert holdings[0].ticker == "PLTR"
    assert holdings[0].weight == Decimal("8.40")


@pytest.mark.asyncio
@respx.mock
async def test_vaneck_adapter_wraps_http_errors() -> None:
    adapter = VaneckAdapter()
    respx.get("https://www.vaneck.com/etf/dfns/holdings.csv").mock(
        return_value=httpx.Response(503)
    )

    with pytest.raises(LookthroughFailure) as excinfo:
        await adapter.fetch("DFNS")

    assert excinfo.value.issuer == "vaneck"
    assert excinfo.value.etf_id == "DFNS"
