"""Merge a Snowball holdings export into config/portfolio.yaml."""

import argparse
import csv
import difflib
import sys
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml

DEFAULT_PORTFOLIO_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "portfolio.yaml"
)
HOLDINGS_COLUMNS = ("Ticker", "Shares", "Average cost", "Currency")
TRANSACTION_COLUMNS = ("Event", "Date", "Symbol", "Price", "Quantity", "Currency")
FX_MATCH_WINDOW = timedelta(seconds=1)


class SnowballSchemaError(RuntimeError):
    """Raised when the Snowball CSV schema does not match expectations."""


class SnowballImportError(RuntimeError):
    """Raised when a Snowball import cannot be applied safely."""


@dataclass(frozen=True)
class _TransactionRow:
    event: str
    occurred_at: datetime
    symbol: str
    price: Decimal
    quantity: Decimal
    currency: str
    note: str
    row_number: int


@dataclass
class _CashConversion:
    occurred_at: datetime
    symbol: str
    converted_amount: Decimal
    eur_amount: Decimal
    row_number: int
    used: bool = False


def main(argv: list[str] | None = None) -> int:
    """Run the Snowball importer CLI."""

    parser = argparse.ArgumentParser(
        description="Merge a Snowball CSV export into config/portfolio.yaml."
    )
    parser.add_argument("csv_path", type=Path, help="Path to the Snowball CSV export.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the diff without writing config/portfolio.yaml.",
    )
    args = parser.parse_args(argv)

    try:
        diff_text, warnings = import_snowball(args.csv_path, dry_run=args.dry_run)
    except (SnowballSchemaError, SnowballImportError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    for warning in warnings:
        print(warning, file=sys.stderr)

    print(diff_text or "No changes.", end="")

    return 0


def import_snowball(
    csv_path: str | Path,
    *,
    dry_run: bool,
    portfolio_path: str | Path | None = None,
) -> tuple[str, list[str]]:
    """Merge a Snowball export into the default portfolio path."""

    resolved_portfolio_path = Path(portfolio_path or DEFAULT_PORTFOLIO_PATH)
    if not resolved_portfolio_path.exists():
        raise SnowballImportError(
            f"Portfolio file does not exist: {resolved_portfolio_path}"
        )

    portfolio_data = _load_portfolio_mapping(resolved_portfolio_path)
    original_data = deepcopy(portfolio_data)
    snowball_rows, export_kind = _load_snowball_export(csv_path)
    warnings = _merge_portfolio_positions(
        portfolio_data,
        snowball_rows,
        update_cost_basis=export_kind == "holdings",
        enforce_currency=export_kind == "holdings",
    )

    original_text = resolved_portfolio_path.read_text(encoding="utf-8")
    if portfolio_data == original_data:
        return "", warnings

    updated_text = yaml.safe_dump(
        portfolio_data,
        sort_keys=False,
        allow_unicode=True,
    )
    diff_text = _build_diff(original_text, updated_text, resolved_portfolio_path)

    if not dry_run and updated_text != original_text:
        resolved_portfolio_path.write_text(updated_text, encoding="utf-8")

    return diff_text, warnings


def load_snowball_rows(path: str | Path) -> dict[str, dict[str, str]]:
    """Load Snowball rows keyed by ticker."""

    rows, _ = _load_snowball_export(path)
    return rows


def _load_snowball_export(
    path: str | Path,
) -> tuple[dict[str, dict[str, str]], str]:
    """Load either a holdings snapshot or a transactional Snowball export."""

    csv_path = Path(path)
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        header_names = set(fieldnames)
        if all(column in header_names for column in TRANSACTION_COLUMNS):
            return _load_transaction_rows(reader), "transactions"

        if header_names.intersection(HOLDINGS_COLUMNS):
            _validate_columns(fieldnames, HOLDINGS_COLUMNS)
            return _load_holdings_rows(reader), "holdings"

        if header_names.intersection(TRANSACTION_COLUMNS):
            _validate_columns(fieldnames, TRANSACTION_COLUMNS)
            return _load_transaction_rows(reader), "transactions"

    raise SnowballSchemaError(
        "Unsupported Snowball schema. Expected holdings columns "
        f"{', '.join(HOLDINGS_COLUMNS)} or transaction columns "
        f"{', '.join(TRANSACTION_COLUMNS)}."
    )


def _validate_columns(fieldnames: list[str], required: tuple[str, ...]) -> None:
    missing = [column for column in required if column not in fieldnames]
    if missing:
        raise SnowballSchemaError(
            "Missing required Snowball columns: " + ", ".join(missing)
        )


def _load_holdings_rows(reader: csv.DictReader) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    for row_number, row in enumerate(reader, start=2):
        ticker = _normalize_string(
            row.get("Ticker"),
            field="Ticker",
            row_number=row_number,
        )
        shares = _normalize_positive_decimal(
            row.get("Shares"),
            field="Shares",
            ticker=ticker,
            places=4,
        )
        average_cost = _normalize_positive_decimal(
            row.get("Average cost"),
            field="Average cost",
            ticker=ticker,
            places=6,
        )
        currency = _normalize_string(
            row.get("Currency"),
            field="Currency",
            row_number=row_number,
        )
        rows[ticker] = {
            "shares": shares,
            "cost_basis_eur": average_cost,
            "currency": currency,
        }

    return rows


def _load_transaction_rows(reader: csv.DictReader) -> dict[str, dict[str, str]]:
    holdings: dict[str, dict[str, Decimal | str]] = {}
    cash_conversions: list[_CashConversion] = []
    transactions: list[_TransactionRow] = []

    for row_number, row in enumerate(reader, start=2):
        event = _normalize_string(
            row.get("Event"),
            field="Event",
            row_number=row_number,
        )
        occurred_at = _parse_datetime(row.get("Date"), row_number=row_number)
        symbol = _normalize_string(
            row.get("Symbol"),
            field="Symbol",
            row_number=row_number,
        )
        price = _parse_decimal(
            row.get("Price"),
            field="Price",
            row_context=f"Snowball row {row_number}",
        )
        quantity = _parse_decimal(
            row.get("Quantity"),
            field="Quantity",
            row_context=f"Snowball row {row_number}",
        )
        currency = _normalize_string(
            row.get("Currency"),
            field="Currency",
            row_number=row_number,
        )
        note = (row.get("Note") or "").strip()

        if event == "CASH_CONVERT":
            cash_conversions.append(
                _CashConversion(
                    occurred_at=occurred_at,
                    symbol=symbol,
                    converted_amount=quantity,
                    eur_amount=price,
                    row_number=row_number,
                )
            )
            continue

        if event not in {"BUY", "SELL"}:
            continue

        transactions.append(
            _TransactionRow(
                event=event,
                occurred_at=occurred_at,
                symbol=symbol,
                price=price,
                quantity=quantity,
                currency=currency,
                note=note,
                row_number=row_number,
            )
        )

    for transaction in transactions:
        signed_quantity = _signed_quantity(transaction)
        if transaction.symbol in {"EUR", "USD"}:
            continue

        entry = holdings.setdefault(
            transaction.symbol,
            {
                "shares": Decimal("0"),
                "acquired_shares": Decimal("0"),
                "eur_cost": Decimal("0"),
                "currency": transaction.currency,
            },
        )

        entry_currency = str(entry["currency"])
        if entry_currency != transaction.currency:
            raise SnowballSchemaError(
                f"Snowball transactions for {transaction.symbol} use multiple "
                f"currencies: {entry_currency}, {transaction.currency}"
            )

        entry["shares"] = Decimal(entry["shares"]) + signed_quantity

        if signed_quantity <= 0 or _is_balance_adjustment(transaction):
            continue

        eur_cost = _resolve_eur_cost(transaction, cash_conversions)
        entry["acquired_shares"] = Decimal(entry["acquired_shares"]) + signed_quantity
        entry["eur_cost"] = Decimal(entry["eur_cost"]) + eur_cost

    rows: dict[str, dict[str, str]] = {}
    for ticker, entry in holdings.items():
        shares = Decimal(entry["shares"])
        if shares <= 0:
            continue

        acquired_shares = Decimal(entry["acquired_shares"])
        eur_cost = Decimal(entry["eur_cost"])
        if acquired_shares <= 0 or eur_cost <= 0:
            raise SnowballSchemaError(
                f"Unable to derive EUR cost basis for {ticker} from Snowball "
                "transactions."
            )

        rows[ticker] = {
            "shares": _format_decimal(shares, places=4),
            "cost_basis_eur": _format_decimal(eur_cost / acquired_shares, places=6),
            "currency": str(entry["currency"]),
        }

    return rows


def _load_portfolio_mapping(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise SnowballImportError(f"Portfolio file must contain a mapping: {path}")

    positions = data.get("positions")
    if not isinstance(positions, list):
        raise SnowballImportError(
            f"Portfolio file must contain a positions list: {path}"
        )

    return data


def _merge_portfolio_positions(
    portfolio_data: dict[str, Any],
    snowball_rows: dict[str, dict[str, str]],
    *,
    update_cost_basis: bool,
    enforce_currency: bool,
) -> list[str]:
    positions = portfolio_data["positions"]
    assert isinstance(positions, list)

    existing_entries: dict[str, dict[str, Any]] = {}
    existing_tickers: list[str] = []
    for raw_entry in positions:
        if not isinstance(raw_entry, dict):
            raise SnowballImportError("Portfolio positions must all be mappings.")

        entry = raw_entry
        ticker = str(entry.get("ticker", "")).strip().upper()
        if not ticker:
            raise SnowballImportError(
                "Portfolio positions must include non-empty tickers."
            )

        existing_entries[ticker] = entry
        existing_tickers.append(ticker)

    warnings: list[str] = []
    for ticker in existing_tickers:
        if ticker not in snowball_rows:
            warnings.append(f"missing from Snowball export: {ticker}")
            continue

        entry = existing_entries[ticker]
        row = snowball_rows[ticker]
        existing_currency = str(entry.get("currency", "")).strip().upper()
        if enforce_currency and existing_currency != row["currency"]:
            raise SnowballImportError(
                f"currency mismatch for {ticker}: portfolio has {existing_currency}, "
                f"CSV has {row['currency']}"
            )

        entry["shares"] = row["shares"]
        if update_cost_basis:
            entry["cost_basis_eur"] = row["cost_basis_eur"]

    for ticker, row in snowball_rows.items():
        if ticker in existing_entries:
            continue

        warnings.append(f"new ticker scaffolded: {ticker}")
        positions.append(
            {
                "ticker": ticker,
                "isin": None,
                "asset_type": "stock",
                "issuer": None,
                "shares": row["shares"],
                "cost_basis_eur": row["cost_basis_eur"],
                "currency": row["currency"],
            }
        )

    return warnings


def _build_diff(original_text: str, updated_text: str, portfolio_path: Path) -> str:
    return "".join(
        difflib.unified_diff(
            original_text.splitlines(keepends=True),
            updated_text.splitlines(keepends=True),
            fromfile=str(portfolio_path),
            tofile=str(portfolio_path),
        )
    )


def _normalize_string(value: str | None, *, field: str, row_number: int) -> str:
    text = (value or "").strip()
    if not text:
        raise SnowballSchemaError(
            f"Snowball row {row_number} is missing required field: {field}"
        )
    return text.upper()


def _normalize_positive_decimal(
    value: str | None, *, field: str, ticker: str, places: int
) -> str:
    decimal_value = _parse_decimal(
        value,
        field=field,
        row_context=f"Snowball row for {ticker}",
    )

    if decimal_value <= 0:
        raise SnowballSchemaError(
            f"Snowball row for {ticker} must have positive {field}: {value!r}"
        )

    return _format_decimal(decimal_value, places=places)


def _parse_decimal(value: str | None, *, field: str, row_context: str) -> Decimal:
    raw_text = (value or "").strip()
    if not raw_text:
        raise SnowballSchemaError(f"{row_context} is missing required field: {field}")

    try:
        return Decimal(raw_text)
    except (InvalidOperation, ValueError) as exc:
        raise SnowballSchemaError(
            f"{row_context} has invalid {field}: {value!r}"
        ) from exc


def _parse_datetime(value: str | None, *, row_number: int) -> datetime:
    raw_text = (value or "").strip()
    if not raw_text:
        raise SnowballSchemaError(
            f"Snowball row {row_number} is missing required field: Date"
        )

    try:
        return datetime.fromisoformat(raw_text)
    except ValueError as exc:
        raise SnowballSchemaError(
            f"Snowball row {row_number} has invalid Date: {value!r}"
        ) from exc


def _signed_quantity(transaction: _TransactionRow) -> Decimal:
    if transaction.event == "SELL" and transaction.quantity > 0:
        return -transaction.quantity

    return transaction.quantity


def _is_balance_adjustment(transaction: _TransactionRow) -> bool:
    return transaction.note.startswith(
        "Automatically generated transaction to adjust balance"
    )


def _resolve_eur_cost(
    transaction: _TransactionRow,
    cash_conversions: list[_CashConversion],
) -> Decimal:
    if transaction.currency == "EUR":
        return transaction.price * _signed_quantity(transaction)

    target_amount = abs(transaction.price * _signed_quantity(transaction))
    matching_conversion = _match_cash_conversion(
        occurred_at=transaction.occurred_at,
        source_currency=transaction.currency,
        target_amount=target_amount,
        cash_conversions=cash_conversions,
    )
    if matching_conversion is None:
        raise SnowballSchemaError(
            f"Unable to match FX conversion for {transaction.symbol} on row "
            f"{transaction.row_number}"
        )

    matching_conversion.used = True
    return matching_conversion.eur_amount


def _match_cash_conversion(
    *,
    occurred_at: datetime,
    source_currency: str,
    target_amount: Decimal,
    cash_conversions: list[_CashConversion],
) -> _CashConversion | None:
    candidates = [
        conversion
        for conversion in cash_conversions
        if not conversion.used
        and conversion.symbol == source_currency
        and abs(conversion.occurred_at - occurred_at) <= FX_MATCH_WINDOW
    ]
    if not candidates:
        return None

    return min(
        candidates,
        key=lambda conversion: (
            abs(conversion.converted_amount - target_amount),
            abs(conversion.occurred_at - occurred_at),
            conversion.row_number,
        ),
    )


def _format_decimal(value: Decimal, *, places: int) -> str:
    quantizer = Decimal("1." + ("0" * places))
    return str(value.quantize(quantizer))


if __name__ == "__main__":
    raise SystemExit(main())
