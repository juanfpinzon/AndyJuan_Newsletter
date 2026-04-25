"""Pure P&L calculations from positions and price snapshots."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from decimal import Decimal

from src.portfolio.models import Position
from src.pricing import PriceSnapshot

from .models import DailyDelta, PnLSnapshot, TotalPnL


def compute_pnl(
    positions: Iterable[Position],
    prices: Mapping[str, PriceSnapshot],
) -> dict[str, PnLSnapshot]:
    """Calculate per-position daily and total P&L in EUR."""

    snapshots: dict[str, PnLSnapshot] = {}
    for position in positions:
        if position.ticker not in prices:
            raise KeyError(f"Missing price for ticker: {position.ticker}")

        price = prices[position.ticker]
        cost_basis_total = position.shares * position.cost_basis_eur
        current_value = position.shares * price.last_eur
        previous_value = position.shares * price.previous_close_eur
        total_pnl = current_value - cost_basis_total
        daily_amount = current_value - previous_value
        snapshots[position.ticker] = PnLSnapshot(
            ticker=position.ticker,
            shares=position.shares,
            cost_basis_total_eur=cost_basis_total,
            current_value_eur=current_value,
            total_pnl_eur=total_pnl,
            total_pnl_pct=(
                Decimal("0")
                if cost_basis_total == 0
                else (total_pnl / cost_basis_total) * Decimal("100")
            ),
            daily_delta=DailyDelta(
                amount_eur=daily_amount,
                change_pct=(
                    Decimal("0")
                    if previous_value == 0
                    else (daily_amount / previous_value) * Decimal("100")
                ),
            ),
        )

    return snapshots


def compute_total(snapshots: Mapping[str, PnLSnapshot]) -> TotalPnL:
    """Aggregate portfolio-level P&L totals."""

    cost_basis_total = sum(
        (snapshot.cost_basis_total_eur for snapshot in snapshots.values()),
        start=Decimal("0"),
    )
    current_value_total = sum(
        (snapshot.current_value_eur for snapshot in snapshots.values()),
        start=Decimal("0"),
    )
    total_pnl = sum(
        (snapshot.total_pnl_eur for snapshot in snapshots.values()),
        start=Decimal("0"),
    )
    daily_pnl = sum(
        (snapshot.daily_delta.amount_eur for snapshot in snapshots.values()),
        start=Decimal("0"),
    )
    return TotalPnL(
        cost_basis_total_eur=cost_basis_total,
        current_value_total_eur=current_value_total,
        total_pnl_eur=total_pnl,
        total_pnl_pct=(
            Decimal("0")
            if cost_basis_total == 0
            else (total_pnl / cost_basis_total) * Decimal("100")
        ),
        daily_pnl_eur=daily_pnl,
    )
