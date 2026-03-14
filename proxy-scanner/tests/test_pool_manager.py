import json
import time

import pytest

from proxy_scanner.pool_manager import (
    POOL_KEY,
    POOL_TMP_KEY,
    build_proxy_entry,
    get_retained_proxies,
    update_pool,
)
from proxy_scanner.source_fetcher import Proxy


@pytest.mark.unit
def test_build_proxy_entry_format():
    proxy = Proxy(addr="1.2.3.4:8080", source="test", protocol="socks5")
    entry = build_proxy_entry(proxy, expire_seconds=3600)
    parsed = json.loads(entry)
    assert parsed["type"] == "socks5"
    assert parsed["addr"] == "1.2.3.4:8080"
    assert "expire" in parsed
    assert "T" in parsed["expire"]


@pytest.mark.unit
def test_build_proxy_entry_strips_protocol_prefix():
    """Proxies with socks5:// prefix in addr should have it stripped for g3proxy."""
    proxy = Proxy(addr="socks5://1.2.3.4:1080", source="test", protocol="socks5")
    entry = build_proxy_entry(proxy, expire_seconds=3600)
    parsed = json.loads(entry)
    assert parsed["addr"] == "1.2.3.4:1080"  # bare ip:port, no prefix


@pytest.mark.integration
async def test_get_retained_proxies_returns_valid(redis_client):
    future_expire = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 3600))
    entry = json.dumps({"type": "socks5", "addr": "1.2.3.4:8080", "expire": future_expire})
    await redis_client.sadd(POOL_KEY, entry)
    retained = await get_retained_proxies(redis_client)
    assert len(retained) == 1
    assert retained[0] == entry


@pytest.mark.integration
async def test_get_retained_proxies_skips_expired(redis_client):
    past_expire = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 60))
    entry = json.dumps({"type": "socks5", "addr": "1.2.3.4:8080", "expire": past_expire})
    await redis_client.sadd(POOL_KEY, entry)
    retained = await get_retained_proxies(redis_client)
    assert len(retained) == 0


@pytest.mark.integration
async def test_update_pool_atomic_swap(redis_client):
    entries = ['{"type":"socks5","addr":"1.2.3.4:8080","expire":"2099-01-01T00:00:00Z"}']
    await update_pool(redis_client, entries)
    members = await redis_client.smembers(POOL_KEY)
    assert len(members) == 1
    assert not await redis_client.exists(POOL_TMP_KEY)


@pytest.mark.integration
async def test_update_pool_empty_deletes_key(redis_client):
    await redis_client.sadd(POOL_KEY, "old_entry")
    await update_pool(redis_client, [])
    assert not await redis_client.exists(POOL_KEY)
