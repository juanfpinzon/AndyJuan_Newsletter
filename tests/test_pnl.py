from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from src.pnl import DailyDelta, PnLSnapshot, TotalPnL, compute_pnl, compute_total
from src.portfolio.loader import load_portfolio
from src.portfolio.models import Position
from src.pricing import PriceSnapshot, fetch_prices

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "yfinance"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def _build_history_frame(payload: dict[str, Any]) -> pd.DataFrame:
    frames: dict[str, pd.DataFrame] = {}
    for symbol, rows in payload["history"].items():
        frames[symbol] = pd.DataFrame(
            {"Close": [float(row["close"]) for row in rows]},
            index=pd.to_datetime([row["date"] for row in rows]),
        )
    return pd.concat(frames, axis=1).sort_index()


def _install_fake_yfinance(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, Any],
) -> None:
    import src.pricing.yfinance_client as yfinance_client

    class FakeTicker:
        def __init__(self, currency: str) -> None:
            self.fast_info = {"currency": currency}

    class FakeTickers:
        def __init__(self, tickers: Any, session: Any = None) -> None:
            del session
            if isinstance(tickers, str):
                symbols = tickers.split()
            else:
                symbols = list(tickers)
            self.tickers = {
                symbol: FakeTicker(payload["currencies"][symbol]) for symbol in symbols
            }

    def fake_download(tickers: Any, **kwargs: Any) -> pd.DataFrame:
        del tickers, kwargs
        return _build_history_frame(payload)

    monkeypatch.setattr(yfinance_client.yf, "Tickers", FakeTickers)
    monkeypatch.setattr(yfinance_client.yf, "download", fake_download)


def test_compute_pnl_returns_position_snapshots() -> None:
    positions = [
        Position(
            ticker="BNKE",
            isin="LU1829219390",
            asset_type="etf",
            issuer="Amundi ETF",
            shares=Decimal("2"),
            cost_basis_eur=Decimal("10"),
            currency="EUR",
        )
    ]
    prices = {
        "BNKE": PriceSnapshot(
            ticker="BNKE",
            last=Decimal("12"),
            previous_close=Decimal("11"),
            currency_native="EUR",
            last_eur=Decimal("12"),
            change_pct=Decimal("9.090909090909090909090909091"),
            fx_rate_to_eur=Decimal("1"),
        )
    }

    assert compute_pnl(positions, prices) == {
        "BNKE": PnLSnapshot(
            ticker="BNKE",
            shares=Decimal("2"),
            cost_basis_total_eur=Decimal("20"),
            current_value_eur=Decimal("24"),
            total_pnl_eur=Decimal("4"),
            total_pnl_pct=Decimal("20"),
            daily_delta=DailyDelta(
                amount_eur=Decimal("2"),
                change_pct=Decimal("9.090909090909090909090909091"),
            ),
        )
    }


def test_compute_pnl_raises_when_price_is_missing() -> None:
    positions = [
        Position(
            ticker="BNKE",
            isin="LU1829219390",
            asset_type="etf",
            issuer="Amundi ETF",
            shares=Decimal("1"),
            cost_basis_eur=Decimal("10"),
            currency="EUR",
        )
    ]

    with pytest.raises(KeyError, match="BNKE"):
        compute_pnl(positions, {})


def test_compute_total_aggregates_snapshots() -> None:
    snapshots = {
        "BNKE": PnLSnapshot(
            ticker="BNKE",
            shares=Decimal("2"),
            cost_basis_total_eur=Decimal("20"),
            current_value_eur=Decimal("24"),
            total_pnl_eur=Decimal("4"),
            total_pnl_pct=Decimal("20"),
            daily_delta=DailyDelta(
                amount_eur=Decimal("2"),
                change_pct=Decimal("9.0909"),
            ),
        ),
        "QDVE": PnLSnapshot(
            ticker="QDVE",
            shares=Decimal("1"),
            cost_basis_total_eur=Decimal("50"),
            current_value_eur=Decimal("45"),
            total_pnl_eur=Decimal("-5"),
            total_pnl_pct=Decimal("-10"),
            daily_delta=DailyDelta(
                amount_eur=Decimal("-1"),
                change_pct=Decimal("-2.173913043478260869565217391"),
            ),
        ),
    }

    assert compute_total(snapshots) == TotalPnL(
        cost_basis_total_eur=Decimal("70"),
        current_value_total_eur=Decimal("69"),
        total_pnl_eur=Decimal("-1"),
        total_pnl_pct=Decimal("-1.428571428571428571428571429"),
        daily_pnl_eur=Decimal("1"),
    )


def test_portfolio_fixture_matches_seeded_screenshot_totals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _load_fixture("portfolio_snapshot.json")
    _install_fake_yfinance(monkeypatch, payload)
    positions = load_portfolio(REPOSITORY_ROOT / "config" / "portfolio.yaml")

    prices = fetch_prices([position.ticker for position in positions])
    snapshots = compute_pnl(positions, prices)
    total = compute_total(snapshots)

    assert snapshots["BNKE"].current_value_eur.quantize(Decimal("0.01")) == Decimal(
        "350.22"
    )
    assert snapshots["NVDA"].total_pnl_eur.quantize(Decimal("0.01")) == Decimal(
        "53.22"
    )
    assert snapshots["QDVE"].daily_delta.amount_eur.quantize(
        Decimal("0.01")
    ) == Decimal(
        "-4.23"
    )

    assert total.cost_basis_total_eur.quantize(Decimal("0.01")) == Decimal("2693.16")
    assert total.current_value_total_eur.quantize(Decimal("0.01")) == Decimal("2760.68")
    assert total.total_pnl_eur.quantize(Decimal("0.01")) == Decimal("67.52")
    assert total.daily_pnl_eur.quantize(Decimal("0.01")) == Decimal("0.14")
