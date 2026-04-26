"""Minimal yfinance wrapper for latest portfolio pricing."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
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


@dataclass(frozen=True)
class CurrencyQuoteSpec:
    currency: str
    price_divisor: Decimal = Decimal("1")


def fetch_prices(
    tickers: Iterable[str],
    base_currency: str = SUPPORTED_BASE_CURRENCY,
    *,
    market_symbols: Mapping[str, str] | None = None,
) -> dict[str, PriceSnapshot]:
    """Fetch the most recent close and previous close for each ticker."""

    normalized_base = base_currency.upper()
    if normalized_base != SUPPORTED_BASE_CURRENCY:
        raise ValueError(f"Unsupported base currency: {base_currency}")

    raw_symbols = list(dict.fromkeys(_normalize_ticker(ticker) for ticker in tickers))
    if not raw_symbols:
        return {}

    resolved_symbols = {
        symbol: _normalize_ticker(market_symbols.get(symbol, symbol))
        if market_symbols
        else symbol
        for symbol in raw_symbols
    }
    market_symbol_list = list(dict.fromkeys(resolved_symbols.values()))

    currency_specs = {
        symbol: _quote_currency_spec(raw_currency)
        for symbol, raw_currency in _fetch_currencies(market_symbol_list).items()
    }
    fx_symbols = list(
        dict.fromkeys(
            _fx_symbol(spec.currency, normalized_base)
            for spec in currency_specs.values()
            if spec.currency != normalized_base
        )
    )
    history = yf.download(
        " ".join(market_symbol_list + fx_symbols),
        period=HISTORY_PERIOD,
        interval="1d",
        actions=False,
        auto_adjust=False,
        group_by="ticker",
        progress=False,
        threads=False,
    )

    snapshots: dict[str, PriceSnapshot] = {}
    for raw_symbol in raw_symbols:
        market_symbol = resolved_symbols[raw_symbol]
        last_close, previous_close = _last_two_closes(
            _extract_close_series(history, market_symbol)
        )
        currency_spec = currency_specs[market_symbol]
        last_close = _normalize_quote_amount(last_close, currency_spec)
        previous_close = _normalize_quote_amount(previous_close, currency_spec)
        fx_rate = (
            Decimal("1")
            if currency_spec.currency == normalized_base
            else _last_close(
                _extract_close_series(
                    history,
                    _fx_symbol(currency_spec.currency, normalized_base),
                )
            )
        )
        last_eur = last_close / fx_rate
        change_pct = (
            Decimal("0")
            if previous_close == 0
            else ((last_close - previous_close) / previous_close) * Decimal("100")
        )
        snapshots[raw_symbol] = PriceSnapshot(
            ticker=raw_symbol,
            last=last_close,
            previous_close=previous_close,
            currency_native=currency_spec.currency,
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
        currencies[ticker] = str(currency).strip()
    return currencies


def _fx_symbol(currency: str, base_currency: str) -> str:
    return f"{base_currency}{currency}=X"


def _quote_currency_spec(raw_currency: str) -> CurrencyQuoteSpec:
    normalized = raw_currency.strip()
    if normalized in {"GBp", "GBX"}:
        return CurrencyQuoteSpec(currency="GBP", price_divisor=Decimal("100"))
    return CurrencyQuoteSpec(currency=normalized.upper())


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


def _normalize_quote_amount(
    amount: Decimal,
    currency_spec: CurrencyQuoteSpec,
) -> Decimal:
    return amount / currency_spec.price_divisor


def _to_decimal(value: object) -> Decimal:
    return Decimal(str(value))
