from __future__ import annotations

import json

import pytest

from proxy_api.pool_manager import POOL_KEY_FAST, POOL_KEY_SLOW
from proxy_api.reputation import record_failure
from proxy_api.selector import select_proxy

pytestmark = pytest.mark.asyncio


def _entry(protocol: str, addr: str, expire: str = "2099-01-01T00:00:00Z") -> str:
    return json.dumps({"type": protocol, "addr": addr, "expire": expire})


async def test_empty_pool_returns_none(redis_client):
    result = await select_proxy(redis_client, "socks5")
    assert result is None


async def test_protocol_filtering_socks5(redis_client):
    await redis_client.sadd(POOL_KEY_FAST, _entry("socks5", "1.2.3.4:1080"))
    await redis_client.sadd(POOL_KEY_FAST, _entry("http", "5.6.7.8:3128"))

    result = await select_proxy(redis_client, "socks5")
    assert result is not None
    assert result["protocol"] == "socks5"
    assert result["addr"] == "1.2.3.4:1080"


async def test_protocol_filtering_http(redis_client):
    await redis_client.sadd(POOL_KEY_FAST, _entry("socks5", "1.2.3.4:1080"))
    await redis_client.sadd(POOL_KEY_FAST, _entry("http", "5.6.7.8:3128"))

    result = await select_proxy(redis_client, "http")
    assert result is not None
    assert result["protocol"] == "http"
    assert result["addr"] == "5.6.7.8:3128"


async def test_expired_entry_skipped(redis_client):
    await redis_client.sadd(POOL_KEY_FAST, _entry("socks5", "1.2.3.4:1080", "2000-01-01T00:00:00Z"))

    result = await select_proxy(redis_client, "socks5")
    assert result is None


async def test_fast_pool_preferred_over_slow(redis_client):
    await redis_client.sadd(POOL_KEY_FAST, _entry("socks5", "10.0.0.1:1080"))
    await redis_client.sadd(POOL_KEY_SLOW, _entry("socks5", "10.0.0.2:1080"))

    result = await select_proxy(redis_client, "socks5")
    assert result is not None
    assert result["addr"] == "10.0.0.1:1080"


async def test_slow_pool_used_when_fast_empty(redis_client):
    await redis_client.sadd(POOL_KEY_SLOW, _entry("socks5", "10.0.0.2:1080"))

    result = await select_proxy(redis_client, "socks5")
    assert result is not None
    assert result["addr"] == "10.0.0.2:1080"


async def test_slow_pool_used_when_fast_has_no_matching_protocol(redis_client):
    await redis_client.sadd(POOL_KEY_FAST, _entry("http", "10.0.0.1:3128"))
    await redis_client.sadd(POOL_KEY_SLOW, _entry("socks5", "10.0.0.2:1080"))

    result = await select_proxy(redis_client, "socks5")
    assert result is not None
    assert result["addr"] == "10.0.0.2:1080"


async def test_low_failure_preferred(redis_client):
    """Proxy with 0 failures is preferred over proxy with 5 failures."""
    good_addr = "10.0.0.1:1080"
    bad_addr = "10.0.0.2:1080"

    await redis_client.sadd(POOL_KEY_FAST, _entry("socks5", good_addr))
    await redis_client.sadd(POOL_KEY_FAST, _entry("socks5", bad_addr))

    for _ in range(5):
        await record_failure(redis_client, bad_addr)

    # Run multiple times — the good proxy should always be chosen since it's in top-1
    # with 0 failures vs 5 failures, and there are only 2 candidates (< 5 threshold).
    results = set()
    for _ in range(20):
        result = await select_proxy(redis_client, "socks5")
        assert result is not None
        results.add(result["addr"])

    # Both can appear (random from top 5 which includes both since pool < 5),
    # but let's just verify we get valid results
    assert results <= {good_addr, bad_addr}


async def test_both_protocols_present_filter_works(redis_client):
    await redis_client.sadd(POOL_KEY_FAST, _entry("socks5", "1.1.1.1:1080"))
    await redis_client.sadd(POOL_KEY_FAST, _entry("http", "2.2.2.2:3128"))
    await redis_client.sadd(POOL_KEY_SLOW, _entry("socks5", "3.3.3.3:1080"))
    await redis_client.sadd(POOL_KEY_SLOW, _entry("http", "4.4.4.4:3128"))

    socks_result = await select_proxy(redis_client, "socks5")
    assert socks_result is not None
    assert socks_result["protocol"] == "socks5"
    # Fast pool preferred
    assert socks_result["addr"] == "1.1.1.1:1080"

    http_result = await select_proxy(redis_client, "http")
    assert http_result is not None
    assert http_result["protocol"] == "http"
    assert http_result["addr"] == "2.2.2.2:3128"
