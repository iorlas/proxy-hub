# Proxy Scanner Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a service that continuously scrapes free proxy lists, validates them through a 2-stage pipeline (alive+anonymity via httpbin, then YouTube content check), and pushes working proxies to a Redis set for g3proxy consumption.

**Architecture:** New `proxy-scanner` Python service in the proxy-hub compose stack. Fetches from 4 proxy list sources, runs a 2-stage async validation pipeline, writes survivors to Redis `proxy_pool:free`, logs cycle stats as JSON to a mounted volume. Runs as a Docker container alongside existing health-checker.

**Tech Stack:** Python 3.13, aiohttp, aiohttp-socks, redis, fakeredis (tests), aioresponses (tests), ruff, ty, pytest, uv

**Deferred:** GeoIP (geoip2 + MaxMind) — country data collection deferred until core pipeline is proven. `ProxyCheckResult.country` stays as `""` for now.

**Spec:** `docs/superpowers/specs/2026-03-14-proxy-scanner-design.md`

---

## Chunk 1: Project Scaffolding + Source Fetcher

### Task 1: Initialize proxy-scanner Python project with uv

**Files:**
- Create: `proxy-scanner/pyproject.toml`
- Create: `proxy-scanner/proxy_scanner/__init__.py`
- Create: `proxy-scanner/proxy_scanner/main.py` (stub)
- Create: `proxy-scanner/tests/__init__.py`
- Create: `proxy-scanner/tests/conftest.py`
- Create: `proxy-scanner/Makefile`
- Create: `proxy-scanner/.pre-commit-config.yaml`
- Modify: `.gitignore`

- [ ] **Step 1: Create project directory and pyproject.toml**

```toml
# proxy-scanner/pyproject.toml
[project]
name = "proxy-scanner"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = [
    "aiohttp>=3.11",
    "aiohttp-socks>=0.10",
    "redis>=5.2",
]

[dependency-groups]
dev = [
    "pytest>=8.4",
    "pytest-cov>=6.0",
    "pytest-asyncio>=1.0",
    "diff-cover>=9.0",
    "ruff>=0.14",
    "ty>=0.0.13",
    "fakeredis[aioredis]>=2.26",
    "aioresponses>=0.7",
]

[tool.ruff]
target-version = "py313"
line-length = 140

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]

[tool.ty.environment]
python-version = "3.13"

[tool.ty.rules]
possibly-unresolved-reference = "error"
invalid-argument-type = "error"
missing-argument = "error"
unsupported-operator = "error"
division-by-zero = "error"
unused-ignore-comment = "warn"
redundant-cast = "warn"

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = "-v --strict-markers --cov --cov-report=term:skip-covered --cov-report=xml --cov-fail-under=95"
markers = [
    "unit: pure logic, no I/O",
    "integration: requires Redis or mocked HTTP",
]

[tool.coverage.run]
source = ["proxy_scanner"]
branch = true
omit = ["proxy_scanner/main.py"]

[tool.coverage.report]
skip_covered = true
exclude_lines = [
    "pragma: no cover",
    "if __name__ == .__main__.",
    "if TYPE_CHECKING:",
]
```

- [ ] **Step 2: Create __init__.py files**

```python
# proxy-scanner/proxy_scanner/__init__.py
# (empty)
```

```python
# proxy-scanner/tests/__init__.py
# (empty)
```

- [ ] **Step 3: Create main.py stub**

```python
# proxy-scanner/proxy_scanner/main.py
"""Proxy scanner entry point — orchestrates fetch → validate → pool update cycles."""


def main() -> None:  # pragma: no cover
    pass


if __name__ == "__main__":  # pragma: no cover
    main()
```

- [ ] **Step 4: Create conftest.py with shared fixtures**

```python
# proxy-scanner/tests/conftest.py
import pytest
import fakeredis.aioredis


@pytest.fixture
async def redis_client():
    """Fake async Redis client for testing pool operations."""
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()
```

- [ ] **Step 5: Create Makefile**

```makefile
# proxy-scanner/Makefile
test:
	uv run pytest tests/

lint:
	uv run ruff check proxy_scanner tests
	uv run ruff format --check proxy_scanner tests
	uvx ty check proxy_scanner tests

coverage-diff:
	uv run diff-cover coverage.xml --compare-branch=origin/main --fail-under=95
```

- [ ] **Step 6: Create .pre-commit-config.yaml**

```yaml
# proxy-scanner/.pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: ruff-format
        name: ruff format
        entry: bash -c 'cd proxy-scanner && uv run ruff format .'
        language: system
        types: [python]
        pass_filenames: false

      - id: ruff-check
        name: ruff check
        entry: bash -c 'cd proxy-scanner && uv run ruff check --fix .'
        language: system
        types: [python]
        pass_filenames: false

      - id: ty
        name: ty type check
        entry: bash -c 'cd proxy-scanner && uvx ty check .'
        language: system
        types: [python]
        pass_filenames: false
```

- [ ] **Step 7: Update .gitignore**

Add to existing `.gitignore`:
```
__pycache__/
*.pyc
.venv/
.coverage
coverage.xml
.ruff_cache/
.pytest_cache/
```

- [ ] **Step 8: Initialize uv project and install deps**

Run: `cd proxy-scanner && uv sync`
Expected: lockfile created, all deps installed

- [ ] **Step 9: Verify lint and test commands work**

Run: `cd proxy-scanner && make lint && make test`
Expected: lint passes (no source files to check yet), test passes with 0 tests collected

- [ ] **Step 10: Commit**

```bash
git add proxy-scanner/ .gitignore
git commit -m "feat: scaffold proxy-scanner project with uv, ruff, ty, pytest"
```

---

### Task 2: Source Fetcher — fetch and dedup proxy lists

**Files:**
- Create: `proxy-scanner/proxy_scanner/source_fetcher.py`
- Create: `proxy-scanner/tests/test_source_fetcher.py`

- [ ] **Step 1: Write failing tests for source fetcher**

```python
# proxy-scanner/tests/test_source_fetcher.py
import pytest
from aioresponses import aioresponses

from proxy_scanner.source_fetcher import SOURCES, Proxy, fetch_all_sources


@pytest.mark.unit
def test_sources_dict_has_expected_entries():
    assert len(SOURCES) == 8
    assert "proxyscrape_http" in SOURCES
    assert "proxifly_socks5" in SOURCES


@pytest.mark.integration
async def test_fetch_all_sources_parses_lines():
    with aioresponses() as m:
        m.get(SOURCES["proxyscrape_http"], body="1.2.3.4:8080\n5.6.7.8:3128\n")
        # stub remaining sources as empty
        for name, url in SOURCES.items():
            if name != "proxyscrape_http":
                m.get(url, body="")

        proxies = await fetch_all_sources()

    assert len(proxies) == 2
    assert proxies[0] == Proxy(addr="1.2.3.4:8080", source="proxyscrape_http", protocol="http")
    assert proxies[1] == Proxy(addr="5.6.7.8:3128", source="proxyscrape_http", protocol="http")


@pytest.mark.integration
async def test_fetch_deduplicates_by_addr_protocol():
    with aioresponses() as m:
        m.get(SOURCES["proxyscrape_http"], body="1.2.3.4:8080\n")
        m.get(SOURCES["thespeedx_http"], body="1.2.3.4:8080\n")  # same addr+protocol
        m.get(SOURCES["proxyscrape_socks5"], body="1.2.3.4:8080\n")  # same addr, different protocol — kept
        for name, url in SOURCES.items():
            if name not in ("proxyscrape_http", "thespeedx_http", "proxyscrape_socks5"):
                m.get(url, body="")

        proxies = await fetch_all_sources()

    assert len(proxies) == 2
    protocols = {p.protocol for p in proxies}
    assert protocols == {"http", "socks5"}


@pytest.mark.integration
async def test_fetch_skips_failed_source():
    with aioresponses() as m:
        m.get(SOURCES["proxyscrape_http"], exception=TimeoutError("test"))
        for name, url in SOURCES.items():
            if name != "proxyscrape_http":
                m.get(url, body="9.9.9.9:1080\n" if "socks5" in name else "")

        proxies = await fetch_all_sources()

    # should still get proxies from other sources, not crash
    assert len(proxies) > 0


@pytest.mark.integration
async def test_fetch_strips_whitespace_and_skips_empty():
    with aioresponses() as m:
        m.get(SOURCES["proxyscrape_http"], body="  1.2.3.4:8080  \n\n\n5.6.7.8:3128\n")
        for name, url in SOURCES.items():
            if name != "proxyscrape_http":
                m.get(url, body="")

        proxies = await fetch_all_sources()

    assert len(proxies) == 2
    assert proxies[0].addr == "1.2.3.4:8080"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd proxy-scanner && uv run pytest tests/test_source_fetcher.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'proxy_scanner.source_fetcher'`

- [ ] **Step 3: Implement source_fetcher.py**

```python
# proxy-scanner/proxy_scanner/source_fetcher.py
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
    except Exception as e:
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd proxy-scanner && uv run pytest tests/test_source_fetcher.py -v`
Expected: all 5 tests PASS

- [ ] **Step 5: Run lint**

Run: `cd proxy-scanner && make lint`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add proxy-scanner/proxy_scanner/source_fetcher.py proxy-scanner/tests/test_source_fetcher.py
git commit -m "feat: add source fetcher with dedup and error handling"
```

---

## Chunk 2: Validators (Stage 1 + Stage 2)

### Task 3: Stage 1 validator — fast filter + anonymity via httpbin/anything

**Files:**
- Create: `proxy-scanner/proxy_scanner/validators.py`
- Create: `proxy-scanner/tests/test_validators.py`

- [ ] **Step 1: Write failing tests for stage 1**

```python
# proxy-scanner/tests/test_validators.py
import pytest
from aioresponses import aioresponses

from proxy_scanner.source_fetcher import Proxy
from proxy_scanner.validators import ProxyCheckResult, check_alive_and_anonymity

HTTPBIN_URL = "https://httpbin.org/anything"


@pytest.mark.unit
async def test_alive_proxy_elite():
    """Proxy that returns valid httpbin response with no leak."""
    proxy = Proxy(addr="1.2.3.4:8080", source="test", protocol="http")
    with aioresponses() as m:
        m.get(
            HTTPBIN_URL,
            payload={
                "origin": "1.2.3.4",
                "headers": {"Host": "httpbin.org", "Accept": "*/*"},
            },
        )
        result = await check_alive_and_anonymity(proxy, real_ip="99.99.99.99")

    assert result is not None
    assert result.alive is True
    assert result.anonymity == "elite"
    assert result.latency_ms > 0


@pytest.mark.unit
async def test_transparent_proxy_rejected():
    """Proxy that leaks our real IP in X-Forwarded-For."""
    proxy = Proxy(addr="1.2.3.4:8080", source="test", protocol="http")
    with aioresponses() as m:
        m.get(
            HTTPBIN_URL,
            payload={
                "origin": "1.2.3.4",
                "headers": {"X-Forwarded-For": "99.99.99.99", "Host": "httpbin.org"},
            },
        )
        result = await check_alive_and_anonymity(proxy, real_ip="99.99.99.99")

    assert result is not None
    assert result.anonymity == "transparent"


@pytest.mark.unit
async def test_anonymous_proxy():
    """Proxy headers present but real IP not leaked."""
    proxy = Proxy(addr="1.2.3.4:8080", source="test", protocol="http")
    with aioresponses() as m:
        m.get(
            HTTPBIN_URL,
            payload={
                "origin": "1.2.3.4",
                "headers": {"Via": "1.1 proxy.example.com", "Host": "httpbin.org"},
            },
        )
        result = await check_alive_and_anonymity(proxy, real_ip="99.99.99.99")

    assert result is not None
    assert result.anonymity == "anonymous"


@pytest.mark.unit
async def test_dead_proxy_returns_none():
    """Proxy that times out returns None."""
    proxy = Proxy(addr="1.2.3.4:8080", source="test", protocol="http")
    with aioresponses() as m:
        m.get(HTTPBIN_URL, exception=TimeoutError("test"))
        result = await check_alive_and_anonymity(proxy, real_ip="99.99.99.99")

    assert result is None


@pytest.mark.unit
async def test_socks5_proxy_path():
    """SOCKS5 proxy uses ProxyConnector — verify it doesn't crash."""
    proxy = Proxy(addr="1.2.3.4:1080", source="test", protocol="socks5")
    with aioresponses() as m:
        m.get(
            HTTPBIN_URL,
            payload={"origin": "1.2.3.4", "headers": {"Host": "httpbin.org"}},
        )
        result = await check_alive_and_anonymity(proxy, real_ip="99.99.99.99")

    assert result is not None
    assert result.anonymity == "elite"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd proxy-scanner && uv run pytest tests/test_validators.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement validators.py with stage 1**

```python
# proxy-scanner/proxy_scanner/validators.py
"""Two-stage proxy validation pipeline."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import aiohttp
from aiohttp_socks import ProxyConnector

from proxy_scanner.source_fetcher import Proxy

log = logging.getLogger(__name__)

HTTPBIN_URL = "https://httpbin.org/anything"
YOUTUBE_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
YOUTUBE_MARKERS = ["ytInitialPlayerResponse", "videoDetails"]

PROXY_INDICATING_HEADERS = {
    "x-forwarded-for", "x-real-ip", "via", "forwarded",
    "x-proxy-id", "proxy-connection", "x-forwarded-host",
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


@dataclass
class ValidatedProxy:
    proxy: Proxy
    latency_ms: int
    anonymity: str
    country: str
    youtube_ok: bool


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
    else:
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

        latency = int((time.monotonic() - start) * 1000)
        headers = data.get("headers", {})
        anonymity = _classify_anonymity(headers, real_ip)

        return ProxyCheckResult(
            proxy=proxy,
            alive=True,
            latency_ms=latency,
            anonymity=anonymity,
            country="",  # filled by caller via GeoIP
        )
    except Exception:
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
    except Exception:
        return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd proxy-scanner && uv run pytest tests/test_validators.py -v`
Expected: all 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add proxy-scanner/proxy_scanner/validators.py proxy-scanner/tests/test_validators.py
git commit -m "feat: add stage 1 validator — alive + anonymity via httpbin/anything"
```

---

### Task 4: Stage 2 validator — YouTube content check

**Files:**
- Modify: `proxy-scanner/tests/test_validators.py`

- [ ] **Step 1: Write failing tests for YouTube validation**

Append to `proxy-scanner/tests/test_validators.py`:

```python
from proxy_scanner.validators import check_youtube


@pytest.mark.unit
async def test_youtube_ok_with_markers():
    proxy = Proxy(addr="1.2.3.4:8080", source="test", protocol="http")
    body = "<html>" + "x" * 10000 + "ytInitialPlayerResponse" + "videoDetails" + "</html>"
    with aioresponses() as m:
        m.get(YOUTUBE_URL, body=body)
        result = await check_youtube(proxy)
    assert result is True


@pytest.mark.unit
async def test_youtube_fail_captcha():
    proxy = Proxy(addr="1.2.3.4:8080", source="test", protocol="http")
    body = "<html>Please verify you are not a robot captcha</html>"
    with aioresponses() as m:
        m.get(YOUTUBE_URL, body=body)
        result = await check_youtube(proxy)
    assert result is False


@pytest.mark.unit
async def test_youtube_fail_short_response():
    proxy = Proxy(addr="1.2.3.4:8080", source="test", protocol="http")
    with aioresponses() as m:
        m.get(YOUTUBE_URL, body="short")
        result = await check_youtube(proxy)
    assert result is False


@pytest.mark.unit
async def test_youtube_fail_timeout():
    proxy = Proxy(addr="1.2.3.4:8080", source="test", protocol="http")
    with aioresponses() as m:
        m.get(YOUTUBE_URL, exception=TimeoutError("test"))
        result = await check_youtube(proxy)
    assert result is False


YOUTUBE_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
```

Note: move `YOUTUBE_URL` import or define at module level — the constant is already in validators.py.

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd proxy-scanner && uv run pytest tests/test_validators.py -v`
Expected: all 8 tests PASS (validators.py already has `check_youtube` implemented)

- [ ] **Step 3: Run full test suite + lint**

Run: `cd proxy-scanner && make lint && make test`
Expected: all tests PASS, lint PASS

- [ ] **Step 4: Commit**

```bash
git add proxy-scanner/tests/test_validators.py
git commit -m "test: add YouTube validation tests for stage 2"
```

---

## Chunk 3: Pool Manager + Stats

### Task 5: Pool manager — Redis read/write with atomic swap

**Files:**
- Create: `proxy-scanner/proxy_scanner/pool_manager.py`
- Create: `proxy-scanner/tests/test_pool_manager.py`

- [ ] **Step 1: Write failing tests for pool manager**

```python
# proxy-scanner/tests/test_pool_manager.py
import json
import time

import pytest

from proxy_scanner.pool_manager import (
    POOL_KEY,
    POOL_TMP_KEY,
    build_proxy_entry,
    get_retained_proxies,
    update_pool,
)
from proxy_scanner.source_fetcher import Proxy


@pytest.mark.unit
def test_build_proxy_entry_format():
    proxy = Proxy(addr="1.2.3.4:8080", source="test", protocol="socks5")
    entry = build_proxy_entry(proxy, expire_seconds=3600)
    parsed = json.loads(entry)
    assert parsed["type"] == "socks5"
    assert parsed["addr"] == "1.2.3.4:8080"
    assert "expire" in parsed
    # expire should be roughly 1 hour from now
    assert "T" in parsed["expire"]


@pytest.mark.integration
async def test_get_retained_proxies_returns_valid(redis_client):
    # Add a proxy that expires in the future
    future_expire = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 3600))
    entry = json.dumps({"type": "socks5", "addr": "1.2.3.4:8080", "expire": future_expire})
    await redis_client.sadd(POOL_KEY, entry)

    retained = await get_retained_proxies(redis_client)
    assert len(retained) == 1
    assert retained[0] == entry


@pytest.mark.integration
async def test_get_retained_proxies_skips_expired(redis_client):
    past_expire = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 60))
    entry = json.dumps({"type": "socks5", "addr": "1.2.3.4:8080", "expire": past_expire})
    await redis_client.sadd(POOL_KEY, entry)

    retained = await get_retained_proxies(redis_client)
    assert len(retained) == 0


@pytest.mark.integration
async def test_update_pool_atomic_swap(redis_client):
    entries = ['{"type":"socks5","addr":"1.2.3.4:8080","expire":"2099-01-01T00:00:00Z"}']
    await update_pool(redis_client, entries)

    members = await redis_client.smembers(POOL_KEY)
    assert len(members) == 1
    # tmp key should be gone
    assert not await redis_client.exists(POOL_TMP_KEY)


@pytest.mark.integration
async def test_update_pool_empty_deletes_key(redis_client):
    # Pre-populate
    await redis_client.sadd(POOL_KEY, "old_entry")
    await update_pool(redis_client, [])

    assert not await redis_client.exists(POOL_KEY)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd proxy-scanner && uv run pytest tests/test_pool_manager.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement pool_manager.py**

```python
# proxy-scanner/proxy_scanner/pool_manager.py
"""Redis pool management — read retained proxies, atomic swap updates."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

from redis.asyncio import Redis

from proxy_scanner.source_fetcher import Proxy

log = logging.getLogger(__name__)

POOL_KEY = "proxy_pool:free"
POOL_TMP_KEY = "proxy_pool:free:tmp"
DEFAULT_EXPIRE_SECONDS = 3600  # 60 minutes


def build_proxy_entry(proxy: Proxy, expire_seconds: int = DEFAULT_EXPIRE_SECONDS) -> str:
    """Build a JSON entry compatible with g3proxy proxy_float format."""
    expire_ts = datetime.fromtimestamp(time.time() + expire_seconds, tz=timezone.utc)
    return json.dumps({
        "type": proxy.protocol,
        "addr": proxy.addr,
        "expire": expire_ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
    })


async def get_retained_proxies(r: Redis) -> list[str]:
    """Get proxies from the current pool that haven't expired yet."""
    members = await r.smembers(POOL_KEY)
    now = time.time()
    retained = []
    for entry_str in members:
        try:
            entry = json.loads(entry_str)
            expire_str = entry.get("expire", "")
            expire_dt = datetime.strptime(expire_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            if expire_dt.timestamp() > now:
                retained.append(entry_str)
        except (json.JSONDecodeError, ValueError, KeyError):
            continue
    return retained


async def update_pool(r: Redis, entries: list[str]) -> None:
    """Atomically replace the pool with new entries."""
    if not entries:
        await r.delete(POOL_KEY)
        return

    await r.delete(POOL_TMP_KEY)
    await r.sadd(POOL_TMP_KEY, *entries)
    await r.rename(POOL_TMP_KEY, POOL_KEY)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd proxy-scanner && uv run pytest tests/test_pool_manager.py -v`
Expected: all 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add proxy-scanner/proxy_scanner/pool_manager.py proxy-scanner/tests/test_pool_manager.py
git commit -m "feat: add pool manager with retained proxy logic and atomic swap"
```

---

### Task 6: Stats logger — JSON line per cycle

**Files:**
- Create: `proxy-scanner/proxy_scanner/stats.py`
- Create: `proxy-scanner/tests/test_stats.py`

- [ ] **Step 1: Write failing tests for stats**

```python
# proxy-scanner/tests/test_stats.py
import json
import tempfile
from pathlib import Path

import pytest

from proxy_scanner.stats import CycleStats, format_stats_line, append_stats


@pytest.mark.unit
def test_format_stats_line_is_valid_json():
    stats = CycleStats(
        cycle_seconds=152,
        scraped=5009,
        retained=142,
        alive_anon=170,
        transparent_rejected=4,
        youtube_ok=82,
        pool_size=224,
        sources={"proxifly_socks5": 57, "monosans_http": 6},
    )
    line = format_stats_line(stats)
    parsed = json.loads(line)
    assert parsed["cycle_s"] == 152
    assert parsed["scraped"] == 5009
    assert parsed["pool_size"] == 224
    assert "ts" in parsed
    assert parsed["sources"]["proxifly_socks5"] == 57


@pytest.mark.unit
def test_format_stats_line_has_no_newline():
    stats = CycleStats(cycle_seconds=10, scraped=0, retained=0, alive_anon=0, transparent_rejected=0, youtube_ok=0, pool_size=0, sources={})
    line = format_stats_line(stats)
    assert "\n" not in line


@pytest.mark.unit
def test_append_stats_creates_and_appends():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "stats.log"
        stats = CycleStats(cycle_seconds=10, scraped=100, retained=5, alive_anon=10, transparent_rejected=0, youtube_ok=8, pool_size=13, sources={})

        append_stats(path, stats)
        append_stats(path, stats)

        lines = path.read_text().strip().splitlines()
        assert len(lines) == 2
        json.loads(lines[0])  # should not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd proxy-scanner && uv run pytest tests/test_stats.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement stats.py**

```python
# proxy-scanner/proxy_scanner/stats.py
"""Cycle statistics logging — JSON lines to file + Docker stdout."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class CycleStats:
    cycle_seconds: int
    scraped: int
    retained: int
    alive_anon: int
    transparent_rejected: int
    youtube_ok: int
    pool_size: int
    sources: dict[str, int] = field(default_factory=dict)


def format_stats_line(stats: CycleStats) -> str:
    """Format cycle stats as a single JSON line (no trailing newline)."""
    return json.dumps({
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cycle_s": stats.cycle_seconds,
        "scraped": stats.scraped,
        "retained": stats.retained,
        "alive_anon": stats.alive_anon,
        "transparent_rejected": stats.transparent_rejected,
        "youtube_ok": stats.youtube_ok,
        "pool_size": stats.pool_size,
        "sources": stats.sources,
    })


def append_stats(path: Path, stats: CycleStats) -> None:
    """Append a stats line to the file. Creates file if needed."""
    line = format_stats_line(stats)
    with path.open("a") as f:
        f.write(line + "\n")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd proxy-scanner && uv run pytest tests/test_stats.py -v`
Expected: all 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add proxy-scanner/proxy_scanner/stats.py proxy-scanner/tests/test_stats.py
git commit -m "feat: add cycle stats logger with JSON line format"
```

---

## Chunk 4: Main Orchestrator + Docker + CI

### Task 7: Main orchestrator — the cycle loop

**Files:**
- Modify: `proxy-scanner/proxy_scanner/main.py`
- Create: `proxy-scanner/tests/test_main.py`

- [ ] **Step 1: Write integration test for a full cycle**

```python
# proxy-scanner/tests/test_main.py
import json

import pytest
from aioresponses import aioresponses

from proxy_scanner.main import run_cycle
from proxy_scanner.pool_manager import POOL_KEY
from proxy_scanner.source_fetcher import SOURCES


def _youtube_body() -> str:
    return "<html>" + "x" * 10000 + "ytInitialPlayerResponse" + "videoDetails" + "</html>"


@pytest.mark.integration
async def test_run_cycle_end_to_end(redis_client, tmp_path):
    stats_path = tmp_path / "stats.log"
    with aioresponses() as m:
        # One source returns one proxy
        m.get(SOURCES["proxyscrape_http"], body="1.2.3.4:8080\n")
        for name, url in SOURCES.items():
            if name != "proxyscrape_http":
                m.get(url, body="")

        # Stage 1: httpbin/anything succeeds — elite proxy
        m.get(
            "https://httpbin.org/anything",
            payload={"origin": "1.2.3.4", "headers": {"Host": "httpbin.org"}},
        )

        # Our real IP lookup
        m.get("https://httpbin.org/ip", payload={"origin": "99.99.99.99"})

        # Stage 2: YouTube succeeds
        m.get("https://www.youtube.com/watch?v=jNQXAC9IVRw", body=_youtube_body())

        stats = await run_cycle(redis_client, stats_path)

    assert stats.youtube_ok == 1
    assert stats.pool_size == 1

    # Check Redis has the proxy
    members = await redis_client.smembers(POOL_KEY)
    assert len(members) == 1
    entry = json.loads(next(iter(members)))
    assert entry["addr"] == "1.2.3.4:8080"

    # Check stats file was written
    assert stats_path.exists()
    line = json.loads(stats_path.read_text().strip())
    assert line["youtube_ok"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd proxy-scanner && uv run pytest tests/test_main.py -v`
Expected: FAIL — `ImportError: cannot import name 'run_cycle' from 'proxy_scanner.main'`

- [ ] **Step 3: Implement main.py**

```python
# proxy-scanner/proxy_scanner/main.py
"""Proxy scanner entry point — orchestrates fetch → validate → pool update cycles."""

from __future__ import annotations

import asyncio
import json
import logging
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
    import os

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd proxy-scanner && uv run pytest tests/ -v`
Expected: all tests PASS

- [ ] **Step 5: Run lint**

Run: `cd proxy-scanner && make lint`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add proxy-scanner/proxy_scanner/main.py proxy-scanner/tests/test_main.py
git commit -m "feat: add main orchestrator with cycle loop"
```

---

### Task 8: Dockerfile + compose + CI integration

**Files:**
- Create: `proxy-scanner/Dockerfile`
- Create: `proxy-scanner/requirements.txt`
- Modify: `docker-compose.prod.yml`
- Modify: `docker-compose.yml`
- Modify: `.github/workflows/deploy.yml`

- [ ] **Step 1: Create Dockerfile**

```dockerfile
# proxy-scanner/Dockerfile
FROM python:3.13-alpine

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY proxy_scanner/ ./proxy_scanner/

CMD ["python", "-u", "/app/proxy_scanner/main.py"]
```

Note: GeoIP (MaxMind GeoLite2) is deferred — the initial deployment works without country data. GeoIP integration is a follow-up enhancement once the core pipeline is proven.

- [ ] **Step 2: Create requirements.txt**

```
aiohttp>=3.11
aiohttp-socks>=0.10
redis>=5.2
```

Note: `geoip2` omitted from initial deployment — added when GeoIP is wired in.

- [ ] **Step 3: Update docker-compose.prod.yml**

Add after the `health-checker` service:

```yaml
  proxy-scanner:
    image: ghcr.io/${GITHUB_OWNER}/proxy-hub-scanner:${IMAGE_TAG:-latest}
    environment:
      - REDIS_PASSWORD=${REDIS_PASSWORD}
    volumes:
      - scanner-data:/data
    restart: unless-stopped
    depends_on:
      - redis
```

Add to the `volumes:` section:

```yaml
  scanner-data:
```

- [ ] **Step 4: Update docker-compose.yml (dev)**

Add after the `health-checker` service:

```yaml
  proxy-scanner:
    build:
      context: ./proxy-scanner
      dockerfile: Dockerfile
    env_file:
      - .env
    volumes:
      - scanner-data:/data
    depends_on:
      - redis
```

Add to the `volumes:` section:

```yaml
  scanner-data:
```

- [ ] **Step 5: Update deploy.yml — add scanner build step**

Add after the health-checker build step, before "Deploy to Dokploy":

```yaml
      - name: Build and push proxy-scanner
        uses: docker/build-push-action@v6
        with:
          context: ./proxy-scanner
          push: true
          cache-from: type=gha,scope=scanner
          cache-to: type=gha,mode=max,scope=scanner
          tags: ${{ env.SCANNER_IMAGE }}:${{ steps.tag.outputs.tag }}
```

Add to the `env:` section at the top of the workflow:

```yaml
  SCANNER_IMAGE: ghcr.io/${{ github.repository_owner }}/proxy-hub-scanner
```

- [ ] **Step 6: Verify compose config parses**

Run: `cd /Users/iorlas/Workspaces/proxy-hub && docker compose -f docker-compose.prod.yml config > /dev/null 2>&1; echo "EXIT: $?"`
Expected: `EXIT: 0`

- [ ] **Step 7: Commit**

```bash
git add proxy-scanner/Dockerfile proxy-scanner/requirements.txt docker-compose.prod.yml docker-compose.yml .github/workflows/deploy.yml
git commit -m "feat: add proxy-scanner container to compose stack and CI"
```

---

### Task 9: Final verification — full test suite + coverage

- [ ] **Step 1: Run full test suite with coverage**

Run: `cd proxy-scanner && uv run pytest tests/ -v --cov --cov-report=term --cov-fail-under=95`
Expected: all tests PASS, coverage >= 95%

- [ ] **Step 2: Run lint**

Run: `cd proxy-scanner && make lint`
Expected: PASS

- [ ] **Step 3: Push to deploy**

```bash
git push origin main
```

Watch: `gh run watch $(gh run list --limit 1 --json databaseId -q '.[0].databaseId') --exit-status`
Expected: CI green, all 3 images built and deployed

- [ ] **Step 4: Verify scanner is running**

```bash
ssh -p 2201 iorlas@shen.iorlas.net "docker logs --tail 20 <scanner-container-name>"
```
Expected: cycle progress logs showing proxies scraped, validated, and pool updated

- [ ] **Step 5: Verify stats file**

```bash
ssh -p 2201 iorlas@shen.iorlas.net "docker exec <scanner-container-name> cat /data/scanner-stats.log"
```
Expected: at least one JSON stats line after first cycle completes
