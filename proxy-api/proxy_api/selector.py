"""Weighted proxy selection with reputation-aware ranking."""

from __future__ import annotations

import json
import random
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from proxy_api.pool_manager import POOL_KEY_FAST, POOL_KEY_SLOW
from proxy_api.reputation import get_failures

if TYPE_CHECKING:
    from redis.asyncio import Redis

_TOP_N = 5


async def _load_candidates(r: Redis, pool_key: str, protocol: str) -> list[dict]:
    """Parse pool entries, filter by protocol, and skip expired."""
    members = await r.smembers(pool_key)  # ty: ignore[invalid-await]
    now = time.time()
    candidates = []
    for raw in members:
        try:
            entry = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        if entry.get("type") != protocol:
            continue
        expire_str = entry.get("expire", "")
        try:
            expire_dt = datetime.strptime(expire_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        except ValueError:
            continue
        if expire_dt.timestamp() <= now:
            continue
        candidates.append(entry)
    return candidates


async def get_pool_stats(r: Redis) -> tuple[dict, list[str]]:
    """Return protocol counts per pool and all non-expired proxy addresses.

    Returns a tuple of (stats_dict, all_addresses) where stats_dict has the shape::

        {
            "fast": {"total": N, "socks5": N, "http": N},
            "slow": {"total": N, "socks5": N, "http": N},
        }

    and all_addresses is a flat list of every non-expired proxy address across both pools.
    """
    now = time.time()

    def _parse_pool(members: set) -> tuple[dict, list[str]]:
        counts: dict[str, int] = {"total": 0, "socks5": 0, "http": 0}
        addrs: list[str] = []
        for raw in members:
            try:
                entry = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue
            expire_str = entry.get("expire", "")
            try:
                expire_dt = datetime.strptime(expire_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
            except ValueError:
                continue
            if expire_dt.timestamp() <= now:
                continue
            proto = entry.get("type", "")
            counts["total"] += 1
            if proto in counts:
                counts[proto] += 1
            addr = entry.get("addr", "")
            if addr:
                addrs.append(addr)
        return counts, addrs

    fast_members = await r.smembers(POOL_KEY_FAST)  # ty: ignore[invalid-await]
    slow_members = await r.smembers(POOL_KEY_SLOW)  # ty: ignore[invalid-await]

    fast_counts, fast_addrs = _parse_pool(fast_members)
    slow_counts, slow_addrs = _parse_pool(slow_members)

    stats = {"fast": fast_counts, "slow": slow_counts}
    all_addresses = fast_addrs + slow_addrs
    return stats, all_addresses


async def select_proxy(r: Redis, protocol: str) -> dict | None:
    """Select the best available proxy for the requested protocol.

    Fast pool is preferred. Within a pool, proxies are ranked by failure count
    (ascending) and the result is chosen randomly from the top candidates.
    """
    candidates = await _load_candidates(r, POOL_KEY_FAST, protocol)
    if not candidates:
        candidates = await _load_candidates(r, POOL_KEY_SLOW, protocol)
    if not candidates:
        return None

    addrs = [c["addr"] for c in candidates]
    failures = await get_failures(r, addrs)

    ranked = sorted(candidates, key=lambda c: failures.get(c["addr"], 0))
    top = ranked[:_TOP_N] if len(ranked) > _TOP_N else ranked
    chosen = random.choice(top)  # noqa: S311

    return {"addr": chosen["addr"], "protocol": chosen["type"]}
