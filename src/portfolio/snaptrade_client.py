"""SnapTrade portfolio wrapper."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml

from src.config import SnapTradeSettings
from src.pnl import DailyDelta, PnLSnapshot
from src.portfolio.models import AssetType, Position
from src.pricing import PriceSnapshot, fetch_prices

DEFAULT_PORTFOLIO_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "portfolio.yaml"
)

SUPPORTED_ASSET_TYPES: dict[str, AssetType] = {
    "stock": "stock",
    "etf": "etf",
    "crypto": "crypto",
}


class SnapTradeError(RuntimeError):
    """Raised when SnapTrade data cannot be loaded safely."""


@dataclass(frozen=True)
class HistoricalPnL:
    timeframe: str
    start_date: date
    end_date: date
    start_value: Decimal
    end_value: Decimal
    pnl_amount: Decimal
    pnl_pct: Decimal
    currency: str


class SnapTradeClient:
    """Thin wrapper around the SnapTrade SDK with app-specific normalization.

    Note: This client is designed for single-run pipeline usage and is NOT
    thread-safe. Mutable instance caches (``_fx_rates_to_eur``,
    ``_last_positions``, etc.) are written without locking, so concurrent
    access from multiple threads may produce inconsistent results.
    """

    def __init__(
        self,
        settings: SnapTradeSettings,
        *,
        logger: Any | None = None,
    ) -> None:
        self._settings = settings
        self._logger = logger
        self._sdk = self._build_sdk(settings)
        self._fx_rates_to_eur: dict[str, Decimal] = {"EUR": Decimal("1")}
        self._last_account_positions: list[dict[str, Any]] = []
        self._last_mapped_account_positions: list[dict[str, Any]] = []
        self._last_positions: list[Position] = []

    def get_positions(self) -> list[Position]:
        """Return live holdings normalized into the portfolio Position model."""

        raw_positions = self._fetch_account_positions()
        fetched_at = datetime.now(UTC)
        positions: list[Position] = []
        mapped_payloads: list[dict[str, Any]] = []
        for payload in raw_positions:
            position = self._map_position(payload, fetched_at=fetched_at)
            if position is not None:
                positions.append(position)
                mapped_payloads.append(dict(payload))

        self._last_mapped_account_positions = mapped_payloads
        self._last_positions = positions
        return positions

    def get_daily_pnl(
        self,
        price_snapshots: Mapping[str, PriceSnapshot] | None = None,
    ) -> dict[str, PnLSnapshot]:
        """Return live-price P&L with local prior-close data for daily delta."""

        positions = self._last_positions or self.get_positions()
        raw_positions = (
            self._last_mapped_account_positions
            if self._last_mapped_account_positions
            else self._refresh_positions_and_payloads()
        )
        if price_snapshots is None:
            canonical_market_symbols = _load_canonical_market_symbols()
            price_snapshots = fetch_prices(
                [position.ticker for position in positions],
                base_currency="EUR",
                market_symbols={
                    position.ticker: canonical_market_symbols.get(position.ticker)
                    or position.market_symbol
                    for position in positions
                    if canonical_market_symbols.get(position.ticker)
                    or position.market_symbol
                },
            )

        snapshots: dict[str, PnLSnapshot] = {}
        for position, payload in zip(positions, raw_positions, strict=True):
            current_price_native = _to_decimal(
                payload.get("price"),
                label=f"{position.ticker} price",
            )
            fx_rate = self._fx_rate_to_eur(position.currency)
            current_value_eur = (position.shares * current_price_native) / fx_rate
            cost_basis_total_eur = position.shares * position.cost_basis_eur
            total_pnl_eur = current_value_eur - cost_basis_total_eur

            try:
                previous_close_eur = price_snapshots[position.ticker].previous_close_eur
            except KeyError as exc:
                raise KeyError(
                    "Missing prior-close snapshot for SnapTrade ticker: "
                    f"{position.ticker}"
                ) from exc

            previous_value_eur = position.shares * previous_close_eur
            daily_amount = current_value_eur - previous_value_eur
            snapshots[position.ticker] = PnLSnapshot(
                ticker=position.ticker,
                shares=position.shares,
                cost_basis_total_eur=cost_basis_total_eur,
                current_value_eur=current_value_eur,
                total_pnl_eur=total_pnl_eur,
                total_pnl_pct=_pct(total_pnl_eur, cost_basis_total_eur),
                daily_delta=DailyDelta(
                    amount_eur=daily_amount,
                    change_pct=_pct(daily_amount, previous_value_eur),
                ),
            )

        return snapshots

    def get_weekly_pnl(self) -> HistoricalPnL:
        """Return account-level weekly P&L from SnapTrade balance history."""

        return self._historical_pnl(days=7, timeframe="weekly")

    def get_monthly_pnl(self) -> HistoricalPnL:
        """Return account-level monthly P&L from SnapTrade balance history."""

        return self._historical_pnl(days=30, timeframe="monthly")

    def _historical_pnl(self, *, days: int, timeframe: str) -> HistoricalPnL:
        response = self._sdk.account_information.get_account_balance_history(
            user_id=self._settings.user_id,
            user_secret=self._settings.user_secret,
            account_id=self._settings.account_id,
        )
        body = _require_mapping(response.body, label="account balance history")
        raw_history = body.get("history")
        if not isinstance(raw_history, list) or not raw_history:
            raise SnapTradeError("SnapTrade balance history did not return usable data")

        history = sorted(
            (
                (
                    _to_date(item.get("date"), label="history date"),
                    _to_decimal(item.get("total_value"), label="history total_value"),
                )
                for item in raw_history
                if isinstance(item, dict)
            ),
            key=lambda item: item[0],
        )
        if not history:
            raise SnapTradeError("SnapTrade balance history was empty")

        end_date, end_value = history[-1]
        target_date = end_date - timedelta(days=days)
        start_date, start_value = history[0]
        for point_date, point_value in history:
            if point_date <= target_date:
                start_date, start_value = point_date, point_value

        pnl_amount = end_value - start_value
        return HistoricalPnL(
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            start_value=start_value,
            end_value=end_value,
            pnl_amount=pnl_amount,
            pnl_pct=_pct(pnl_amount, start_value),
            currency=str(body.get("currency") or "EUR"),
        )

    def _fetch_account_positions(self) -> list[dict[str, Any]]:
        response = self._sdk.account_information.get_all_account_positions(
            user_id=self._settings.user_id,
            user_secret=self._settings.user_secret,
            account_id=self._settings.account_id,
        )
        body = _require_mapping(response.body, label="account positions")
        results = body.get("results")
        if not isinstance(results, list):
            raise SnapTradeError("SnapTrade account positions response was malformed")

        normalized = [item for item in results if isinstance(item, dict)]
        self._last_account_positions = normalized
        return normalized

    def _refresh_positions_and_payloads(self) -> list[dict[str, Any]]:
        self.get_positions()
        return self._last_mapped_account_positions

    def _map_position(
        self,
        payload: Mapping[str, Any],
        *,
        fetched_at: datetime,
    ) -> Position | None:
        instrument = _require_mapping(payload.get("instrument"), label="instrument")
        kind = str(instrument.get("kind") or "").lower()
        if kind not in SUPPORTED_ASSET_TYPES:
            return None
        if bool(payload.get("cash_equivalent")):
            return None

        ticker = _non_empty_string(
            instrument.get("raw_symbol") or instrument.get("symbol"),
            label="instrument symbol",
        )
        units = _to_decimal(payload.get("units"), label=f"{ticker} units")
        if units <= 0:
            return None

        native_cost_basis = _to_decimal(
            payload.get("cost_basis"),
            label=f"{ticker} cost_basis",
        )
        currency = _non_empty_string(
            payload.get("currency") or instrument.get("currency") or "EUR",
            label=f"{ticker} currency",
        ).upper()
        fx_rate = self._fx_rate_to_eur(currency)
        cost_basis_eur = native_cost_basis / fx_rate
        market_symbol = _optional_string(instrument.get("symbol"))
        description = _optional_string(instrument.get("description"))
        if market_symbol == ticker:
            market_symbol = None

        return Position(
            ticker=ticker,
            isin=None,
            asset_type=SUPPORTED_ASSET_TYPES[kind],
            issuer=description,
            shares=units,
            cost_basis_eur=cost_basis_eur,
            currency=currency,
            market_symbol=market_symbol,
            source="snaptrade",
            last_updated=fetched_at,
        )

    def _fx_rate_to_eur(self, currency: str) -> Decimal:
        normalized = currency.upper()
        if normalized in self._fx_rates_to_eur:
            return self._fx_rates_to_eur[normalized]

        response = self._sdk.reference_data.get_currency_exchange_rate_pair(
            currency_pair=f"EUR-{normalized}"
        )
        body = _require_mapping(response.body, label="currency exchange rate")
        rate = _to_decimal(
            body.get("exchange_rate"),
            label=f"EUR-{normalized} exchange_rate",
        )
        self._fx_rates_to_eur[normalized] = rate
        return rate

    @staticmethod
    def _build_sdk(settings: SnapTradeSettings) -> Any:
        _require_setting(settings.client_id, name="snaptrade.client_id")
        _require_setting(settings.consumer_key, name="snaptrade.consumer_key")
        _require_setting(settings.user_id, name="snaptrade.user_id")
        _require_setting(settings.user_secret, name="snaptrade.user_secret")
        _require_setting(settings.account_id, name="snaptrade.account_id")

        try:
            from snaptrade_client import SnapTrade
        except ImportError as exc:  # pragma: no cover
            raise SnapTradeError(
                "snaptrade-python-sdk is not installed; add project dependencies first"
            ) from exc

        return SnapTrade(
            client_id=settings.client_id,
            consumer_key=settings.consumer_key,
        )


def _require_setting(value: str | None, *, name: str) -> None:
    if value is None or not str(value).strip():
        raise SnapTradeError(f"Missing required SnapTrade setting: {name}")


def _require_mapping(value: object, *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SnapTradeError(f"SnapTrade {label} response was malformed")
    return dict(value)


def _non_empty_string(value: object, *, label: str) -> str:
    text = _optional_string(value)
    if text is None:
        raise SnapTradeError(f"Missing required SnapTrade field: {label}")
    return text


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_decimal(value: object, *, label: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise SnapTradeError(
            f"Invalid SnapTrade decimal for {label}: {value!r}"
        ) from exc


def _to_date(value: object, *, label: str) -> date:
    if value is None:
        raise SnapTradeError(f"Missing required SnapTrade field: {label}")
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise SnapTradeError(f"Invalid SnapTrade date for {label}: {value!r}") from exc


def _load_canonical_market_symbols(path: Path | None = None) -> dict[str, str]:
    # Intentionally hardcodes the canonical portfolio.yaml path for market
    # symbol resolution rather than accepting a dynamic config path. This is
    # a deliberate simplification for the current single-pipeline architecture.
    portfolio_path = path or DEFAULT_PORTFOLIO_PATH
    try:
        raw_data = yaml.safe_load(portfolio_path.read_text(encoding="utf-8")) or {}
    except OSError:
        return {}
    if not isinstance(raw_data, dict):
        return {}

    raw_positions = raw_data.get("positions")
    if not isinstance(raw_positions, list):
        return {}

    market_symbols: dict[str, str] = {}
    for raw_position in raw_positions:
        if not isinstance(raw_position, dict):
            continue
        ticker = _optional_string(raw_position.get("ticker"))
        market_symbol = _optional_string(raw_position.get("market_symbol"))
        if ticker and market_symbol:
            market_symbols[ticker] = market_symbol
    return market_symbols


def _pct(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator == 0:
        return Decimal("0")
    return (numerator / denominator) * Decimal("100")
