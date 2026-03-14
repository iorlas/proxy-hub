import fakeredis.aioredis
import pytest


@pytest.fixture
async def redis_client():
    """Fake async Redis client for testing pool operations."""
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()
