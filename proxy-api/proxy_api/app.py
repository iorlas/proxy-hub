"""HTTP API for proxy selection and failure reporting."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from aiohttp import web

from proxy_api.reputation import get_reputation_stats, record_failure
from proxy_api.scanner_stats import get_last_cycle
from proxy_api.selector import get_pool_stats, select_proxy

if TYPE_CHECKING:
    from pathlib import Path

    from redis.asyncio import Redis

log = logging.getLogger(__name__)


async def get_proxy(request: web.Request) -> web.Response:
    """Return a proxy matching the requested protocol, or 503 if none available."""
    protocol = request.query.get("protocol")
    if not protocol:
        return web.json_response({"error": "missing_protocol"}, status=400)

    r: Redis = request.app["redis"]
    result = await select_proxy(r, protocol)
    if result is None:
        return web.json_response({"error": "no_proxy_available"}, status=503)

    return web.json_response(result)


async def report_failure(request: web.Request) -> web.Response:
    """Increment failure count for a proxy and return the new count."""
    addr = request.match_info["addr"]
    r: Redis = request.app["redis"]
    failures = await record_failure(r, addr)
    return web.json_response({"addr": addr, "failures": failures})


async def stats(request: web.Request) -> web.Response:
    """Return aggregated pool, reputation, and scanner stats."""
    r: Redis = request.app["redis"]
    stats_path: Path | None = request.app["stats_path"]

    pool_data, all_addrs = await get_pool_stats(r)
    rep_data = await get_reputation_stats(r, all_addrs)
    scanner_data = get_last_cycle(stats_path) if stats_path else None

    return web.json_response(
        {
            "pools": pool_data,
            "reputation": rep_data,
            "scanner_last_cycle": scanner_data,
        }
    )


async def health(request: web.Request) -> web.Response:
    """Health check — ping Redis and return 200 or 503."""
    r: Redis = request.app["redis"]
    try:
        await r.ping()
    except Exception:
        log.exception("Redis health check failed")
        return web.json_response({"status": "error"}, status=503)
    return web.json_response({"status": "ok"})


def create_app(redis_client: Redis, stats_path: Path | None = None) -> web.Application:
    """Build the aiohttp application with routes and Redis client."""
    app = web.Application()
    app["redis"] = redis_client
    app["stats_path"] = stats_path
    app.router.add_get("/proxy", get_proxy)
    app.router.add_get("/proxy/stats", stats)
    app.router.add_post("/proxy/{addr}/fail", report_failure)
    app.router.add_get("/health", health)
    return app
