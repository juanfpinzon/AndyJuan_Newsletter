"""Composite exposure resolver."""

from __future__ import annotations

from decimal import Decimal

from src.exposure.models import ExposureEntry
from src.lookthrough.models import Holding
from src.portfolio.models import Position


class ExposureComputationError(RuntimeError):
    """Raised when exposure inputs are incomplete."""


def compute_exposure(
    positions: list[Position],
    lookthrough_data: dict[str, list[Holding]],
) -> dict[str, ExposureEntry]:
    """Compute composite exposure weights on invested cost basis."""

    total_cost = sum(
        (position.shares * position.cost_basis_eur for position in positions),
        start=Decimal("0"),
    )
    exposures: dict[str, dict[str, object]] = {}

    for position in positions:
        position_cost = position.shares * position.cost_basis_eur
        position_weight = position_cost / total_cost
        if position.asset_type == "etf":
            holdings = lookthrough_data.get(position.ticker)
            if holdings is None:
                raise ExposureComputationError(
                    f"Missing look-through data for ETF {position.ticker}"
                )

            for holding in _coalesce_holdings(holdings):
                contribution = position_weight * holding.weight / Decimal("100")
                _record_path(
                    exposures,
                    entity=holding.ticker,
                    source=f"etf:{position.ticker}",
                    weight=contribution,
                )
            continue

        _record_path(
            exposures,
            entity=position.ticker,
            source="direct",
            weight=position_weight,
        )

    return {
        entity: ExposureEntry(
            entity=entity,
            composite_weight=entry["composite_weight"],
            paths=tuple(
                sorted(
                    entry["paths"],
                    key=lambda path: (-path["weight"], path["source"]),
                )
            ),
        )
        for entity, entry in sorted(
            exposures.items(),
            key=lambda item: (-item[1]["composite_weight"], item[0]),
        )
    }


def _coalesce_holdings(holdings: list[Holding]) -> list[Holding]:
    merged: dict[str, Holding] = {}
    for holding in holdings:
        existing = merged.get(holding.ticker)
        if existing is None:
            merged[holding.ticker] = holding
            continue

        merged[holding.ticker] = Holding(
            ticker=holding.ticker,
            isin=existing.isin or holding.isin,
            weight=existing.weight + holding.weight,
        )
    return list(merged.values())


def _record_path(
    exposures: dict[str, dict[str, object]],
    *,
    entity: str,
    source: str,
    weight: Decimal,
) -> None:
    current = exposures.setdefault(
        entity,
        {
            "composite_weight": Decimal("0"),
            "paths": [],
        },
    )
    current["composite_weight"] += weight
    current["paths"].append({"source": source, "weight": weight})
