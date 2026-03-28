"""Fetch and deduplicate proxy lists from multiple free sources."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import aiohttp

log = logging.getLogger(__name__)

SOURCES: dict[str, str] = {
    "proxyscrape_http": "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=5000&country=all&ssl=all&anonymity=all",
    "proxyscrape_socks5": "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=socks5&timeout=5000&country=all&ssl=all&anonymity=all",
    "monosans_http": "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    "monosans_socks5": "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies_anonymous/socks5.txt",
    "proxifly_http": "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/http/data.txt",
    "proxifly_socks5": "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/socks5/data.txt",
    "thespeedx_http": "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
    "thespeedx_socks5": "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt",
    "nikolait_http": "https://raw.githubusercontent.com/NikolaiT/free-proxy-list/main/proxies/http_working.txt",
    "nikolait_socks5": "https://raw.githubusercontent.com/NikolaiT/free-proxy-list/main/proxies/socks5_working.txt",
    "databay_http": "https://raw.githubusercontent.com/databay-labs/free-proxy-list/master/http.txt",
    "databay_socks5": "https://raw.githubusercontent.com/databay-labs/free-proxy-list/master/socks5.txt",
}


@dataclass(frozen=True)
class Proxy:
    addr: str  # "ip:port"
    source: str
    protocol: str  # "http" or "socks5"

    @property
    def proxy_url(self) -> str:
        if "://" in self.addr:
            return self.addr
        return f"{self.protocol}://{self.addr}"


async def _fetch_one(session: aiohttp.ClientSession, name: str, url: str) -> list[tuple[str, str, str]]:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            text = await resp.text()
            protocol = "socks5" if "socks5" in name else "http"
            results = []
            for line in text.splitlines():
                addr = line.strip()
                if addr and ":" in addr:
                    results.append((addr, name, protocol))
            return results
    except Exception as e:  # noqa: BLE001 — any failure from a proxy source is non-fatal
        log.warning("Failed to fetch source %s: %s", name, e)
        return []


async def fetch_all_sources() -> list[Proxy]:
    """Fetch proxy lists from all sources concurrently, deduplicate by addr+protocol."""
    async with aiohttp.ClientSession() as session:
        tasks = [_fetch_one(session, name, url) for name, url in SOURCES.items()]
        results = await asyncio.gather(*tasks)

    seen: set[tuple[str, str]] = set()
    proxies: list[Proxy] = []
    for entries in results:
        for addr, source, protocol in entries:
            key = (addr, protocol)
            if key not in seen:
                seen.add(key)
                proxies.append(Proxy(addr=addr, source=source, protocol=protocol))

    return proxies
