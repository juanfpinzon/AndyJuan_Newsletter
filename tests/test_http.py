import httpx
import pytest
import respx

from src.utils.http import get_async_client


@pytest.mark.asyncio
async def test_async_client_retries_on_retryable_status_codes(
    respx_mock: respx.MockRouter,
) -> None:
    route = respx_mock.get("https://example.com/retry").mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(503),
            httpx.Response(200, json={"ok": True}),
        ]
    )

    async with get_async_client(backoff_base=0) as client:
        response = await client.get("https://example.com/retry")

    assert response.status_code == 200
    assert route.call_count == 3


@pytest.mark.asyncio
async def test_async_client_does_not_retry_non_retryable_client_errors(
    respx_mock: respx.MockRouter,
) -> None:
    route = respx_mock.get("https://example.com/not-found").mock(
        return_value=httpx.Response(404)
    )

    async with get_async_client(backoff_base=0) as client:
        response = await client.get("https://example.com/not-found")

    assert response.status_code == 404
    assert route.call_count == 1
