"""Configuration loading utilities."""

from __future__ import annotations

import os
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, get_type_hints

import yaml


class ConfigError(RuntimeError):
    """Raised when configuration cannot be loaded safely."""


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


DEFAULT_SETTINGS_PATH = Path(__file__).resolve().parents[1] / "config" / "settings.yaml"
SETTINGS_TYPE_HINTS = get_type_hints(Settings)


def load_settings(path: str | Path | None = None) -> Settings:
    """Load settings from YAML, allowing environment overrides per field."""

    settings_path = Path(path) if path is not None else DEFAULT_SETTINGS_PATH
    if not settings_path.exists():
        raise ConfigError(f"Settings file does not exist: {settings_path}")

    data = yaml.safe_load(settings_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"Settings file must contain a mapping: {settings_path}")

    missing = [field.name for field in fields(Settings) if field.name not in data]
    if missing:
        raise ConfigError(
            "Missing required settings keys: " + ", ".join(sorted(missing))
        )

    resolved: dict[str, Any] = {}
    for field in fields(Settings):
        raw_value = os.getenv(field.name.upper(), data[field.name])
        resolved[field.name] = _coerce_value(
            field.name,
            raw_value,
            SETTINGS_TYPE_HINTS[field.name],
        )

    return Settings(**resolved)


def _coerce_value(name: str, value: Any, expected_type: type[Any]) -> Any:
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
        return str(value)
    return value
