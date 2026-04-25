"""P&L value objects."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class DailyDelta:
    amount_eur: Decimal
    change_pct: Decimal


@dataclass(frozen=True)
class PnLSnapshot:
    ticker: str
    shares: Decimal
    cost_basis_total_eur: Decimal
    current_value_eur: Decimal
    total_pnl_eur: Decimal
    total_pnl_pct: Decimal
    daily_delta: DailyDelta


@dataclass(frozen=True)
class TotalPnL:
    cost_basis_total_eur: Decimal
    current_value_total_eur: Decimal
    total_pnl_eur: Decimal
    total_pnl_pct: Decimal
    daily_pnl_eur: Decimal
