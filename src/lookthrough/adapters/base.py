"""Base interface for ETF look-through adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.lookthrough.models import Holding


class BaseAdapter(ABC):
    issuer: str

    @abstractmethod
    async def fetch(self, etf_id: str) -> list[Holding]:
        raise NotImplementedError
