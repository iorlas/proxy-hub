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


@pytest.fixture
async def stats_client(redis_client, tmp_path):
    stats_path = tmp_path / "stats.log"
    app = create_app(redis_client, stats_path=stats_path)
    async with TestClient(TestServer(app)) as c:
        yield c, stats_path


async def test_stats_with_seeded_pools(redis_client, stats_client):
    client, stats_path = stats_client
    await redis_client.sadd(POOL_KEY_FAST, _entry("socks5", "1.2.3.4:1080"))
    await redis_client.sadd(POOL_KEY_FAST, _entry("http", "5.6.7.8:8080"))
    # Record a failure so reputation is non-trivial
    await redis_client.hincrby("proxy_reputation", "1.2.3.4:1080", 3)
    # Write a scanner stats line
    stats_path.write_text(
        json.dumps(
            {
                "ts": "2026-03-27T12:00:00Z",
                "scraped": 100,
                "alive_anon": 50,
                "youtube_ok": 10,
                "web_general_ok": 30,
                "fast": 20,
                "slow": 10,
            }
        )
        + "\n"
    )

    resp = await client.get("/proxy/stats")
    assert resp.status == 200
    body = await resp.json()

    assert "pools" in body
    assert body["pools"]["fast"]["total"] == 2
    assert body["pools"]["fast"]["socks5"] == 1
    assert body["pools"]["fast"]["http"] == 1

    assert "reputation" in body
    assert body["reputation"]["total_tracked"] == 2
    assert body["reputation"]["total_failures"] == 3

    assert "scanner_last_cycle" in body
    assert body["scanner_last_cycle"]["scraped"] == 100
    assert body["scanner_last_cycle"]["fast"] == 20


async def test_stats_empty_pools(stats_client):
    client, _stats_path = stats_client

    resp = await client.get("/proxy/stats")
    assert resp.status == 200
    body = await resp.json()

    assert body["pools"]["fast"]["total"] == 0
    assert body["pools"]["slow"]["total"] == 0
    assert body["reputation"]["total_tracked"] == 0
    assert body["reputation"]["total_failures"] == 0


async def test_stats_no_stats_file(stats_client):
    client, _stats_path = stats_client
    # stats_path does not exist on disk — scanner_last_cycle should be None

    resp = await client.get("/proxy/stats")
    assert resp.status == 200
    body = await resp.json()
    assert body["scanner_last_cycle"] is None
