"""Minimal yfinance wrapper for latest portfolio pricing."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

import pandas as pd
import yfinance as yf

HISTORY_PERIOD = "7d"
SUPPORTED_BASE_CURRENCY = "EUR"


@dataclass(frozen=True)
class PriceSnapshot:
    ticker: str
    last: Decimal
    previous_close: Decimal
    currency_native: str
    last_eur: Decimal
    change_pct: Decimal
    fx_rate_to_eur: Decimal = Decimal("1")

    @property
    def previous_close_eur(self) -> Decimal:
        return self.previous_close / self.fx_rate_to_eur


def fetch_prices(
    tickers: Iterable[str],
    base_currency: str = SUPPORTED_BASE_CURRENCY,
) -> dict[str, PriceSnapshot]:
    """Fetch the most recent close and previous close for each ticker."""

    normalized_base = base_currency.upper()
    if normalized_base != SUPPORTED_BASE_CURRENCY:
        raise ValueError(f"Unsupported base currency: {base_currency}")

    symbols = list(dict.fromkeys(_normalize_ticker(ticker) for ticker in tickers))
    if not symbols:
        return {}

    currencies = _fetch_currencies(symbols)
    fx_symbols = list(
        dict.fromkeys(
            _fx_symbol(currency, normalized_base)
            for currency in currencies.values()
            if currency != normalized_base
        )
    )
    history = yf.download(
        " ".join(symbols + fx_symbols),
        period=HISTORY_PERIOD,
        interval="1d",
        actions=False,
        auto_adjust=False,
        group_by="ticker",
        progress=False,
        threads=False,
    )

    snapshots: dict[str, PriceSnapshot] = {}
    for symbol in symbols:
        close_series = _extract_close_series(history, symbol)
        last_close, previous_close = _last_two_closes(close_series)
        currency = currencies[symbol]
        fx_rate = (
            Decimal("1")
            if currency == normalized_base
            else _last_close(
                _extract_close_series(
                    history,
                    _fx_symbol(currency, normalized_base),
                )
            )
        )
        last_eur = last_close / fx_rate
        change_pct = (
            Decimal("0")
            if previous_close == 0
            else ((last_close - previous_close) / previous_close) * Decimal("100")
        )
        snapshots[symbol] = PriceSnapshot(
            ticker=symbol,
            last=last_close,
            previous_close=previous_close,
            currency_native=currency,
            last_eur=last_eur,
            change_pct=change_pct,
            fx_rate_to_eur=fx_rate,
        )

    return snapshots


def _normalize_ticker(ticker: str) -> str:
    normalized = str(ticker).strip()
    if not normalized:
        raise ValueError("Ticker values must be non-empty")
    return normalized


def _fetch_currencies(tickers: list[str]) -> dict[str, str]:
    batch = yf.Tickers(" ".join(tickers))
    currencies: dict[str, str] = {}
    for ticker in tickers:
        ticker_obj = batch.tickers[ticker]
        fast_info = getattr(ticker_obj, "fast_info", {})
        info = getattr(ticker_obj, "info", {})
        currency = fast_info.get("currency") or info.get("currency")
        if not currency:
            raise ValueError(f"Missing currency metadata for ticker: {ticker}")
        currencies[ticker] = str(currency).upper()
    return currencies


def _fx_symbol(currency: str, base_currency: str) -> str:
    return f"{base_currency}{currency}=X"


def _extract_close_series(history: pd.DataFrame, symbol: str) -> pd.Series:
    if isinstance(history.columns, pd.MultiIndex):
        return history[symbol]["Close"].dropna()
    return history["Close"].dropna()


def _last_two_closes(series: pd.Series) -> tuple[Decimal, Decimal]:
    if series.empty:
        raise ValueError("Price history is empty")
    last_close = _to_decimal(series.iloc[-1])
    previous_value = series.iloc[-2] if len(series) > 1 else series.iloc[-1]
    previous_close = _to_decimal(previous_value)
    return last_close, previous_close


def _last_close(series: pd.Series) -> Decimal:
    if series.empty:
        raise ValueError("FX history is empty")
    return _to_decimal(series.iloc[-1])


def _to_decimal(value: object) -> Decimal:
    return Decimal(str(value))
