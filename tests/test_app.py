"""Test FastAPI application."""

import httpx
import pytest


@pytest.mark.asyncio
async def test_health(client: httpx.AsyncClient) -> None:
    """
    Test liveness health endpoint.

    Args:
        client: Async client.

    Returns:
        None.

    """
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "up", "version": "0.1.0"}


@pytest.mark.asyncio
async def test_readiness(client: httpx.AsyncClient) -> None:
    """
    Test readiness health endpoint.

    Args:
        client: Async client.

    Returns:
        None.

    """
    response = await client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "up"
    assert body["version"] == "0.1.0"
    assert body["checks"]["mongodb"] == "up"
    assert body["checks"]["redis"] == "skipped"
    assert body["checks"]["sql"] == "skipped"
