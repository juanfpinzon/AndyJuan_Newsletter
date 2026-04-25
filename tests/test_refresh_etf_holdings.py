import importlib.util
from decimal import Decimal
from pathlib import Path

import pytest

from src.lookthrough import resolver as lookthrough_resolver
from src.lookthrough.models import Holding, LookthroughFailure
from src.portfolio import loader as portfolio_loader
from src.portfolio.models import Position
from src.storage import db as storage_db

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPOSITORY_ROOT / "scripts" / "refresh_etf_holdings.py"


def load_refresh_module():
    spec = importlib.util.spec_from_file_location("refresh_etf_holdings", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_position(
    ticker: str,
    *,
    asset_type: str,
    issuer: str | None,
) -> Position:
    return Position(
        ticker=ticker,
        isin=None,
        asset_type=asset_type,  # type: ignore[arg-type]
        issuer=issuer,
        shares=Decimal("1"),
        cost_basis_eur=Decimal("100"),
        currency="EUR",
    )


class SuccessfulAdapter:
    def __init__(self, holdings: list[Holding]) -> None:
        self.holdings = holdings
        self.seen_ids: list[str] = []

    async def fetch(self, etf_id: str) -> list[Holding]:
        self.seen_ids.append(etf_id)
        return self.holdings


class FailingAdapter:
    async def fetch(self, etf_id: str) -> list[Holding]:
        raise LookthroughFailure("boom", issuer="ishares", etf_id=etf_id)


@pytest.mark.asyncio
async def test_refresh_holdings_returns_nonzero_when_no_supported_etfs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = load_refresh_module()
    monkeypatch.setattr(
        portfolio_loader,
        "load_portfolio",
        lambda: [make_position("NVDA", asset_type="stock", issuer="NVIDIA")],
    )
    monkeypatch.setattr(lookthrough_resolver, "load_fallback_config", lambda: {})
    monkeypatch.setattr(lookthrough_resolver, "build_default_adapters", lambda: {})

    cached: list[dict[str, object]] = []
    monkeypatch.setattr(
        storage_db,
        "cache_etf_holdings",
        lambda *args, **kwargs: cached.append(kwargs),
    )

    exit_code = await module.refresh_holdings(tmp_path / "holdings.db")

    assert exit_code == 1
    assert cached == []


@pytest.mark.asyncio
async def test_refresh_holdings_returns_zero_when_an_issuer_succeeds(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = load_refresh_module()
    adapter = SuccessfulAdapter([Holding("NVDA", None, Decimal("100"))])
    monkeypatch.setattr(
        portfolio_loader,
        "load_portfolio",
        lambda: [make_position("QDVE", asset_type="etf", issuer="iShares")],
    )
    monkeypatch.setattr(
        lookthrough_resolver,
        "load_fallback_config",
        lambda: {"QDVE": {"aliases": ["IUIT"]}},
    )
    monkeypatch.setattr(
        lookthrough_resolver,
        "build_default_adapters",
        lambda: {"ishares": adapter},
    )

    cached: list[dict[str, object]] = []
    monkeypatch.setattr(
        storage_db,
        "cache_etf_holdings",
        lambda db_path, **kwargs: cached.append({"db_path": db_path, **kwargs}),
    )

    exit_code = await module.refresh_holdings(tmp_path / "holdings.db")

    assert exit_code == 0
    assert adapter.seen_ids == ["IUIT"]
    assert cached == [
        {
            "db_path": tmp_path / "holdings.db",
            "ticker": "QDVE",
            "source_etf_id": "IUIT",
            "issuer": "iShares",
            "holdings": [
                {"ticker": "NVDA", "isin": None, "weight": "100"},
            ],
        }
    ]


@pytest.mark.asyncio
async def test_refresh_holdings_returns_nonzero_when_all_supported_issuers_fail(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = load_refresh_module()
    monkeypatch.setattr(
        portfolio_loader,
        "load_portfolio",
        lambda: [make_position("QDVE", asset_type="etf", issuer="iShares")],
    )
    monkeypatch.setattr(lookthrough_resolver, "load_fallback_config", lambda: {})
    monkeypatch.setattr(
        lookthrough_resolver,
        "build_default_adapters",
        lambda: {"ishares": FailingAdapter()},
    )
    monkeypatch.setattr(storage_db, "cache_etf_holdings", lambda *args, **kwargs: None)

    exit_code = await module.refresh_holdings(tmp_path / "holdings.db")

    assert exit_code == 1
