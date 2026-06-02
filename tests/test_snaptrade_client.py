from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

import src.portfolio.snaptrade_client as snaptrade_client
from src.config import SnapTradeSettings
from src.portfolio.models import Position
from src.portfolio.snaptrade_client import HistoricalPnL, SnapTradeClient
from src.pricing import PriceSnapshot

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "snaptrade"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


class _Response:
    def __init__(self, body: object) -> None:
        self.body = body


class _FakeAccountInformation:
    def __init__(self, *, positions: dict, history: dict) -> None:
        self._positions = positions
        self._history = history

    def get_all_account_positions(self, **kwargs) -> _Response:
        del kwargs
        return _Response(self._positions)

    def get_account_balance_history(self, **kwargs) -> _Response:
        del kwargs
        return _Response(self._history)


class _FakeReferenceData:
    def __init__(self, fx_rates: dict[str, Decimal]) -> None:
        self._fx_rates = fx_rates
        self.requested_pairs: list[str] = []

    def get_currency_exchange_rate_pair(self, *, currency_pair: str) -> _Response:
        self.requested_pairs.append(currency_pair)
        return _Response({"exchange_rate": str(self._fx_rates[currency_pair])})


class _FakeSdk:
    def __init__(
        self,
        *,
        positions: dict,
        history: dict,
        fx_rates: dict[str, Decimal],
    ) -> None:
        self.account_information = _FakeAccountInformation(
            positions=positions,
            history=history,
        )
        self.reference_data = _FakeReferenceData(fx_rates)


def _build_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    positions: dict | None = None,
    history: dict | None = None,
    fx_rates: dict[str, Decimal] | None = None,
) -> SnapTradeClient:
    fake_sdk = _FakeSdk(
        positions=positions or _load_fixture("account_positions.json"),
        history=history or _load_fixture("balance_history.json"),
        fx_rates=fx_rates or {"EUR-USD": Decimal("1.25")},
    )
    monkeypatch.setattr(
        SnapTradeClient,
        "_build_sdk",
        staticmethod(lambda settings: fake_sdk),
    )
    return SnapTradeClient(
        SnapTradeSettings(
            enabled=True,
            client_id="client",
            consumer_key="consumer",
            user_id="user",
            user_secret="secret",
            account_id="account",
        )
    )


def test_get_positions_maps_supported_snaptrade_positions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _build_client(monkeypatch)

    positions = client.get_positions()

    assert positions == [
        Position(
            ticker="NVDA",
            isin=None,
            asset_type="stock",
            issuer="NVIDIA Corporation",
            shares=Decimal("2.5"),
            cost_basis_eur=Decimal("96"),
            currency="USD",
            source="snaptrade",
            last_updated=positions[0].last_updated,
        ),
        Position(
            ticker="QDVE",
            isin=None,
            asset_type="etf",
            issuer="iShares S&P 500 Information Technology Sector UCITS ETF",
            shares=Decimal("1.25"),
            cost_basis_eur=Decimal("28"),
            currency="EUR",
            source="snaptrade",
            last_updated=positions[1].last_updated,
        ),
        Position(
            ticker="BTC",
            isin=None,
            asset_type="crypto",
            issuer="Bitcoin",
            shares=Decimal("0.1"),
            cost_basis_eur=Decimal("40000"),
            currency="USD",
            source="snaptrade",
            last_updated=positions[2].last_updated,
        ),
    ]

    assert all(position.last_updated is not None for position in positions)
    assert client._sdk.reference_data.requested_pairs == ["EUR-USD"]


def test_get_daily_pnl_uses_snaptrade_current_prices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _build_client(monkeypatch)
    client.get_positions()

    snapshots = client.get_daily_pnl(
        price_snapshots={
            "NVDA": PriceSnapshot(
                ticker="NVDA",
                last=Decimal("120"),
                previous_close=Decimal("120"),
                currency_native="USD",
                last_eur=Decimal("96"),
                change_pct=Decimal("0"),
                fx_rate_to_eur=Decimal("1.25"),
            ),
            "QDVE": PriceSnapshot(
                ticker="QDVE",
                last=Decimal("39"),
                previous_close=Decimal("39"),
                currency_native="EUR",
                last_eur=Decimal("39"),
                change_pct=Decimal("0"),
                fx_rate_to_eur=Decimal("1"),
            ),
            "BTC": PriceSnapshot(
                ticker="BTC",
                last=Decimal("58000"),
                previous_close=Decimal("58000"),
                currency_native="USD",
                last_eur=Decimal("46400"),
                change_pct=Decimal("0"),
                fx_rate_to_eur=Decimal("1.25"),
            ),
        }
    )

    assert snapshots["NVDA"].current_value_eur == Decimal("250")
    assert snapshots["NVDA"].total_pnl_eur == Decimal("10")
    assert snapshots["NVDA"].daily_delta.amount_eur == Decimal("10")
    assert snapshots["QDVE"].current_value_eur == Decimal("50")
    assert snapshots["BTC"].total_pnl_eur == Decimal("800")


def test_get_daily_pnl_uses_canonical_market_symbol_overrides(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    portfolio_path = tmp_path / "portfolio.yaml"
    portfolio_path.write_text(
        "\n".join(
            [
                "positions:",
                "  - ticker: QDVE",
                "    market_symbol: IITU.L",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(snaptrade_client, "DEFAULT_PORTFOLIO_PATH", portfolio_path)

    captured_market_symbols: dict[str, str] = {}

    def fake_fetch_prices(
        tickers,
        base_currency: str = "EUR",
        *,
        market_symbols=None,
    ):
        del tickers, base_currency
        captured_market_symbols.update(market_symbols or {})
        return {
            "NVDA": PriceSnapshot(
                ticker="NVDA",
                last=Decimal("120"),
                previous_close=Decimal("120"),
                currency_native="USD",
                last_eur=Decimal("96"),
                change_pct=Decimal("0"),
                fx_rate_to_eur=Decimal("1.25"),
            ),
            "QDVE": PriceSnapshot(
                ticker="QDVE",
                last=Decimal("39"),
                previous_close=Decimal("39"),
                currency_native="EUR",
                last_eur=Decimal("39"),
                change_pct=Decimal("0"),
                fx_rate_to_eur=Decimal("1"),
            ),
            "BTC": PriceSnapshot(
                ticker="BTC",
                last=Decimal("58000"),
                previous_close=Decimal("58000"),
                currency_native="USD",
                last_eur=Decimal("46400"),
                change_pct=Decimal("0"),
                fx_rate_to_eur=Decimal("1.25"),
            ),
        }

    monkeypatch.setattr(snaptrade_client, "fetch_prices", fake_fetch_prices)
    client = _build_client(monkeypatch)

    client.get_daily_pnl()

    assert captured_market_symbols == {"QDVE": "IITU.L"}


def test_get_weekly_and_monthly_pnl_use_balance_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _build_client(monkeypatch)

    weekly = client.get_weekly_pnl()
    monthly = client.get_monthly_pnl()

    assert weekly == HistoricalPnL(
        timeframe="weekly",
        start_date=weekly.start_date,
        end_date=weekly.end_date,
        start_value=Decimal("11000.00"),
        end_value=Decimal("11500.00"),
        pnl_amount=Decimal("500.00"),
        pnl_pct=Decimal("4.545454545454545454545454545"),
        currency="USD",
    )
    assert monthly == HistoricalPnL(
        timeframe="monthly",
        start_date=monthly.start_date,
        end_date=monthly.end_date,
        start_value=Decimal("10000.00"),
        end_value=Decimal("11500.00"),
        pnl_amount=Decimal("1500.00"),
        pnl_pct=Decimal("15.00"),
        currency="USD",
    )
