"""Proxy scanner entry point — orchestrates fetch → validate → pool update cycles."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path

import aiohttp
import redis.asyncio as aioredis

from proxy_scanner.pool_manager import build_proxy_entry, get_retained_proxies, update_pool
from proxy_scanner.source_fetcher import SOURCES, Proxy, fetch_all_sources
from proxy_scanner.stats import CycleStats, append_stats
from proxy_scanner.validators import check_alive_and_anonymity, check_youtube

log = logging.getLogger(__name__)

CYCLE_INTERVAL = 30 * 60  # 30 minutes
STAGE1_CONCURRENCY = 200
STAGE2_CONCURRENCY = 30
STATS_PATH = Path("/data/scanner-stats.log")
REDIS_HOST = "redis"
REDIS_PORT = 6379


async def _get_real_ip() -> str:
    async with aiohttp.ClientSession() as session:
        async with session.get("https://httpbin.org/ip", timeout=aiohttp.ClientTimeout(total=10)) as resp:
            data = await resp.json()
            return data["origin"]


async def _run_stage1(proxies: list[Proxy], real_ip: str) -> tuple[list[Proxy], int]:
    """Stage 1: alive + anonymity check. Returns (non-transparent proxies, transparent_count)."""
    sem = asyncio.Semaphore(STAGE1_CONCURRENCY)
    passed: list[Proxy] = []
    transparent_count = 0

    async def check(proxy: Proxy) -> None:
        nonlocal transparent_count
        async with sem:
            result = await check_alive_and_anonymity(proxy, real_ip)
            if result is None:
                return  # dead
            if result.anonymity == "transparent":
                transparent_count += 1
                return
            passed.append(proxy)

    await asyncio.gather(*(check(p) for p in proxies))
    return passed, transparent_count


async def _run_stage2(proxies: list[Proxy]) -> list[Proxy]:
    """Stage 2: YouTube content validation."""
    sem = asyncio.Semaphore(STAGE2_CONCURRENCY)
    passed: list[Proxy] = []

    async def check(proxy: Proxy) -> None:
        async with sem:
            if await check_youtube(proxy):
                passed.append(proxy)

    await asyncio.gather(*(check(p) for p in proxies))
    return passed


async def run_cycle(r: aioredis.Redis, stats_path: Path) -> CycleStats:
    """Run one full scan cycle. Returns stats for the cycle."""
    start = time.monotonic()

    # Get real IP for anonymity check
    real_ip = await _get_real_ip()

    # Fetch sources
    all_proxies = await fetch_all_sources()
    log.info("Cycle starting: %d proxies from %d sources", len(all_proxies), len(SOURCES))

    # Retain still-valid proxies from current pool
    retained_entries = await get_retained_proxies(r)
    retained_addrs = {json.loads(e)["addr"] for e in retained_entries}

    # Filter out already-retained proxies
    new_candidates = [p for p in all_proxies if p.addr not in retained_addrs]

    # Stage 1
    stage1_passed, transparent_rejected = await _run_stage1(new_candidates, real_ip)
    log.info("Stage 1 complete: %d/%d alive + non-transparent", len(stage1_passed), len(new_candidates))

    # Stage 2
    stage2_passed = await _run_stage2(stage1_passed)
    log.info("Stage 2 complete: %d/%d YouTube OK", len(stage2_passed), len(stage1_passed))

    # Build pool entries
    new_entries = [build_proxy_entry(p) for p in stage2_passed]
    all_entries = retained_entries + new_entries

    # Atomic swap
    await update_pool(r, all_entries)

    # Count sources
    source_counts: dict[str, int] = {}
    for p in stage2_passed:
        source_counts[p.source] = source_counts.get(p.source, 0) + 1

    cycle_seconds = int(time.monotonic() - start)
    stats = CycleStats(
        cycle_seconds=cycle_seconds,
        scraped=len(all_proxies),
        retained=len(retained_entries),
        alive_anon=len(stage1_passed),
        transparent_rejected=transparent_rejected,
        youtube_ok=len(stage2_passed),
        pool_size=len(all_entries),
        sources=source_counts,
    )

    append_stats(stats_path, stats)
    log.info(
        "Pool updated: %d proxies in proxy_pool:free (%d retained + %d new)",
        len(all_entries),
        len(retained_entries),
        len(new_entries),
    )

    return stats


async def _main_loop() -> None:  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s", datefmt="%H:%M:%S")

    r = aioredis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=os.environ["REDIS_PASSWORD"],
        decode_responses=True,
    )

    while True:
        try:
            stats = await run_cycle(r, STATS_PATH)
            log.info("Cycle complete in %ds. Pool size: %d. Sleeping %ds.", stats.cycle_seconds, stats.pool_size, CYCLE_INTERVAL)
        except Exception:
            log.exception("Cycle failed")
        await asyncio.sleep(CYCLE_INTERVAL)


def main() -> None:  # pragma: no cover
    asyncio.run(_main_loop())


if __name__ == "__main__":  # pragma: no cover
    main()
