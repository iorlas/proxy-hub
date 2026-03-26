from __future__ import annotations

import json

import pytest
from aiohttp.test_utils import TestClient, TestServer

from proxy_api.app import create_app
from proxy_api.pool_manager import POOL_KEY_FAST

pytestmark = pytest.mark.asyncio


def _entry(protocol: str, addr: str, expire: str = "2099-01-01T00:00:00Z") -> str:
    return json.dumps({"type": protocol, "addr": addr, "expire": expire})


@pytest.fixture
async def client(redis_client):
    app = create_app(redis_client)
    async with TestClient(TestServer(app)) as c:
        yield c


async def test_get_proxy_returns_matching_proxy(redis_client, client):
    await redis_client.sadd(POOL_KEY_FAST, _entry("socks5", "1.2.3.4:1080"))

    resp = await client.get("/proxy", params={"protocol": "socks5"})
    assert resp.status == 200
    body = await resp.json()
    assert body["addr"] == "1.2.3.4:1080"
    assert body["protocol"] == "socks5"


async def test_get_proxy_empty_pool_returns_503(client):
    resp = await client.get("/proxy", params={"protocol": "socks5"})
    assert resp.status == 503
    body = await resp.json()
    assert body["error"] == "no_proxy_available"


async def test_get_proxy_missing_protocol_returns_400(client):
    resp = await client.get("/proxy")
    assert resp.status == 400
    body = await resp.json()
    assert body["error"] == "missing_protocol"


async def test_report_failure_increments_count(client):
    resp = await client.post("/proxy/1.2.3.4:8080/fail")
    assert resp.status == 200
    body = await resp.json()
    assert body["addr"] == "1.2.3.4:8080"
    assert body["failures"] == 1

    resp2 = await client.post("/proxy/1.2.3.4:8080/fail")
    body2 = await resp2.json()
    assert body2["failures"] == 2


async def test_health_returns_ok(client):
    resp = await client.get("/health")
    assert resp.status == 200
    body = await resp.json()
    assert body["status"] == "ok"
