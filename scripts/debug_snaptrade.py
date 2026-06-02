"""Read-only SnapTrade live diagnostic.

Fetches live positions and cash balances from SnapTrade and prints a
per-position breakdown plus everything the pipeline filters out, so the live
holdings total can be reconciled against the broker / Snowball figure.

Usage:
    python scripts/debug_snaptrade.py

Requires the SNAPTRADE_* credentials in the environment / .env:
    SNAPTRADE_CLIENT_ID, SNAPTRADE_CONSUMER_KEY, SNAPTRADE_USER_ID,
    SNAPTRADE_USER_SECRET, SNAPTRADE_ACCOUNT_ID

This script only issues read-only GET calls; it sends nothing and writes
nothing. `snaptrade.enabled` does not need to be true to run it.
"""

from __future__ import annotations

import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")


def _dec(value: object, default: str = "0") -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(default)


def _eur(amount: Decimal) -> str:
    return f"{amount.quantize(Decimal('0.01')):>12}"


def run() -> int:
    from src.config import load_settings
    from src.portfolio.loader import load_portfolio
    from src.portfolio.snaptrade_client import (
        SUPPORTED_ASSET_TYPES,
        SnapTradeClient,
        SnapTradeError,
    )

    settings = load_settings()
    creds = settings.snaptrade
    missing = [
        name
        for name, value in (
            ("SNAPTRADE_CLIENT_ID", creds.client_id),
            ("SNAPTRADE_CONSUMER_KEY", creds.consumer_key),
            ("SNAPTRADE_USER_ID", creds.user_id),
            ("SNAPTRADE_USER_SECRET", creds.user_secret),
            ("SNAPTRADE_ACCOUNT_ID", creds.account_id),
        )
        if not value
    ]
    if missing:
        print("Missing SnapTrade credentials. Set these in .env:")
        for name in missing:
            print(f"  - {name}")
        return 1

    print(f"snaptrade.enabled (settings) = {creds.enabled}")
    print("Connecting to SnapTrade (read-only)...\n")

    try:
        client = SnapTradeClient(creds)
        positions = client.get_positions()
    except SnapTradeError as exc:
        print(f"SnapTrade error: {exc}")
        return 1

    raw_positions = client._last_account_positions

    # --- Mapped holdings (what the pipeline actually totals) ---
    print("MAPPED HOLDINGS (used by the pipeline):")
    header = (
        f"  {'ticker':<8}{'units':>12}{'price':>12}"
        f"{'ccy':>5}{'fx→EUR':>10}{'value EUR':>14}"
    )
    print(header)
    holdings_total_eur = Decimal("0")
    mapped_by_ticker = {p.ticker: p for p in positions}
    for payload in raw_positions:
        instrument = payload.get("instrument") or {}
        ticker = str(instrument.get("raw_symbol") or instrument.get("symbol") or "")
        if ticker not in mapped_by_ticker:
            continue
        units = _dec(payload.get("units"))
        price = _dec(payload.get("price"))
        currency = str(
            payload.get("currency") or instrument.get("currency") or "EUR"
        ).upper()
        try:
            fx = client._fx_rate_to_eur(currency)
        except SnapTradeError:
            fx = Decimal("1")
        value_eur = (units * price) / fx if fx else Decimal("0")
        holdings_total_eur += value_eur
        print(
            f"  {ticker:<8}{units:>12}{price:>12}{currency:>5}"
            f"{fx.quantize(Decimal('0.0001')):>10}{_eur(value_eur)}"
        )

    # --- Filtered-out raw positions (cash, futures/options, dust) ---
    print("\nFILTERED OUT (excluded from pipeline total):")
    filtered_total_eur = Decimal("0")
    any_filtered = False
    for payload in raw_positions:
        instrument = payload.get("instrument") or {}
        kind = str(instrument.get("kind") or "").lower()
        cash_equivalent = bool(payload.get("cash_equivalent"))
        units = _dec(payload.get("units"))
        if kind in SUPPORTED_ASSET_TYPES and not cash_equivalent and units > 0:
            continue  # this one was mapped
        any_filtered = True
        symbol = str(instrument.get("raw_symbol") or instrument.get("symbol") or "?")
        currency = str(
            payload.get("currency") or instrument.get("currency") or "EUR"
        ).upper()
        price = _dec(payload.get("price"), default="1")
        try:
            fx = client._fx_rate_to_eur(currency)
        except SnapTradeError:
            fx = Decimal("1")
        value_eur = (units * price) / fx if fx else Decimal("0")
        if cash_equivalent or kind == "cash":
            reason = "cash_equivalent"
        elif kind not in SUPPORTED_ASSET_TYPES:
            reason = f"unsupported_kind:{kind or 'unknown'}"
        else:
            reason = "zero_units"
        filtered_total_eur += value_eur
        print(f"  {symbol:<8} {reason:<24} {currency} {_eur(value_eur)}")
    if not any_filtered:
        print("  (none)")

    # --- Cash balances from the dedicated endpoint (authoritative) ---
    print("\nCASH BALANCES (get_user_account_balance):")
    cash_total_eur = Decimal("0")
    try:
        response = client._sdk.account_information.get_user_account_balance(
            user_id=creds.user_id,
            user_secret=creds.user_secret,
            account_id=creds.account_id,
        )
        body = response.body
        balances = body if isinstance(body, list) else body.get("balances", body)
        if isinstance(balances, list):
            for item in balances:
                if not isinstance(item, dict):
                    continue
                currency_field = item.get("currency")
                code = (
                    currency_field.get("code")
                    if isinstance(currency_field, dict)
                    else str(currency_field or "EUR")
                ).upper()
                cash = _dec(item.get("cash"))
                try:
                    fx = client._fx_rate_to_eur(code)
                except SnapTradeError:
                    fx = Decimal("1")
                value_eur = cash / fx if fx else Decimal("0")
                cash_total_eur += value_eur
                print(
                    f"  {code} cash {cash} → EUR {value_eur.quantize(Decimal('0.01'))}"
                )
        else:
            print(f"  (unexpected balance payload shape: {type(body).__name__})")
    except Exception as exc:  # noqa: BLE001 - diagnostic, surface any provider error
        print(f"  unavailable: {type(exc).__name__}: {exc}")

    # --- Reconciliation summary ---
    cents = Decimal("0.01")
    holdings = holdings_total_eur.quantize(cents)
    filtered = filtered_total_eur.quantize(cents)
    cash = cash_total_eur.quantize(cents)
    grand = (holdings_total_eur + max(filtered_total_eur, cash_total_eur)).quantize(
        cents
    )
    yaml_total_note = len(load_portfolio())
    print("\n" + "=" * 52)
    print(f"  mapped holdings total (pipeline) : EUR {holdings}")
    print(f"  filtered-out positions total     : EUR {filtered}")
    print(f"  cash (balance endpoint)          : EUR {cash}")
    print(f"  holdings + cash (approx broker)  : EUR {grand}")
    print(f"  (positions in config/portfolio.yaml: {yaml_total_note})")
    print("=" * 52)
    return 0


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
