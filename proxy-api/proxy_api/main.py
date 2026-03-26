from __future__ import annotations

import asyncio
import logging
import os

import redis.asyncio as aioredis
from aiohttp import web

from proxy_api.app import create_app
from proxy_api.scanner import run_cycle

logger = logging.getLogger(__name__)

CYCLE_INTERVAL = 30 * 60


async def scanner_loop(r: aioredis.Redis) -> None:
    while True:
        try:
            await run_cycle(r)
        except Exception:
            logger.exception("scanner.cycle_failed")
        await asyncio.sleep(CYCLE_INTERVAL)


def main() -> None:
    redis_host = os.environ.get("REDIS_HOST", "redis")
    redis_port = int(os.environ.get("REDIS_PORT", "6379"))
    redis_password = os.environ.get("REDIS_PASSWORD")

    r: aioredis.Redis = aioredis.Redis(
        host=redis_host,
        port=redis_port,
        password=redis_password,
        decode_responses=True,
    )

    app = create_app(r)

    async def start_background(app: web.Application) -> None:
        app["scanner_task"] = asyncio.create_task(scanner_loop(r))

    async def stop_background(app: web.Application) -> None:
        app["scanner_task"].cancel()

    app.on_startup.append(start_background)
    app.on_cleanup.append(stop_background)
    web.run_app(app, host="0.0.0.0", port=8080)  # noqa: S104


if __name__ == "__main__":
    main()
