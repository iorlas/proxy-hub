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


async def get_reputation_stats(r: Redis, pool_addrs: list[str]) -> dict:
    """Return failure distribution stats for all proxies currently in pools."""
    if not pool_addrs:
        return {
            "total_tracked": 0,
            "proxies_with_failures": 0,
            "total_failures": 0,
            "p50": 0,
            "p90": 0,
            "p99": 0,
            "max": 0,
        }

    raw: dict[bytes, bytes] = await r.hgetall(REPUTATION_KEY)  # ty: ignore[invalid-await]
    reputation = {k.decode() if isinstance(k, bytes) else k: int(v) for k, v in raw.items()}

    counts = [reputation.get(addr, 0) for addr in pool_addrs]
    sorted_counts = sorted(counts)
    n = len(sorted_counts)

    def percentile(p: float) -> int:
        idx = min(int(n * p), n - 1)
        return sorted_counts[idx]

    return {
        "total_tracked": n,
        "proxies_with_failures": sum(1 for c in counts if c > 0),
        "total_failures": sum(counts),
        "p50": percentile(0.50),
        "p90": percentile(0.90),
        "p99": percentile(0.99),
        "max": sorted_counts[-1],
    }
