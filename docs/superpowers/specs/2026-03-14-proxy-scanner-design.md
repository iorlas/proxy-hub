# Proxy Scanner Service — Design Spec

## Purpose

Continuously scrape free proxy lists, validate them through a multi-stage pipeline, and push working proxies to Redis for g3proxy consumption. Enables proxy hub to operate without paid proxy services or laptops being online.

## Context

POC results (2026-03-14):
- 5,009 proxies scraped from 4 sources (8 endpoints)
- 3.5% alive rate (174/5009)
- 47% YouTube pass rate among alive proxies (82/174)
- 100% of alive proxies are elite anonymity (no IP leakage)
- Best source: proxifly SOCKS5 (57 YouTube-viable from 600 scraped)
- Full cycle completes in ~3-5 minutes

## Architecture

New `proxy-scanner` container in the proxy-hub compose stack. Runs alongside the existing `health-checker` (which manages laptop proxies separately).

```
proxy-scanner
├── source_fetcher.py    — fetch + dedup proxy lists
├── validators.py        — 3-stage validation pipeline
├── pool_manager.py      — Redis pool writes + expiry
├── stats.py             — cycle stats logging
└── main.py              — orchestrator + cycle loop
```

## Validation Pipeline

Three stages, each progressively more expensive. Each stage only processes survivors from the previous one.

### Stage 1: Fast Filter (200 concurrent, 5s timeout)
- HTTP GET to `https://httpbin.org/ip` *through the proxy* (not raw TCP — proves the proxy actually proxies traffic, not just has an open port)
- Measure round-trip latency (ms)
- GeoIP country lookup via local MaxMind GeoLite2 database
- Output: alive proxies with latency + country metadata
- Expected kill rate: ~96%

### Stage 2: Anonymity Check (50 concurrent, 10s timeout)
- HTTP GET `https://httpbin.org/headers` through proxy
- Check if real IP appears in any response header
- Classify: elite / anonymous / transparent
- Reject transparent proxies
- If httpbin.org is unreachable, skip this stage and treat all as passed (the real filter is Stage 3)
- Expected kill rate: ~0% (POC showed all are elite, but this is cheap insurance)

### Stage 3: YouTube Validation (30 concurrent, 20s timeout)
- HTTP GET `https://www.youtube.com/watch?v=jNQXAC9IVRw` ("Me at the zoo" — globally available, online since 2005, first YouTube video ever) through proxy
- Send browser-like User-Agent and Accept-Language headers
- SOCKS5 proxies use remote DNS resolution (proxy resolves youtube.com, not the scanner)
- Check response for content markers: `ytInitialPlayerResponse`, `videoDetails`
- Reject: captcha pages, consent walls, short responses (<5KB), missing markers
- Expected kill rate: ~50% of alive proxies

## Proxy Sources

| Source | Endpoints | Update frequency |
|---|---|---|
| ProxyScrape API | HTTP, SOCKS5 | Every 5 min |
| monosans/proxy-list | HTTP, SOCKS5 | Hourly |
| proxifly/free-proxy-list | HTTP, SOCKS5 | Every 5 min |
| TheSpeedX/PROXY-List | HTTP, SOCKS5 | Daily |

Sources are fetched via HTTP GET (plain text, one proxy per line). No scraping of HTML pages. New sources can be added by appending to a config dict.

If a source fetch fails, log a warning and continue with remaining sources. If all sources fail, still run Pool Update with retained proxies from the previous cycle.

## Cycle Behavior

1. Fetch all sources, dedup by `address:protocol` (same IP on HTTP and SOCKS5 = two separate entries)
2. Copy still-valid proxies from current `proxy_pool:free` into the working set (these skip the pipeline)
3. Run 3-stage pipeline on new candidates (not already in the working set)
4. Add pipeline survivors to the working set
5. Atomic swap: write working set to `proxy_pool:free:tmp`, then `RENAME` to `proxy_pool:free`
6. Log one-line stats summary to Docker logs and stats file
7. Sleep 30 minutes
8. Repeat

This means known-good proxies are retained without re-testing (until their 60-min expiry lapses), while new proxies must pass all three stages. A proxy that was valid last cycle but has now expired gets re-tested from scratch.

Total cycle time: ~3-5 minutes for ~5,000 proxies.

### Progress Logging (Docker logs)

During long cycles, log progress at stage boundaries and periodically within stages:

```
[14:30:00] Cycle starting: 5009 proxies from 8 sources (142 retained from pool)
[14:30:05] Stage 1 complete: 174/4867 alive
[14:30:15] Stage 2 complete: 170/174 anonymous+
[14:32:30] Stage 3 complete: 82/170 YouTube OK
[14:32:30] Pool updated: 224 proxies in proxy_pool:free (142 retained + 82 new)
```

### Stats File (`/data/scanner-stats.log`)

Append-only, one line per cycle. JSON format for easy parsing by Claude Code:

```json
{"ts":"2026-03-14T14:32:30Z","cycle_s":192,"scraped":5009,"retained":142,"alive":174,"anon_ok":170,"youtube_ok":82,"pool_size":224,"sources":{"proxifly_socks5":57,"monosans_http":6,"proxyscrape_http":6,"thespeedx_http":6,"proxifly_http":7}}
```

## Redis

### Key: `proxy_pool:free`

Redis SET, same format as existing `proxy_pool` used by health-checker:

```json
{"type":"socks5","addr":"5.255.117.127:1080","expire":"2026-03-14T15:30:00Z"}
```

Expire field set to current time + 60 minutes. Proxies not re-validated within 60 minutes (roughly 2 missed cycles) drop out automatically.

### Pool Update Strategy

Atomic swap — no separate merge step:
1. Build working set in Python: retained (still-valid from current pool) + new survivors
2. Write entire working set to `proxy_pool:free:tmp` via SADD
3. `RENAME proxy_pool:free:tmp proxy_pool:free`

If no proxies are valid (empty working set), `DEL proxy_pool:free` instead of RENAME.

## Container

- **Base image:** `python:3.13-alpine`
- **Dependencies:** `aiohttp`, `aiohttp-socks`, `redis`, `geoip2`
- **GeoLite2 database:** downloaded at build time, baked into image (~5MB). Requires `MAXMIND_LICENSE_KEY` in CI (free registration at maxmind.com). Country-level accuracy is sufficient; weekly staleness is acceptable.
- **Volume:** `scanner-data:/data` for stats file persistence
- **CMD:** `python -u /app/main.py`
- **Environment variables (from Dokploy env store):**
  - `REDIS_PASSWORD` — same as other services
- **Hardcoded:**
  - `REDIS_HOST=redis` (compose DNS, not env var — learned from Dokploy behavior)
  - Source URLs in code (not configurable via env — changes require a deploy anyway)

## Compose Changes

```yaml
# docker-compose.prod.yml — additions only
services:
  proxy-scanner:
    image: ghcr.io/${GITHUB_OWNER}/proxy-hub-scanner:${IMAGE_TAG:-latest}
    environment:
      - REDIS_PASSWORD=${REDIS_PASSWORD}
    volumes:
      - scanner-data:/data
    restart: unless-stopped
    depends_on:
      - redis

volumes:
  scanner-data:  # new
```

CI workflow: add build step for `proxy-scanner` image (same pattern as health-checker).

## Quality Assurance

Inherited from aggre project conventions, adapted for a service with no database or HTTP API.

### Toolchain

| Tool | Purpose | Config |
|---|---|---|
| Ruff | Linter + formatter | `pyproject.toml` |
| Ty | Static type checking | `pyproject.toml` |
| pytest | Test framework | `pyproject.toml` |
| pytest-cov | Coverage reporting | `pyproject.toml`, `--cov-fail-under=95` |
| diff-cover | Coverage of changed lines | Makefile, `--fail-under=95` |
| pre-commit | Hook chain: format → lint → type check | `.pre-commit-config.yaml` |
| aioresponses | Async HTTP mocking for aiohttp | dev dependency |

### Ruff Config

```toml
[tool.ruff]
target-version = "py313"
line-length = 140

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]
```

### Ty Config

```toml
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
```

### Test Markers

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --strict-markers --cov --cov-report=term:skip-covered --cov-report=xml --cov-fail-under=95"
markers = [
    "unit: pure logic, no I/O",
    "integration: requires Redis or mocked HTTP",
]
```

### Coverage

```toml
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

### Test Structure

```
tests/
├── conftest.py          — Redis fixture (fakeredis), aioresponses fixture
├── test_source_fetcher.py  — mock HTTP responses for each source
├── test_validators.py      — mock proxy responses, test 3-stage pipeline
├── test_pool_manager.py    — Redis read/write with fakeredis
└── test_stats.py           — stats formatting and file append
```

- **Unit tests**: validation logic, dedup, stats formatting, expiry calculation
- **Integration tests**: full cycle with mocked HTTP + fakeredis (no real proxies or Redis needed)
- Redis mocked via `fakeredis[aioredis]` — no test-compose needed

### Pre-commit Hooks

```yaml
repos:
  - repo: local
    hooks:
      - id: ruff-format
        name: ruff format
        entry: bash -c 'uv run ruff format .'
        language: system
        types: [python]
        pass_filenames: false

      - id: ruff-check
        name: ruff check
        entry: bash -c 'uv run ruff check --fix .'
        language: system
        types: [python]
        pass_filenames: false

      - id: ty
        name: ty type check
        entry: bash -c 'uvx ty check .'
        language: system
        types: [python]
        pass_filenames: false
```

### Makefile

```makefile
test:
	uv run pytest tests/

lint:
	uv run ruff check proxy_scanner tests
	uv run ruff format --check proxy_scanner tests
	uvx ty check proxy_scanner tests

coverage-diff:
	uv run diff-cover coverage.xml --compare-branch=origin/main --fail-under=95
```

### TDD Workflow

Red-green-refactor: write failing test → make it pass → clean up. Every module gets tests before implementation. Coverage gate at 95% prevents shipping untested code.

## Out of Scope

- **g3proxy failover routing** — scanner populates `proxy_pool:free` but g3proxy doesn't consume it yet. Follow-up task to add `route_failover` chain: free pool -> laptop pool.
- **Oxylabs integration** — future tier, commented reference only.
- **Merging health-checker into scanner** — keep separate for now. Merge when scanner is proven stable.
- **Prometheus/Grafana** — stats file + Docker logs are sufficient.
- **Web UI** — not needed.
- **GeoIP-based routing** — country data is collected but not used for routing decisions yet.

## Success Criteria

- Scanner runs continuously on shen without intervention
- Maintains 10+ YouTube-viable proxies in `proxy_pool:free`
- Stats file accumulates data for weekly retrospective analysis
- Docker logs show cycle progress without excessive noise
- No impact on existing laptop proxy functionality
