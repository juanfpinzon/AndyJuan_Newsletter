"""Exposure models."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ExposureEntry:
    entity: str
    composite_weight: Decimal
    paths: tuple[dict[str, object], ...]
