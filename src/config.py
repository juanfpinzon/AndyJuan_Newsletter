"""Configuration loading utilities."""

from __future__ import annotations

import os
from dataclasses import MISSING, dataclass, field, fields, is_dataclass
from pathlib import Path
from types import UnionType
from typing import Any, get_args, get_origin, get_type_hints

import yaml


class ConfigError(RuntimeError):
    """Raised when configuration cannot be loaded safely."""


@dataclass(frozen=True)
class SnapTradeSettings:
    enabled: bool = False
    client_id: str | None = None
    consumer_key: str | None = None
    user_id: str | None = None
    user_secret: str | None = None
    account_id: str | None = None


@dataclass(frozen=True)
class Settings:
    llm_scoring_model: str
    llm_synthesis_model: str
    llm_fact_check_model: str
    llm_fallback_model: str
    database_path: str
    log_file: str
    news_item_limit: int
    exposure_threshold_percent: float
    entity_match_threshold: float
    theme_item_cap: int = 5
    snaptrade: SnapTradeSettings = field(default_factory=SnapTradeSettings)


DEFAULT_SETTINGS_PATH = Path(__file__).resolve().parents[1] / "config" / "settings.yaml"


def load_settings(path: str | Path | None = None) -> Settings:
    """Load settings from YAML, allowing environment overrides per field."""

    settings_path = Path(path) if path is not None else DEFAULT_SETTINGS_PATH
    if not settings_path.exists():
        raise ConfigError(f"Settings file does not exist: {settings_path}")

    data = yaml.safe_load(settings_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"Settings file must contain a mapping: {settings_path}")

    resolved = _resolve_dataclass(Settings, data)
    return Settings(**resolved)


def _resolve_dataclass(
    dataclass_type: type[Any],
    data: dict[str, Any],
    *,
    env_prefix: str = "",
) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ConfigError(f"Expected mapping for {dataclass_type.__name__}")

    type_hints = get_type_hints(dataclass_type)
    missing = [
        item.name
        for item in fields(dataclass_type)
        if item.name not in data
        and item.default is MISSING
        and item.default_factory is MISSING
    ]
    if missing:
        raise ConfigError(
            "Missing required settings keys: " + ", ".join(sorted(missing))
        )

    resolved: dict[str, Any] = {}
    for item in fields(dataclass_type):
        field_type = type_hints[item.name]
        env_name = f"{env_prefix}{item.name}".upper()
        default_value = _field_default(item)

        if _is_dataclass_type(field_type):
            nested_data = data.get(item.name, {})
            if nested_data is None:
                nested_data = {}
            if not isinstance(nested_data, dict):
                raise ConfigError(f"Expected mapping for {item.name}: {nested_data!r}")
            resolved[item.name] = field_type(
                **_resolve_dataclass(
                    field_type,
                    nested_data,
                    env_prefix=f"{env_name}_",
                )
            )
            continue

        raw_value = os.getenv(env_name, data.get(item.name, default_value))
        resolved[item.name] = _coerce_value(env_name.lower(), raw_value, field_type)

    return resolved


def _field_default(item: Any) -> Any:
    if item.default is not MISSING:
        return item.default
    if item.default_factory is not MISSING:
        return item.default_factory()
    return MISSING


def _is_dataclass_type(expected_type: Any) -> bool:
    return isinstance(expected_type, type) and is_dataclass(expected_type)


def _coerce_value(name: str, value: Any, expected_type: Any) -> Any:
    origin = get_origin(expected_type)
    if origin in (UnionType,):
        return _coerce_union_value(name, value, expected_type)
    if origin is None and isinstance(expected_type, UnionType):
        return _coerce_union_value(name, value, expected_type)
    if origin is not None:
        return _coerce_union_value(name, value, expected_type)

    if expected_type is bool:
        return _coerce_bool(name, value)
    if expected_type is int:
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"Invalid integer for {name}: {value!r}") from exc
    if expected_type is float:
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"Invalid float for {name}: {value!r}") from exc
    if expected_type is str:
        if value is None:
            raise ConfigError(f"Missing string value for {name}")
        text = str(value).strip()
        if not text:
            raise ConfigError(f"Missing string value for {name}")
        return text
    return value


def _coerce_union_value(name: str, value: Any, expected_type: Any) -> Any:
    args = get_args(expected_type)
    allows_none = type(None) in args
    concrete_args = [arg for arg in args if arg is not type(None)]
    if allows_none and (value is None or str(value).strip() == ""):
        return None
    if len(concrete_args) == 1:
        return _coerce_value(name, value, concrete_args[0])
    return value


def _coerce_bool(name: str, value: Any) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"Invalid boolean for {name}: {value!r}")
