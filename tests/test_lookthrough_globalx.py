from decimal import Decimal
from pathlib import Path

import httpx
import pytest
import respx

from src.lookthrough.adapters.globalx import GlobalxAdapter
from src.lookthrough.models import LookthroughFailure

FIXTURES = Path(__file__).parent / "fixtures" / "etf_holdings" / "globalx"


@pytest.mark.asyncio
@respx.mock
async def test_globalx_adapter_returns_top_ten_for_sil() -> None:
    adapter = GlobalxAdapter()
    payload = (FIXTURES / "sil.csv").read_text(encoding="utf-8")
    respx.get("https://www.globalxetfs.com/funds/sil/holdings.csv").mock(
        return_value=httpx.Response(200, text=payload)
    )

    holdings = await adapter.fetch("SIL")

    assert len(holdings) == 10
    assert holdings[0].ticker == "WPM"
    assert holdings[0].weight == Decimal("15.58")


@pytest.mark.asyncio
@respx.mock
async def test_globalx_adapter_wraps_http_errors() -> None:
    adapter = GlobalxAdapter()
    respx.get("https://www.globalxetfs.com/funds/sil/holdings.csv").mock(
        return_value=httpx.Response(503)
    )

    with pytest.raises(LookthroughFailure) as excinfo:
        await adapter.fetch("SIL")

    assert excinfo.value.issuer == "globalx"
    assert excinfo.value.etf_id == "SIL"
