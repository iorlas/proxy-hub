# Proxy Hub — Integration Guide

How to route traffic through Proxy Hub from other services and scripts.

## Endpoints

| Protocol | Endpoint | Use when |
|---|---|---|
| SOCKS5 | `socks5h://<TAILSCALE_IP>:2080` | General purpose. DNS resolved by proxy (recommended). |
| SOCKS5 (local DNS) | `socks5://<TAILSCALE_IP>:2080` | You need DNS resolved locally before proxying. |
| SOCKS4 | `socks4://<TAILSCALE_IP>:2080` | Legacy clients that only support SOCKS4. |
| HTTP CONNECT | `http://<TAILSCALE_IP>:2880` | HTTP-aware clients, browser configs, `HTTP_PROXY` env var. |

**Current Tailscale IP:** see `hosts/shen.md` in Knowledge base, or run `ssh shen "tailscale ip -4"`.
The IP may change on node re-registration.

**FQDN alternative:** `shen.shrimp-boa.ts.net` (stable, resolves via Tailscale MagicDNS).

## Access

- **Network:** Tailscale only. Ports are bound to the Tailscale IP — not reachable from the public internet.
- **Authentication:** None. Any Tailscale peer can connect.
- **TLS:** Not terminated by the proxy. Clients establish TLS end-to-end through the tunnel (HTTPS works transparently).

## What you get

Traffic exits through residential IP addresses (laptops on home networks). The pool is dynamic — backends are health-checked every 30s and expire after 120s of being unreachable.

**Expect:**
- Residential IPs (not datacenter) — useful for avoiding bot detection
- 1-2 backends in the pool at any time
- Backends may go offline (laptop sleeping, network change) — pool can be empty

## Client configuration

### Environment variables (most tools, libraries)

```sh
export HTTP_PROXY=http://shen.shrimp-boa.ts.net:2880
export HTTPS_PROXY=http://shen.shrimp-boa.ts.net:2880
# or for SOCKS5:
export ALL_PROXY=socks5h://shen.shrimp-boa.ts.net:2080
```

### curl

```sh
curl -x socks5h://shen.shrimp-boa.ts.net:2080 https://example.com
curl -x http://shen.shrimp-boa.ts.net:2880 https://example.com
```

### Python (requests)

```python
proxies = {
    "http": "socks5h://shen.shrimp-boa.ts.net:2080",
    "https": "socks5h://shen.shrimp-boa.ts.net:2080",
}
requests.get("https://example.com", proxies=proxies)
```

Requires `pip install requests[socks]` for SOCKS support. HTTP proxy works without extras:

```python
proxies = {
    "http": "http://shen.shrimp-boa.ts.net:2880",
    "https": "http://shen.shrimp-boa.ts.net:2880",
}
```

### Node.js (undici / fetch)

```js
import { ProxyAgent } from "undici";
const agent = new ProxyAgent("http://shen.shrimp-boa.ts.net:2880");
const res = await fetch("https://example.com", { dispatcher: agent });
```

### Docker Compose service

```yaml
services:
  my-scraper:
    image: my-scraper:latest
    environment:
      - HTTP_PROXY=http://shen.shrimp-boa.ts.net:2880
      - HTTPS_PROXY=http://shen.shrimp-boa.ts.net:2880
    networks:
      - dokploy-network  # must be on Tailscale-reachable network
```

## Timeouts

The proxy adds latency (residential network + Tailscale relay). Recommended client timeouts:

| Setting | Value | Why |
|---|---|---|
| Connect timeout | 10s | Accounts for Tailscale relay + residential latency |
| Read/response timeout | 30s+ | Depends on target site, not the proxy |
| Retry on connection refused | 1-2 retries with backoff | Pool may be temporarily empty |

## Error handling

| Symptom | Cause | Fix |
|---|---|---|
| Connection refused on port 2080/2880 | g3proxy container down | Check Dokploy deployment status |
| SOCKS5 "general failure" / HTTP 502 | No backends in pool (all laptops offline) | Wait for a laptop to come online, or check health-checker logs |
| Slow responses | Residential network latency | Normal — not datacenter speeds |
| Different IP on each request | Multiple backends in pool, round-robin | Expected behavior |

## Choosing SOCKS5 vs HTTP proxy

| Factor | SOCKS5 (port 2080) | HTTP CONNECT (port 2880) |
|---|---|---|
| Protocol support | Any TCP (HTTP, HTTPS, custom) | HTTP and HTTPS only |
| DNS resolution | `socks5h://` = proxy resolves DNS | Client resolves DNS |
| Library support | Needs SOCKS library (`pysocks`, etc.) | Built into most HTTP clients |
| `HTTP_PROXY` env var | Not standard | Works everywhere |

**Default recommendation:** Use HTTP proxy on port 2880 unless you need non-HTTP TCP traffic or proxy-side DNS resolution.

---

## Proxy API

The Proxy API is a lightweight HTTP service that sits in front of the proxy pool and adds **smart proxy selection with runtime reputation tracking**. It lets callers pick a specific backend proxy address and report failures back, so the system can avoid known-bad proxies within a scan cycle.

Use the Proxy API when you need **session stickiness** — all requests for a single job (e.g. a webpage download including all page resources) go through the same proxy. For simple fire-and-forget traffic (collectors, yt-dlp), the g3proxy ports (2080 / 2880) remain simpler.

### Service overview

- **Port:** 8080 (internal to Docker network, not exposed to the internet)
- **Network:** `dokploy-network` — accessible by any service on the same Docker network
- **State:** Redis Hash key `proxy_reputation` — stores failure count per proxy address
- **Reputation reset:** The scanner resets reputation each scan cycle, so a proxy that was failing gets a fresh start once the pool is rebuilt

### Endpoints

#### `GET /proxy?protocol=socks5|http`

Returns a proxy address selected from the pool, preferring proxies with fewer recorded failures.

**Query parameters:**

| Parameter | Values | Default |
|---|---|---|
| `protocol` | `socks5`, `http` | `socks5` |

**Response (200):**
```json
{"addr": "1.2.3.4:1080", "protocol": "socks5"}
```

**Response (503):** Pool is empty (no backends available for the requested protocol).

#### `POST /proxy/{addr}/fail`

Reports that the proxy at `addr` failed. Increments the failure counter in Redis.

**Path parameter:** `addr` — the address returned by `GET /proxy` (e.g. `1.2.3.4:1080`)

**Response (200):**
```json
{"addr": "1.2.3.4:1080", "failures": 3}
```

#### `GET /health`

Service health check. Returns 200 when the API is up.

### How reputation works

1. `GET /proxy` reads `proxy_reputation` from Redis and selects a backend with the fewest failures.
2. When a download fails, the caller calls `POST /proxy/{addr}/fail` to increment that proxy's failure count.
3. The scanner runs on its normal cycle and rebuilds the proxy pool, which resets `proxy_reputation` to zero for all proxies.

This means reputation is ephemeral within a cycle — a bad proxy is deprioritised for the current cycle, then gets a fresh chance on the next scan.

**Redis key:** `proxy_reputation` (Hash — field: proxy address, value: failure count as integer)

### Usage example (Aggre)

Aggre sets `AGGRE_PROXY_API_URL=http://proxy-api:8080` in its environment. The webpage workflow calls `GET /proxy` before each download to obtain a proxy address, then uses that specific address for all requests in the download session. On any network error, it calls `POST /proxy/{addr}/fail` before retrying or giving up.

```python
# Before download
resp = httpx.get(f"{AGGRE_PROXY_API_URL}/proxy?protocol=socks5")
if resp.status_code == 503:
    raise NoProxyAvailableError()
proxy = resp.json()  # {"addr": "1.2.3.4:1080", "protocol": "socks5"}

# On failure
httpx.post(f"{AGGRE_PROXY_API_URL}/proxy/{proxy['addr']}/fail")
```

### Proxy API vs g3proxy

| | Proxy API (port 8080) | g3proxy (port 2080 / 2880) |
|---|---|---|
| What it returns | A specific proxy address | Proxied connection (round-robin) |
| Session stickiness | Yes — caller pins to returned address | No — each connection may use a different backend |
| Failure reporting | Yes — `POST /proxy/{addr}/fail` | No |
| Use case | Webpage downloads (Aggre), anything needing a stable IP per session | Collectors, yt-dlp, simple HTTP/SOCKS clients |
| Access | Docker-internal (dokploy-network) | Tailscale network |
