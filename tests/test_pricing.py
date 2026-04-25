from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from src.pricing import PriceSnapshot, fetch_prices

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "yfinance"


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
) -> list[tuple[Any, dict[str, Any]]]:
    import src.pricing.yfinance_client as yfinance_client

    download_calls: list[tuple[Any, dict[str, Any]]] = []

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
        download_calls.append((tickers, kwargs))
        return _build_history_frame(payload)

    monkeypatch.setattr(yfinance_client.yf, "Tickers", FakeTickers)
    monkeypatch.setattr(yfinance_client.yf, "download", fake_download)
    return download_calls


def test_fetch_prices_batches_fx_once_and_converts_to_eur(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _load_fixture("mixed_batch.json")
    download_calls = _install_fake_yfinance(monkeypatch, payload)

    prices = fetch_prices(["GOOGL", "NVDA", "BNKE"])

    assert prices == {
        "GOOGL": PriceSnapshot(
            ticker="GOOGL",
            last=Decimal("100.0"),
            previous_close=Decimal("95.0"),
            currency_native="USD",
            last_eur=Decimal("80.0"),
            change_pct=Decimal("5.263157894736842105263157895"),
            fx_rate_to_eur=Decimal("1.25"),
        ),
        "NVDA": PriceSnapshot(
            ticker="NVDA",
            last=Decimal("200.0"),
            previous_close=Decimal("190.0"),
            currency_native="USD",
            last_eur=Decimal("160.0"),
            change_pct=Decimal("5.263157894736842105263157895"),
            fx_rate_to_eur=Decimal("1.25"),
        ),
        "BNKE": PriceSnapshot(
            ticker="BNKE",
            last=Decimal("50.0"),
            previous_close=Decimal("49.0"),
            currency_native="EUR",
            last_eur=Decimal("50.0"),
            change_pct=Decimal("2.040816326530612244897959184"),
            fx_rate_to_eur=Decimal("1"),
        ),
    }

    assert len(download_calls) == 1
    downloaded_tickers, download_kwargs = download_calls[0]
    assert set(downloaded_tickers.split()) == {"GOOGL", "NVDA", "BNKE", "EURUSD=X"}
    assert download_kwargs["group_by"] == "ticker"
    assert download_kwargs["progress"] is False
    assert download_kwargs["threads"] is False


def test_fetch_prices_uses_last_available_trading_day(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _load_fixture("weekend_gap.json")
    _install_fake_yfinance(monkeypatch, payload)

    prices = fetch_prices(["BNKE"])

    assert prices["BNKE"].last == Decimal("317.7174998")
    assert prices["BNKE"].previous_close == Decimal("320.4995001")
    assert prices["BNKE"].last_eur == Decimal("317.7174998")

