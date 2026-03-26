from __future__ import annotations

import pytest

from proxy_api.reputation import clear_reputation, get_failures, record_failure

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
