import inspect
from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from src.lookthrough.adapters.base import BaseAdapter
from src.lookthrough.models import Holding


class IncompleteAdapter(BaseAdapter):
    issuer = "test"

    async def fetch(self, etf_id: str) -> list[Holding]:
        return await super().fetch(etf_id)


def test_holding_is_frozen_with_decimal_weight() -> None:
    holding = Holding(ticker="NVDA", isin="US67066G1040", weight=Decimal("23.01"))

    assert isinstance(holding.weight, Decimal)

    with pytest.raises(FrozenInstanceError):
        holding.weight = Decimal("10")


@pytest.mark.asyncio
async def test_base_adapter_is_abstract_and_default_fetch_raises() -> None:
    assert inspect.isabstract(BaseAdapter)

    adapter = IncompleteAdapter()
    with pytest.raises(NotImplementedError):
        await adapter.fetch("QDVE")
