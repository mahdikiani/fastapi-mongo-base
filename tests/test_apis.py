import logging

import httpx
import pytest


@pytest.mark.asyncio
async def test_empty(client: httpx.AsyncClient):
    response = await client.get("/test")
    assert response.status_code == 200
    logging.info(response.json())


@pytest.mark.asyncio
async def test_create(client: httpx.AsyncClient):
    response = await client.post("/test", json={"name": "test"})
    logging.info(response.json())
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_list(client: httpx.AsyncClient):
    response = await client.get("/test")
    assert response.status_code == 200
    logging.info(response.json())
    uid = response.json()["items"][0]["uid"]

    response = await client.get(f"/test/{uid}")
    assert response.status_code == 200
    logging.info(response.json())


@pytest.mark.asyncio
async def test_update(client: httpx.AsyncClient):
    response = await client.get("/test")
    assert response.status_code == 200
    logging.info(response.json())
    uid = response.json()["items"][0]["uid"]

    response = await client.patch(f"/test/{uid}", json={"name": "test2"})
    assert response.status_code == 200
    logging.info(response.json())


@pytest.mark.asyncio
async def test_delete(client: httpx.AsyncClient):
    response = await client.get("/test")
    assert response.status_code == 200
    logging.info(response.json())
    uid = response.json()["items"][0]["uid"]

    response = await client.delete(f"/test/{uid}")
    assert response.status_code == 200
    logging.info(response.json())
