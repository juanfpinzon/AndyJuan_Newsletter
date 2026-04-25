"""Load canonical portfolio data from YAML."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, cast

import yaml

from .models import AssetType, Position

DEFAULT_PORTFOLIO_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "portfolio.yaml"
)
ALLOWED_ASSET_TYPES = {"stock", "etf", "crypto"}
REQUIRED_FIELDS = (
    "ticker",
    "isin",
    "asset_type",
    "issuer",
    "shares",
    "cost_basis_eur",
    "currency",
)


class PortfolioLoadError(RuntimeError):
    """Raised when portfolio data cannot be loaded safely."""


def load_portfolio(path: str | Path | None = None) -> list[Position]:
    """Parse a portfolio YAML file into immutable Position records."""

    portfolio_path = Path(path) if path is not None else DEFAULT_PORTFOLIO_PATH
    if not portfolio_path.exists():
        raise PortfolioLoadError(f"Portfolio file does not exist: {portfolio_path}")

    raw_data = yaml.safe_load(portfolio_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw_data, dict):
        raise PortfolioLoadError(
            f"Portfolio file must contain a mapping: {portfolio_path}"
        )

    raw_positions = raw_data.get("positions")
    if not isinstance(raw_positions, list):
        raise PortfolioLoadError(
            f"Portfolio file must contain a positions list: {portfolio_path}"
        )

    positions: list[Position] = []
    for index, raw_position in enumerate(raw_positions, start=1):
        if not isinstance(raw_position, dict):
            raise PortfolioLoadError(
                f"Position #{index} must be a mapping in {portfolio_path}"
            )

        entry = cast(dict[str, Any], raw_position)
        missing = [field for field in REQUIRED_FIELDS if field not in entry]
        if missing:
            raise PortfolioLoadError(
                f"Position #{index} is missing required fields: {', '.join(missing)}"
            )

        ticker = _coerce_required_string(
            entry["ticker"],
            field_name="ticker",
            index=index,
        )
        asset_type = _coerce_asset_type(entry["asset_type"], ticker=ticker, index=index)
        currency = _coerce_required_string(
            entry["currency"], field_name="currency", index=index
        ).upper()

        positions.append(
            Position(
                ticker=ticker,
                isin=_coerce_optional_string(entry["isin"]),
                asset_type=asset_type,
                issuer=_coerce_optional_string(entry["issuer"]),
                shares=_coerce_decimal(
                    entry["shares"],
                    field_name="shares",
                    ticker=ticker,
                ),
                cost_basis_eur=_coerce_decimal(
                    entry["cost_basis_eur"],
                    field_name="cost_basis_eur",
                    ticker=ticker,
                ),
                currency=currency,
            )
        )

    return positions


def _coerce_required_string(value: Any, *, field_name: str, index: int) -> str:
    if value is None:
        raise PortfolioLoadError(
            f"Position #{index} is missing required field: {field_name}"
        )

    text = str(value).strip()
    if not text:
        raise PortfolioLoadError(f"Position #{index} has empty field: {field_name}")
    return text


def _coerce_optional_string(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    return text or None


def _coerce_asset_type(value: Any, *, ticker: str, index: int) -> AssetType:
    asset_type = _coerce_required_string(value, field_name="asset_type", index=index)
    if asset_type not in ALLOWED_ASSET_TYPES:
        raise PortfolioLoadError(
            f"Position {ticker} has unsupported asset_type: {asset_type}"
        )
    return cast(AssetType, asset_type)


def _coerce_decimal(value: Any, *, field_name: str, ticker: str) -> Decimal:
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise PortfolioLoadError(
            f"Position {ticker} has invalid {field_name}: {value!r}"
        ) from exc

    if decimal_value <= 0:
        raise PortfolioLoadError(
            f"Position {ticker} must have positive {field_name}: {value!r}"
        )
    return decimal_value
