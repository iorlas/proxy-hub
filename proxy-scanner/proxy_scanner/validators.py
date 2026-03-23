"""Two-stage proxy validation pipeline."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import aiohttp
from aiohttp_socks import ProxyConnector

if TYPE_CHECKING:
    from proxy_scanner.source_fetcher import Proxy

log = logging.getLogger(__name__)

HTTPBIN_URL = "https://httpbin.org/anything"
YOUTUBE_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
YOUTUBE_MARKERS = ["ytInitialPlayerResponse", "videoDetails"]

PROXY_INDICATING_HEADERS = {
    "x-forwarded-for",
    "x-real-ip",
    "via",
    "forwarded",
    "x-proxy-id",
    "proxy-connection",
    "x-forwarded-host",
}

STAGE1_TIMEOUT = aiohttp.ClientTimeout(connect=5, total=8)
STAGE2_TIMEOUT = aiohttp.ClientTimeout(connect=10, total=20)


@dataclass
class ProxyCheckResult:
    proxy: Proxy
    alive: bool
    latency_ms: int
    anonymity: str  # "elite", "anonymous", "transparent"
    country: str


def _classify_anonymity(headers: dict[str, str], real_ip: str) -> str:
    ip_leaked = any(real_ip in str(v) for v in headers.values())
    if ip_leaked:
        return "transparent"

    has_proxy_headers = any(k.lower() in PROXY_INDICATING_HEADERS for k in headers)
    if has_proxy_headers:
        return "anonymous"

    return "elite"


async def _make_session(proxy: Proxy, timeout: aiohttp.ClientTimeout) -> tuple[aiohttp.ClientSession, str | None]:
    """Create an aiohttp session routed through the proxy. Returns (session, proxy_arg_for_get)."""
    if proxy.protocol == "socks5":
        connector = ProxyConnector.from_url(proxy.proxy_url)
        return aiohttp.ClientSession(connector=connector, timeout=timeout), None
    return aiohttp.ClientSession(timeout=timeout), proxy.proxy_url


async def check_alive_and_anonymity(proxy: Proxy, real_ip: str) -> ProxyCheckResult | None:
    """Stage 1: check proxy is alive + classify anonymity via httpbin.org/anything."""
    start = time.monotonic()
    try:
        session, proxy_arg = await _make_session(proxy, STAGE1_TIMEOUT)
        async with session:
            kwargs: dict = {}
            if proxy_arg:
                kwargs["proxy"] = proxy_arg
            async with session.get(HTTPBIN_URL, **kwargs) as resp:
                data = await resp.json()

        latency = max(1, int((time.monotonic() - start) * 1000))
        headers = data.get("headers", {})
        anonymity = _classify_anonymity(headers, real_ip)

        return ProxyCheckResult(
            proxy=proxy,
            alive=True,
            latency_ms=latency,
            anonymity=anonymity,
            country="",  # GeoIP deferred
        )
    except Exception:  # noqa: BLE001 — any failure means proxy is broken
        return None


async def check_youtube(proxy: Proxy) -> bool:
    """Stage 2: verify proxy can load real YouTube content (not captcha/block)."""
    try:
        session, proxy_arg = await _make_session(proxy, STAGE2_TIMEOUT)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        }
        async with session:
            kwargs: dict = {"headers": headers}
            if proxy_arg:
                kwargs["proxy"] = proxy_arg
            async with session.get(YOUTUBE_URL, **kwargs) as resp:
                body = await resp.text()

        if len(body) < 5000:
            return False

        found = sum(1 for marker in YOUTUBE_MARKERS if marker in body)
        return found >= 2
    except Exception:  # noqa: BLE001 — any failure means proxy is broken
        return False


BANDWIDTH_URL = "https://speed.cloudflare.com/__down?bytes=2000000"
BANDWIDTH_TIMEOUT = aiohttp.ClientTimeout(connect=10, total=45)
FAST_THRESHOLD_KBS = 1024  # 1 MB/s


async def check_bandwidth(proxy: Proxy) -> int:
    """Stage 3: download 2MB test file, return speed in KB/s. Returns 0 on failure."""
    try:
        session, proxy_arg = await _make_session(proxy, BANDWIDTH_TIMEOUT)
        async with session:
            kwargs: dict = {}
            if proxy_arg:
                kwargs["proxy"] = proxy_arg
            start = time.monotonic()
            async with session.get(BANDWIDTH_URL, **kwargs) as resp:
                data = await resp.read()
            elapsed = time.monotonic() - start
            if len(data) < 1_000_000:  # incomplete download
                return 0
            return max(1, int(len(data) / elapsed / 1024))
    except Exception:  # noqa: BLE001 — any failure means proxy is broken
        return 0
