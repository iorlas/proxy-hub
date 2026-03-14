# Proxy Hub — Integration Guide

How to route traffic through Proxy Hub from other services and scripts.

## Endpoints

| Protocol | Endpoint | Use when |
|---|---|---|
| SOCKS5 | `socks5h://<TAILSCALE_IP>:1080` | General purpose. DNS resolved by proxy (recommended). |
| SOCKS5 (local DNS) | `socks5://<TAILSCALE_IP>:1080` | You need DNS resolved locally before proxying. |
| SOCKS4 | `socks4://<TAILSCALE_IP>:1080` | Legacy clients that only support SOCKS4. |
| HTTP CONNECT | `http://<TAILSCALE_IP>:8080` | HTTP-aware clients, browser configs, `HTTP_PROXY` env var. |

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
export HTTP_PROXY=http://shen.shrimp-boa.ts.net:8080
export HTTPS_PROXY=http://shen.shrimp-boa.ts.net:8080
# or for SOCKS5:
export ALL_PROXY=socks5h://shen.shrimp-boa.ts.net:1080
```

### curl

```sh
curl -x socks5h://shen.shrimp-boa.ts.net:1080 https://example.com
curl -x http://shen.shrimp-boa.ts.net:8080 https://example.com
```

### Python (requests)

```python
proxies = {
    "http": "socks5h://shen.shrimp-boa.ts.net:1080",
    "https": "socks5h://shen.shrimp-boa.ts.net:1080",
}
requests.get("https://example.com", proxies=proxies)
```

Requires `pip install requests[socks]` for SOCKS support. HTTP proxy works without extras:

```python
proxies = {
    "http": "http://shen.shrimp-boa.ts.net:8080",
    "https": "http://shen.shrimp-boa.ts.net:8080",
}
```

### Node.js (undici / fetch)

```js
import { ProxyAgent } from "undici";
const agent = new ProxyAgent("http://shen.shrimp-boa.ts.net:8080");
const res = await fetch("https://example.com", { dispatcher: agent });
```

### Docker Compose service

```yaml
services:
  my-scraper:
    image: my-scraper:latest
    environment:
      - HTTP_PROXY=http://shen.shrimp-boa.ts.net:8080
      - HTTPS_PROXY=http://shen.shrimp-boa.ts.net:8080
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
| Connection refused on port 1080/8080 | g3proxy container down | Check Dokploy deployment status |
| SOCKS5 "general failure" / HTTP 502 | No backends in pool (all laptops offline) | Wait for a laptop to come online, or check health-checker logs |
| Slow responses | Residential network latency | Normal — not datacenter speeds |
| Different IP on each request | Multiple backends in pool, round-robin | Expected behavior |

## Choosing SOCKS5 vs HTTP proxy

| Factor | SOCKS5 (port 1080) | HTTP CONNECT (port 8080) |
|---|---|---|
| Protocol support | Any TCP (HTTP, HTTPS, custom) | HTTP and HTTPS only |
| DNS resolution | `socks5h://` = proxy resolves DNS | Client resolves DNS |
| Library support | Needs SOCKS library (`pysocks`, etc.) | Built into most HTTP clients |
| `HTTP_PROXY` env var | Not standard | Works everywhere |

**Default recommendation:** Use HTTP proxy on port 8080 unless you need non-HTTP TCP traffic or proxy-side DNS resolution.
