"""HTTP API for proxy selection and failure reporting."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from aiohttp import web

from proxy_api.reputation import record_failure
from proxy_api.selector import select_proxy

if TYPE_CHECKING:
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


async def health(request: web.Request) -> web.Response:
    """Health check — ping Redis and return 200 or 503."""
    r: Redis = request.app["redis"]
    try:
        await r.ping()
    except Exception:
        log.exception("Redis health check failed")
        return web.json_response({"status": "error"}, status=503)
    return web.json_response({"status": "ok"})


def create_app(redis_client: Redis) -> web.Application:
    """Build the aiohttp application with routes and Redis client."""
    app = web.Application()
    app["redis"] = redis_client
    app.router.add_get("/proxy", get_proxy)
    app.router.add_post("/proxy/{addr}/fail", report_failure)
    app.router.add_get("/health", health)
    return app
