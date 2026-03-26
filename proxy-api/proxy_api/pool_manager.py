"""Redis pool management — read retained proxies, atomic swap updates."""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from redis.asyncio import Redis

    from proxy_api.source_fetcher import Proxy

log = logging.getLogger(__name__)

POOL_KEY_FAST = "proxy_pool:free:fast"
POOL_KEY_SLOW = "proxy_pool:free:slow"
DEFAULT_EXPIRE_SECONDS = 3600  # 60 minutes


def build_proxy_entry(proxy: Proxy, expire_seconds: int = DEFAULT_EXPIRE_SECONDS) -> str:
    """Build a JSON entry compatible with g3proxy proxy_float format."""
    expire_ts = datetime.fromtimestamp(time.time() + expire_seconds, tz=UTC)
    return json.dumps(
        {
            "type": proxy.protocol,
            "addr": proxy.addr.split("://", 1)[-1] if "://" in proxy.addr else proxy.addr,
            "expire": expire_ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    )


async def get_retained_proxies(r: Redis, pool_key: str) -> list[str]:
    """Get proxies from a pool that haven't expired yet."""
    members = await r.smembers(pool_key)  # type: ignore[invalid-await]  # ty: ignore[invalid-await]
    now = time.time()
    retained = []
    for entry_str in members:
        try:
            entry = json.loads(entry_str)
            expire_str = entry.get("expire", "")
            expire_dt = datetime.strptime(expire_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
            if expire_dt.timestamp() > now:
                retained.append(entry_str)
        except (json.JSONDecodeError, ValueError, KeyError):
            continue
    return retained


async def update_pool(r: Redis, entries: list[str], pool_key: str) -> None:
    """Atomically replace a pool with new entries."""
    tmp_key = f"{pool_key}:tmp"
    if not entries:
        await r.delete(pool_key)
        return
    await r.delete(tmp_key)
    await r.sadd(tmp_key, *entries)  # type: ignore[invalid-await]  # ty: ignore[invalid-await]
    await r.rename(tmp_key, pool_key)
