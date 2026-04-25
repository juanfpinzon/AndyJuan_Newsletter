"""Resolve ETF look-through with issuer adapters and YAML fallbacks."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from src.lookthrough.adapters import (
    BaseAdapter,
    GlobalxAdapter,
    IsharesAdapter,
    LyxorAdapter,
    SsgaAdapter,
    VaneckAdapter,
)
from src.lookthrough.issuers import normalize_issuer
from src.lookthrough.models import Holding, LookthroughExhausted, LookthroughFailure
from src.portfolio.models import Position
from src.utils.log import get_logger

DEFAULT_FALLBACK_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "etf_holdings.yaml"
)


def build_default_adapters() -> dict[str, BaseAdapter]:
    return {
        "ishares": IsharesAdapter(),
        "vaneck": VaneckAdapter(),
        "ssga": SsgaAdapter(),
        "globalx": GlobalxAdapter(),
        "lyxor": LyxorAdapter(),
    }


def load_fallback_config(path: str | Path = DEFAULT_FALLBACK_PATH) -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.exists():
        return {}

    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        return {}
    return payload


async def resolve_lookthrough(
    portfolio: list[Position],
    *,
    adapters: dict[str, BaseAdapter] | None = None,
    fallback_path: str | Path = DEFAULT_FALLBACK_PATH,
) -> dict[str, list[Holding]]:
    resolved: dict[str, list[Holding]] = {}
    registry = adapters or build_default_adapters()
    fallback_config = load_fallback_config(fallback_path)

    for position in portfolio:
        if position.asset_type != "etf":
            continue

        fallback_entry = _as_mapping(fallback_config.get(position.ticker))
        issuer_name = str(position.issuer or fallback_entry.get("issuer") or "")
        adapter_key = normalize_issuer(issuer_name)
        adapter = registry.get(adapter_key) if adapter_key else None
        lookup_id = _resolve_lookup_id(position.ticker, fallback_entry)

        if adapter is not None:
            try:
                resolved[position.ticker] = await adapter.fetch(lookup_id)
                continue
            except LookthroughFailure:
                fallback_holdings = _parse_fallback_holdings(fallback_entry)
                if fallback_holdings:
                    get_logger("lookthrough").warning(
                        "lookthrough_fallback_used",
                        issuer=position.issuer,
                        ticker=position.ticker,
                    )
                    resolved[position.ticker] = fallback_holdings
                    continue

        fallback_holdings = _parse_fallback_holdings(fallback_entry)
        if fallback_holdings:
            resolved[position.ticker] = fallback_holdings
            continue

        raise LookthroughExhausted(position.ticker, position.issuer)

    return resolved


def _resolve_lookup_id(ticker: str, fallback_entry: dict[str, Any]) -> str:
    aliases = fallback_entry.get("aliases")
    if isinstance(aliases, list) and aliases:
        alias = str(aliases[0]).strip()
        if alias:
            return alias
    return ticker


def _parse_fallback_holdings(fallback_entry: dict[str, Any]) -> list[Holding]:
    raw_holdings = fallback_entry.get("top_10")
    if not isinstance(raw_holdings, list):
        return []

    holdings: list[Holding] = []
    for raw_holding in raw_holdings:
        if not isinstance(raw_holding, dict):
            continue

        ticker = str(raw_holding.get("ticker", "")).strip()
        if not ticker:
            continue

        holdings.append(
            Holding(
                ticker=ticker,
                isin=_optional_text(raw_holding.get("isin")),
                weight=_to_decimal_text(raw_holding.get("weight")),
            )
        )
    return holdings
def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    return text or None


def _to_decimal_text(value: Any) -> Decimal:
    return Decimal(str(value))
