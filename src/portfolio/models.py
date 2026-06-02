"""Portfolio domain models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

AssetType = Literal["stock", "etf", "crypto"]
PositionSource = Literal["snaptrade", "binance", "yaml"]


@dataclass(frozen=True)
class Position:
    ticker: str
    isin: str | None
    asset_type: AssetType
    issuer: str | None
    shares: Decimal
    cost_basis_eur: Decimal
    currency: str
    market_symbol: str | None = None
    source: PositionSource = "yaml"
    last_updated: datetime | None = None
