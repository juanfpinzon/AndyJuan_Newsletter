"""Load canonical portfolio data from YAML."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, cast

import yaml

from src.config import Settings
from src.lookthrough.issuers import normalize_issuer
from src.storage.db import cache_position_snapshot, load_latest_position_snapshot
from src.utils.log import get_logger

from .models import AssetType, Position
from .snaptrade_client import SnapTradeClient

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


@dataclass(frozen=True)
class PortfolioSnapshotBundle:
    positions: list[Position]
    snaptrade_client: SnapTradeClient | None = None


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
                market_symbol=_coerce_optional_string(entry.get("market_symbol")),
            )
        )

    return positions


def load_portfolio_snapshot(
    *,
    settings: Settings,
    db_path: str | Path,
    path: str | Path | None = None,
) -> list[Position]:
    """Load the canonical portfolio with live-source overlay and safe fallback."""

    return load_portfolio_snapshot_bundle(
        settings=settings,
        db_path=db_path,
        path=path,
    ).positions


def load_portfolio_snapshot_bundle(
    *,
    settings: Settings,
    db_path: str | Path,
    path: str | Path | None = None,
) -> PortfolioSnapshotBundle:
    """Load positions plus the live SnapTrade client when the fetch succeeded."""

    yaml_positions = load_portfolio(path)
    if not settings.snaptrade.enabled:
        return PortfolioSnapshotBundle(positions=yaml_positions)

    logger = get_logger("portfolio.loader")
    try:
        snaptrade_client = SnapTradeClient(
            settings.snaptrade,
            logger=logger,
        )
        live_positions = snaptrade_client.get_positions()
    except Exception as exc:  # noqa: BLE001 - live data must never kill the run
        # SnapTradeClient wraps every SDK entry point so failures arrive as
        # SnapTradeError, but this is the exact catch that let the 2026-07-22
        # outage through for five weeks. Catching broadly here makes the
        # documented "falls back to portfolio.yaml" promise unconditional.
        cached_positions = load_latest_position_snapshot(db_path, source="snaptrade")
        logger.warning(
            "snaptrade_fallback_used",
            reason=str(exc),
            error_type=type(exc).__name__,
            fallback_source="position_cache" if cached_positions else "yaml",
        )
        return PortfolioSnapshotBundle(
            positions=merge_positions(
                yaml_positions,
                cached_positions,
                logger=logger,
            )
        )

    cache_position_snapshot(db_path, source="snaptrade", positions=live_positions)
    return PortfolioSnapshotBundle(
        positions=merge_positions(
            yaml_positions,
            live_positions,
            logger=logger,
            include_missing_canonical=False,
        ),
        snaptrade_client=snaptrade_client,
    )


def merge_positions(
    canonical_positions: list[Position],
    live_positions: list[Position],
    *,
    logger: Any | None = None,
    include_missing_canonical: bool = True,
) -> list[Position]:
    """Overlay live numeric data onto canonical YAML-enriched positions.

    When ``include_missing_canonical=False`` (the default on the live SnapTrade
    success path), any position that exists only in the YAML file and is not
    reported by IBKR/SnapTrade is intentionally dropped from the output. This
    means operators should be aware that holdings absent from the live broker
    feed will not appear in the pipeline result — by design, the live snapshot
    is treated as the authoritative source for current holdings.
    """

    canonical_by_ticker = {
        position.ticker: position for position in canonical_positions
    }
    merged: list[Position] = []
    seen_tickers: set[str] = set()

    for live_position in live_positions:
        canonical_position = canonical_by_ticker.get(live_position.ticker)
        if canonical_position is None:
            if (
                live_position.asset_type == "etf"
                and normalize_issuer(live_position.issuer) is None
            ):
                if logger is not None:
                    logger.warning(
                        "snaptrade_etf_skipped",
                        ticker=live_position.ticker,
                        reason="missing_canonical_metadata",
                    )
                continue
            merged.append(live_position)
            seen_tickers.add(live_position.ticker)
            continue

        merged.append(
            Position(
                ticker=canonical_position.ticker,
                isin=canonical_position.isin,
                asset_type=canonical_position.asset_type,
                issuer=canonical_position.issuer,
                shares=live_position.shares,
                cost_basis_eur=live_position.cost_basis_eur,
                currency=live_position.currency,
                market_symbol=(
                    canonical_position.market_symbol or live_position.market_symbol
                ),
                source=live_position.source,
                last_updated=live_position.last_updated,
            )
        )
        seen_tickers.add(live_position.ticker)

    if include_missing_canonical:
        for canonical_position in canonical_positions:
            if canonical_position.ticker not in seen_tickers:
                merged.append(canonical_position)

    merged.sort(key=lambda position: position.ticker)
    return merged


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
