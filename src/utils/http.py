"""Shared HTTP client helpers."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import httpx

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


class RetryingAsyncClient(httpx.AsyncClient):
    """AsyncClient with simple exponential-backoff retries."""

    def __init__(
        self,
        *args,
        retries: int = 3,
        backoff_base: float = 0.25,
        sleep_func: Callable[[float], Awaitable[None]] = asyncio.sleep,
        **kwargs,
    ) -> None:
        kwargs.setdefault("http2", True)
        kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
        super().__init__(*args, **kwargs)
        self._retries = retries
        self._backoff_base = backoff_base
        self._sleep_func = sleep_func

    async def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        last_error: Exception | None = None
        last_response: httpx.Response | None = None

        for attempt in range(1, self._retries + 1):
            try:
                response = await super().request(method, url, **kwargs)
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt == self._retries:
                    raise
            else:
                if response.status_code not in RETRYABLE_STATUS_CODES:
                    return response
                last_response = response
                if attempt == self._retries:
                    return response

            await self._sleep_func(self._backoff_base * (2 ** (attempt - 1)))

        if last_response is not None:
            return last_response
        if last_error is not None:
            raise last_error
        raise RuntimeError("HTTP request failed without a captured response or error")


def get_async_client(**kwargs) -> RetryingAsyncClient:
    """Return the shared async HTTP client configuration."""

    return RetryingAsyncClient(**kwargs)
