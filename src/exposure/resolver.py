"""Composite exposure resolver."""

from __future__ import annotations

from decimal import Decimal

from src.exposure.models import ExposureEntry
from src.lookthrough.models import Holding
from src.portfolio.models import Position
from src.utils.log import get_logger


class ExposureComputationError(RuntimeError):
    """Raised when exposure inputs are incomplete."""


def compute_exposure(
    positions: list[Position],
    lookthrough_data: dict[str, list[Holding]],
) -> dict[str, ExposureEntry]:
    """Compute composite exposure weights on invested cost basis.

    Unresolvable ETFs (no look-through entry) are skipped from both the
    numerator and denominator so the remaining exposure percentages stay
    interpretable over the resolvable portfolio. A ``lookthrough_exhausted``
    warning is logged for each skipped ETF. This keeps the pipeline
    fail-soft end-to-end: a single unresolvable ETF no longer crashes the
    daily run.
    """

    skipped_etfs: list[str] = []
    for position in positions:
        if (
            position.asset_type == "etf"
            and lookthrough_data.get(position.ticker) is None
        ):
            skipped_etfs.append(position.ticker)

    resolvable_cost = sum(
        (
            position.shares * position.cost_basis_eur
            for position in positions
            if position.ticker not in skipped_etfs
        ),
        start=Decimal("0"),
    )

    exposures: dict[str, dict[str, object]] = {}

    for position in positions:
        if position.ticker in skipped_etfs:
            get_logger("exposure").warning(
                "lookthrough_exhausted",
                ticker=position.ticker,
                issuer=position.issuer,
                error=f"Missing look-through data for ETF {position.ticker}",
            )
            continue

        position_cost = position.shares * position.cost_basis_eur
        position_weight = position_cost / resolvable_cost
        if position.asset_type == "etf":
            holdings = lookthrough_data[position.ticker]

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
