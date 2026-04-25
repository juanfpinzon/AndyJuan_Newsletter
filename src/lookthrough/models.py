"""Look-through domain models."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Holding:
    ticker: str
    isin: str | None
    weight: Decimal


class LookthroughFailure(RuntimeError):
    """Raised when a single ETF issuer fetch fails."""

    def __init__(self, message: str, *, issuer: str, etf_id: str) -> None:
        super().__init__(message)
        self.issuer = issuer
        self.etf_id = etf_id


class LookthroughExhausted(RuntimeError):
    """Raised when neither scraper nor fallback holdings are available."""

    def __init__(self, ticker: str, issuer: str | None = None) -> None:
        detail = f"Look-through unavailable for {ticker}"
        if issuer:
            detail = f"{detail} ({issuer})"
        super().__init__(detail)
        self.ticker = ticker
        self.issuer = issuer
