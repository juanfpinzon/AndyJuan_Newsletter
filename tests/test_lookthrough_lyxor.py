from decimal import Decimal
from pathlib import Path

import httpx
import pytest
import respx

from src.lookthrough.adapters.lyxor import LyxorAdapter, _parse_table
from src.lookthrough.models import Holding, LookthroughFailure

FIXTURES = Path(__file__).parent / "fixtures" / "etf_holdings" / "lyxor"


@pytest.mark.asyncio
@respx.mock
async def test_lyxor_adapter_returns_top_ten_when_markup_is_parseable() -> None:
    adapter = LyxorAdapter()
    payload = (FIXTURES / "bnke.html").read_text(encoding="utf-8")
    respx.get("https://www.amundietf.com/products/bnke/holdings").mock(
        return_value=httpx.Response(200, text=payload)
    )

    holdings = await adapter.fetch("BNKE")

    assert len(holdings) == 10
    assert holdings[0].ticker == "SAN"
    assert holdings[0].weight == Decimal("14.00")


@pytest.mark.asyncio
@respx.mock
async def test_lyxor_adapter_degrades_cleanly_when_holdings_are_unavailable() -> None:
    adapter = LyxorAdapter()
    payload = (FIXTURES / "missing.html").read_text(encoding="utf-8")
    respx.get("https://www.amundietf.com/products/bnke/holdings").mock(
        return_value=httpx.Response(200, text=payload)
    )

    with pytest.raises(LookthroughFailure) as excinfo:
        await adapter.fetch("BNKE")

    assert excinfo.value.issuer == "lyxor"
    assert excinfo.value.etf_id == "BNKE"


def test_parse_table_accepts_percentage_weights() -> None:
    holdings = _parse_table(
        """
        <table>
          <tr><th>Ticker</th><th>ISIN</th><th>Weight</th></tr>
          <tr><td>SAN</td><td>ES0113900J37</td><td>14.00%</td></tr>
        </table>
        """
    )

    assert holdings == [Holding("SAN", "ES0113900J37", Decimal("14.00"))]
