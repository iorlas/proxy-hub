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

from proxy_scanner.pool_manager import POOL_KEY_FAST, POOL_KEY_SLOW, build_proxy_entry, get_retained_proxies, update_pool
from proxy_scanner.source_fetcher import SOURCES, Proxy, fetch_all_sources
from proxy_scanner.stats import CycleStats, append_stats
from proxy_scanner.validators import FAST_THRESHOLD_KBS, check_alive_and_anonymity, check_bandwidth, check_youtube

log = logging.getLogger(__name__)

CYCLE_INTERVAL = 30 * 60  # 30 minutes
STAGE1_CONCURRENCY = 200
STAGE2_CONCURRENCY = 30
STAGE3_CONCURRENCY = 10  # lower — each downloads 2MB
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


async def _run_stage3(proxies: list[Proxy]) -> tuple[list[Proxy], list[Proxy]]:
    """Stage 3: bandwidth test. Returns (fast_proxies, slow_proxies)."""
    sem = asyncio.Semaphore(STAGE3_CONCURRENCY)
    fast: list[Proxy] = []
    slow: list[Proxy] = []

    async def check(proxy: Proxy) -> None:
        async with sem:
            speed = await check_bandwidth(proxy)
            if speed == 0:
                return  # failed download
            if speed >= FAST_THRESHOLD_KBS:
                fast.append(proxy)
            else:
                slow.append(proxy)

    await asyncio.gather(*(check(p) for p in proxies))
    return fast, slow


async def run_cycle(r: aioredis.Redis, stats_path: Path) -> CycleStats:
    """Run one full scan cycle. Returns stats for the cycle."""
    start = time.monotonic()

    # Get real IP for anonymity check
    real_ip = await _get_real_ip()

    # Fetch sources
    all_proxies = await fetch_all_sources()
    log.info("Cycle starting: %d proxies from %d sources", len(all_proxies), len(SOURCES))

    # Retain still-valid proxies from both pools
    retained_fast = await get_retained_proxies(r, POOL_KEY_FAST)
    retained_slow = await get_retained_proxies(r, POOL_KEY_SLOW)
    retained_entries = retained_fast + retained_slow
    retained_addrs = {json.loads(e)["addr"] for e in retained_entries}

    # Filter out already-retained proxies
    new_candidates = [p for p in all_proxies if p.addr not in retained_addrs]

    # Stage 1
    stage1_passed, transparent_rejected = await _run_stage1(new_candidates, real_ip)
    log.info("Stage 1 complete: %d/%d alive + non-transparent", len(stage1_passed), len(new_candidates))

    # Stage 2
    stage2_passed = await _run_stage2(stage1_passed)
    log.info("Stage 2 complete: %d/%d YouTube OK", len(stage2_passed), len(stage1_passed))

    # Stage 3: bandwidth
    fast_proxies, slow_proxies = await _run_stage3(stage2_passed)
    log.info("Stage 3 complete: %d fast, %d slow (of %d YouTube OK)", len(fast_proxies), len(slow_proxies), len(stage2_passed))

    # Build entries
    fast_entries = retained_fast + [build_proxy_entry(p) for p in fast_proxies]
    slow_entries = retained_slow + [build_proxy_entry(p) for p in slow_proxies]

    # Atomic swap both pools
    await update_pool(r, fast_entries, POOL_KEY_FAST)
    await update_pool(r, slow_entries, POOL_KEY_SLOW)

    # Clean up old single pool key (migration)
    await r.delete("proxy_pool:free")

    # Count sources (from all stage-3 survivors)
    source_counts: dict[str, int] = {}
    for p in fast_proxies + slow_proxies:
        source_counts[p.source] = source_counts.get(p.source, 0) + 1

    pool_size = len(fast_entries) + len(slow_entries)
    cycle_seconds = int(time.monotonic() - start)
    stats = CycleStats(
        cycle_seconds=cycle_seconds,
        scraped=len(all_proxies),
        retained=len(retained_entries),
        alive_anon=len(stage1_passed),
        transparent_rejected=transparent_rejected,
        youtube_ok=len(stage2_passed),
        pool_size=pool_size,
        sources=source_counts,
        fast_count=len(fast_entries),
        slow_count=len(slow_entries),
    )

    append_stats(stats_path, stats)
    log.info(
        "Pool updated: %d fast + %d slow proxies (%d retained + %d new)",
        len(fast_entries),
        len(slow_entries),
        len(retained_entries),
        len(fast_proxies) + len(slow_proxies),
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
