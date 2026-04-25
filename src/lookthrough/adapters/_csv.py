"""Shared CSV parsing for issuer holdings exports."""

from __future__ import annotations

import csv
from decimal import Decimal
from io import StringIO

from src.lookthrough.models import Holding

_TICKER_FIELDS = ("ticker", "symbol")
_ISIN_FIELDS = ("isin",)
_WEIGHT_FIELDS = ("weight", "weight_pct", "weight_percent")


def parse_csv_holdings(payload: str) -> list[Holding]:
    reader = csv.DictReader(StringIO(payload))
    holdings: list[Holding] = []

    for row in reader:
        normalized = {_normalize_key(key): value for key, value in row.items() if key}
        ticker = _get_first(normalized, _TICKER_FIELDS)
        weight = _get_first(normalized, _WEIGHT_FIELDS)
        if not ticker or not weight:
            continue

        holdings.append(
            Holding(
                ticker=ticker.strip(),
                isin=_optional_text(_get_first(normalized, _ISIN_FIELDS)),
                weight=Decimal(weight.strip()),
            )
        )

    return holdings


def _normalize_key(value: str) -> str:
    return value.strip().lower().replace("%", "").replace(" ", "_")


def _get_first(values: dict[str, str | None], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = values.get(key)
        if value is not None and value.strip():
            return value
    return None


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None

    text = value.strip()
    return text or None
