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

### Stage 1: Fast Filter (200 concurrent)
- TCP connection to proxy
- Measure round-trip latency (ms)
- GeoIP country lookup via local MaxMind GeoLite2 database
- Output: alive proxies with latency + country metadata
- Expected kill rate: ~96%

### Stage 2: Anonymity Check (50 concurrent)
- HTTP GET `https://httpbin.org/headers` through proxy
- Check if real IP appears in any response header
- Classify: elite / anonymous / transparent
- Reject transparent proxies
- Expected kill rate: ~0% (POC showed all are elite, but this is cheap insurance)

### Stage 3: YouTube Validation (30 concurrent)
- HTTP GET a known YouTube video page through proxy
- Send browser-like User-Agent and Accept-Language headers
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

## Cycle Behavior

1. Fetch all sources, dedup by address
2. Skip proxies already validated and present in the pool (avoid re-testing known-good proxies)
3. Run 3-stage pipeline on new/expired candidates
4. Push survivors to Redis with expiry
5. Log one-line stats summary to Docker logs and stats file
6. Sleep 30 minutes
7. Repeat

Total cycle time: ~3-5 minutes for ~5,000 proxies.

### Progress Logging (Docker logs)

During long cycles, log progress at stage boundaries and periodically within stages:

```
[14:30:00] Cycle starting: 5009 proxies from 8 sources
[14:30:05] Stage 1 complete: 174/5009 alive
[14:30:15] Stage 2 complete: 170/174 anonymous+
[14:32:30] Stage 3 complete: 82/170 YouTube OK
[14:32:30] Pool updated: 82 proxies in proxy_pool:free
```

### Stats File (`/data/scanner-stats.log`)

Append-only, one line per cycle. Designed for Claude Code to read and analyze:

```
2026-03-14T14:32:30Z cycle=3m12s scraped=5009 alive=174 anon_ok=170 youtube_ok=82 pool_size=82 sources={proxifly_socks5:57,monosans_http:6,proxyscrape_http:6,thespeedx_http:6,proxifly_http:7}
```

## Redis

### Key: `proxy_pool:free`

Redis SET, same format as existing `proxy_pool` used by health-checker:

```json
{"type":"socks5","addr":"5.255.117.127:1080","expire":"2026-03-14T15:30:00Z"}
```

Expire field set to current time + 60 minutes. Proxies not re-validated in the next cycle drop out automatically.

### Pool Update Strategy

Same atomic RENAME pattern as health-checker:
1. Write validated proxies to `proxy_pool:free:tmp`
2. Merge with still-valid entries from current `proxy_pool:free` (proxies that haven't expired and were validated in a prior cycle)
3. `RENAME proxy_pool:free:tmp proxy_pool:free`

## Container

- **Base image:** `python:3.13-alpine`
- **Dependencies:** `aiohttp`, `aiohttp-socks`, `redis`, `geoip2`
- **GeoLite2 database:** downloaded at build time, baked into image (~5MB)
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
