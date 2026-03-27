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
