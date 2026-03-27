from __future__ import annotations

import pytest

from proxy_api.reputation import clear_reputation, get_failures, get_reputation_stats, record_failure

pytestmark = pytest.mark.asyncio


async def test_record_failure_increments(redis_client):
    count = await record_failure(redis_client, "1.2.3.4:8080")
    assert count == 1
    count = await record_failure(redis_client, "1.2.3.4:8080")
    assert count == 2


async def test_get_failures_returns_zero_for_unknown(redis_client):
    result = await get_failures(redis_client, ["1.2.3.4:8080"])
    assert result == {"1.2.3.4:8080": 0}


async def test_get_failures_returns_counts(redis_client):
    await record_failure(redis_client, "1.2.3.4:8080")
    await record_failure(redis_client, "1.2.3.4:8080")
    result = await get_failures(redis_client, ["1.2.3.4:8080", "5.6.7.8:1080"])
    assert result == {"1.2.3.4:8080": 2, "5.6.7.8:1080": 0}


async def test_clear_reputation_wipes_all(redis_client):
    await record_failure(redis_client, "1.2.3.4:8080")
    await clear_reputation(redis_client)
    result = await get_failures(redis_client, ["1.2.3.4:8080"])
    assert result == {"1.2.3.4:8080": 0}


async def test_get_failures_empty_list(redis_client):
    result = await get_failures(redis_client, [])
    assert result == {}


async def test_get_reputation_stats_empty_pool(redis_client):
    result = await get_reputation_stats(redis_client, [])
    assert result == {
        "total_tracked": 0,
        "proxies_with_failures": 0,
        "total_failures": 0,
        "p50": 0,
        "p90": 0,
        "p99": 0,
        "max": 0,
    }


async def test_get_reputation_stats_percentiles(redis_client):
    addrs = [
        "1.1.1.1:8080",
        "2.2.2.2:8080",
        "3.3.3.3:8080",
        "4.4.4.4:8080",
        "5.5.5.5:8080",
    ]
    # failures: 0, 1, 3, 7, 20  → sorted
    await record_failure(redis_client, addrs[1])
    for _ in range(3):
        await record_failure(redis_client, addrs[2])
    for _ in range(7):
        await record_failure(redis_client, addrs[3])
    for _ in range(20):
        await record_failure(redis_client, addrs[4])

    result = await get_reputation_stats(redis_client, addrs)

    assert result["total_tracked"] == 5
    assert result["proxies_with_failures"] == 4
    assert result["total_failures"] == 31
    # sorted: [0, 1, 3, 7, 20], n=5
    # p50: idx=int(5*0.50)=2 → 3
    # p90: idx=int(5*0.90)=4 → 20
    # p99: idx=int(5*0.99)=4 → 20
    assert result["p50"] == 3
    assert result["p90"] == 20
    assert result["p99"] == 20
    assert result["max"] == 20


async def test_get_reputation_stats_pool_addrs_not_in_reputation(redis_client):
    # Record failures for an addr NOT in pool_addrs
    await record_failure(redis_client, "9.9.9.9:9999")

    pool_addrs = ["1.1.1.1:8080", "2.2.2.2:8080"]
    result = await get_reputation_stats(redis_client, pool_addrs)

    assert result["total_tracked"] == 2
    assert result["proxies_with_failures"] == 0
    assert result["total_failures"] == 0
    assert result["p50"] == 0
    assert result["max"] == 0
