import json
from decimal import Decimal
from pathlib import Path

import pytest

from src.lookthrough.adapters.base import BaseAdapter
from src.lookthrough.models import Holding, LookthroughExhausted, LookthroughFailure
from src.lookthrough.resolver import resolve_lookthrough
from src.portfolio.models import Position


def make_position(
    ticker: str,
    *,
    issuer: str,
    asset_type: str = "etf",
    cost_basis_eur: str = "100",
) -> Position:
    return Position(
        ticker=ticker,
        isin=None,
        asset_type=asset_type,
        issuer=issuer,
        shares=Decimal("1"),
        cost_basis_eur=Decimal(cost_basis_eur),
        currency="EUR",
    )


class CapturingAdapter(BaseAdapter):
    issuer = "ishares"

    def __init__(self, holdings: list[Holding]) -> None:
        self.holdings = holdings
        self.seen_ids: list[str] = []

    async def fetch(self, etf_id: str) -> list[Holding]:
        self.seen_ids.append(etf_id)
        return self.holdings


class FailingAdapter(BaseAdapter):
    issuer = "ishares"

    async def fetch(self, etf_id: str) -> list[Holding]:
        raise LookthroughFailure("scrape failed", issuer="ishares", etf_id=etf_id)


@pytest.mark.asyncio
async def test_resolve_lookthrough_prefers_scraped_results_and_uses_aliases(
    tmp_path: Path,
) -> None:
    fallback_path = tmp_path / "etf_holdings.yaml"
    fallback_path.write_text(
        """
QDVE:
  issuer: iShares
  aliases:
    - IUIT
  top_10:
    - ticker: NVDA
      isin: null
      weight: 23.01
""".strip(),
        encoding="utf-8",
    )
    adapter = CapturingAdapter([Holding("NVDA", None, Decimal("23.01"))])

    resolved = await resolve_lookthrough(
        [make_position("QDVE", issuer="iShares")],
        adapters={"ishares": adapter},
        fallback_path=fallback_path,
    )

    assert adapter.seen_ids == ["IUIT"]
    assert resolved["QDVE"][0].ticker == "NVDA"


@pytest.mark.asyncio
async def test_resolve_lookthrough_falls_back_to_yaml_and_logs_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log_path = tmp_path / "lookthrough.jsonl"
    monkeypatch.setenv("LOG_FILE", str(log_path))
    monkeypatch.setenv("APP_ENV", "prod")

    fallback_path = tmp_path / "etf_holdings.yaml"
    fallback_path.write_text(
        """
QDVE:
  issuer: iShares
  aliases:
    - IUIT
  top_10:
    - ticker: NVDA
      isin: null
      weight: 23.01
    - ticker: AAPL
      isin: null
      weight: 18.53
""".strip(),
        encoding="utf-8",
    )

    resolved = await resolve_lookthrough(
        [make_position("QDVE", issuer="iShares")],
        adapters={"ishares": FailingAdapter()},
        fallback_path=fallback_path,
    )

    assert [holding.ticker for holding in resolved["QDVE"]] == ["NVDA", "AAPL"]

    log_lines = log_path.read_text(encoding="utf-8").splitlines()
    payload = json.loads(log_lines[-1])
    assert payload["event"] == "lookthrough_fallback_used"
    assert payload["issuer"] == "iShares"


@pytest.mark.asyncio
async def test_resolve_lookthrough_raises_when_scrape_and_yaml_are_unavailable(
    tmp_path: Path,
) -> None:
    fallback_path = tmp_path / "etf_holdings.yaml"
    fallback_path.write_text("{}", encoding="utf-8")

    with pytest.raises(LookthroughExhausted) as excinfo:
        await resolve_lookthrough(
            [make_position("QDVE", issuer="iShares")],
            adapters={"ishares": FailingAdapter()},
            fallback_path=fallback_path,
        )

    assert excinfo.value.ticker == "QDVE"
