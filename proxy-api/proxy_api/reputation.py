"""Per-proxy failure count storage using a Redis hash."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from redis.asyncio import Redis

REPUTATION_KEY = "proxy_reputation"


async def record_failure(r: Redis, addr: str) -> int:
    """Increment failure count for the given proxy address and return the new count."""
    return await r.hincrby(REPUTATION_KEY, addr, 1)  # ty: ignore[invalid-await]


async def get_failures(r: Redis, addrs: list[str]) -> dict[str, int]:
    """Return failure counts for each address. Unknown addresses return 0."""
    if not addrs:
        return {}
    values = await r.hmget(REPUTATION_KEY, *addrs)  # ty: ignore[invalid-await,invalid-argument-type]
    return {addr: int(v or 0) for addr, v in zip(addrs, values, strict=True)}


async def clear_reputation(r: Redis) -> None:
    """Wipe all stored failure counts."""
    await r.delete(REPUTATION_KEY)
