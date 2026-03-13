# Proxy Hub MVP — Design

## Context

Self-hosted proxy infrastructure per R050 research. Two residential laptops — zep (Zephyrus, Windows) and mac (MacBook, OrbStack) — connected via Tailscale to a Contabo VPS (shen). Need a proxy hub on the VPS that clients (yt-dlp, browserless, httpx) connect to via Tailscale, with traffic distributed across residential laptop IPs.

MVP scope: g3proxy + Redis + health checker, distributing traffic across healthy laptops with direct VPS fallback. No public proxy pool, no session stickiness yet.

## Architecture

```
Clients (via Tailscale FQDN)
  socks5://shen.shrimp-boa.ts.net:1080
  http://shen.shrimp-boa.ts.net:8080
         |
    g3proxy (bound to Tailscale IP, no auth)
         |
    route_failover
    |                         |
  proxy_float              direct_fixed
  (Redis-backed,           (VPS egress,
   round-robin)             last resort)
    |         |
  zep:1080  mac:1080
  (microsocks via Tailscale)

    health-checker ──TCP probe──> zep:1080, mac:1080
         |                        every 30s
         └──SADD──> Redis SET "pool:residential"
                    (2-min expire per entry)
```

### How it works

1. Client connects to g3proxy on shen via Tailscale (no auth needed — Tailscale-only)
2. g3proxy's `proxy_float` escaper polls Redis `pool:residential` every 1s
3. Distributes traffic round-robin across healthy laptops in the pool
4. `health-checker` container probes each laptop via TCP every 30s
5. If reachable → pushes entry to Redis with 2-minute expire
6. If laptop goes offline → entry expires after 2 min → removed from pool
7. During 2-min grace window: some requests may fail (ETL pipeline retries handle this)
8. If pool is empty (all laptops down) → proxy_float returns error → route_failover triggers → direct VPS connection
9. Laptop comes back → next health check re-adds it (auto-recovery)
10. YouTube traffic: should ALWAYS use residential proxy, never direct fallback (fail with error instead). This is a future routing rule — for MVP, all traffic follows the same failover path.

### Access control

- Tailscale-only: g3proxy binds to VPS Tailscale IP, not `0.0.0.0`
- No authentication anywhere: all Tailscale network members are trusted
- No UFW needed: binding to Tailscale IP is sufficient

## Components

### 1. g3proxy (VPS)

Built from source (no official Docker image). SOCKS5 + HTTP frontend, proxy_float for pool, route_failover to direct.

**Config (g3proxy.yaml.tmpl):**

```yaml
runtime:
  thread_number: 2

log:
  default:
    format: text

resolver:
  - name: default
    type: c-ares

escaper:
  # Dynamic pool from Redis — round-robin across healthy laptops
  - name: residential-pool
    type: proxy_float
    source: "redis://:${REDIS_PASSWORD}@127.0.0.1:6379/0?sets_key=pool:residential"
    cache: /var/cache/g3proxy/residential.json
    refresh_interval: 1s
    expire_guard_duration: 10s

  # Last resort: direct from VPS (datacenter IP)
  - name: direct
    type: direct_fixed
    resolver: default

  # Failover: pool → direct
  - name: failover
    type: route_failover
    primary_next: residential-pool
    standby_next: direct

server:
  - name: socks-in
    type: socks_proxy
    escaper: failover
    listen:
      address: "${TAILSCALE_IP}:1080"

  - name: http-in
    type: http_proxy
    escaper: failover
    listen:
      address: "${TAILSCALE_IP}:8080"
```

**Dockerfile:** Multi-stage Rust build:
- Builder: `rust:bookworm`, installs `libclang-dev cmake capnproto`
- Final: `debian:bookworm-slim`, copies `g3proxy` binary
- Entrypoint: `envsubst` on config template → `exec g3proxy`

**Environment variables (set in Dokploy):**

| Var | Description |
|-----|-------------|
| `TAILSCALE_IP` | VPS Tailscale IPv4 |
| `REDIS_PASSWORD` | Redis auth password |

### 2. Redis (VPS)

Off-the-shelf `redis:7-alpine`. Stores proxy pool as a Redis SET.

**Data model:**
```
SET pool:residential
  '{"type":"socks5","addr":"zep.shrimp-boa.ts.net:1080","expire":"2026-03-14T12:02:00Z"}'
  '{"type":"socks5","addr":"mac.shrimp-boa.ts.net:1080","expire":"2026-03-14T12:02:00Z"}'
```

Each entry is a JSON peer object (g3proxy proxy_float format). `expire` is RFC3339, set 2 minutes from push time. g3proxy auto-prunes expired entries on each poll.

### 3. Health checker (VPS)

Alpine container with `redis-cli` and `nc`. Runs in a loop, not cron.

**health-check.sh (~20 lines):**
```bash
#!/bin/sh
BACKENDS="${ZEP_FQDN}:1080 ${MAC_FQDN}:1080"
EXPIRE_SECONDS=120
INTERVAL=30

while true; do
  for backend in $BACKENDS; do
    host=$(echo $backend | cut -d: -f1)
    port=$(echo $backend | cut -d: -f2)
    if nc -z -w3 $host $port 2>/dev/null; then
      expire=$(date -u -d "+${EXPIRE_SECONDS} seconds" +%Y-%m-%dT%H:%M:%SZ)
      redis-cli -a "$REDIS_PASSWORD" SADD pool:residential \
        "{\"type\":\"socks5\",\"addr\":\"${backend}\",\"expire\":\"${expire}\"}"
    fi
  done
  sleep $INTERVAL
done
```

**Behavior:**
- TCP connect check (`nc -z -w3`) — lightweight, no website spamming
- 3-second timeout per probe
- If reachable: pushes/refreshes entry with 2-min expire
- If unreachable: does nothing — entry expires naturally after 2 min
- Grace period: 2 min expire with 30s checks = survives ~4 missed checks before removal
- Auto-recovery: laptop comes back → next successful check re-adds it
- Same infrastructure scales to public proxy lists (replace bash with monosans or jhao104/proxy_pool)

**Environment variables:**

| Var | Description |
|-----|-------------|
| `ZEP_FQDN` | Zephyrus Tailscale FQDN |
| `MAC_FQDN` | MacBook Tailscale FQDN |
| `REDIS_PASSWORD` | Redis auth password |

### 4. microsocks (per laptop)

No auth. Docker container on each laptop.

**zep (Windows, Docker Desktop):**
```bash
docker run -d --restart=unless-stopped --name microsocks --network host rofl0r/microsocks -p 1080
```

**mac (macOS, OrbStack):**
```bash
docker run -d --restart=unless-stopped --name microsocks --network host rofl0r/microsocks -p 1080
```

OrbStack supports `--network host` properly on macOS (unlike Docker Desktop).

### 5. Dokploy deployment

**docker-compose.prod.yml:**

```yaml
services:
  g3proxy:
    image: ghcr.io/<owner>/proxy-hub-g3proxy:${IMAGE_TAG:-latest}
    build:
      context: .
      dockerfile: g3proxy/Dockerfile
    network_mode: host
    env_file:
      - .env
    volumes:
      - g3proxy-cache:/var/cache/g3proxy
    restart: unless-stopped
    depends_on:
      - redis

  redis:
    image: redis:7-alpine
    command: redis-server --requirepass ${REDIS_PASSWORD}
    network_mode: host
    volumes:
      - redis-data:/data
    restart: unless-stopped

  health-checker:
    image: ghcr.io/<owner>/proxy-hub-health:${IMAGE_TAG:-latest}
    build:
      context: .
      dockerfile: health-checker/Dockerfile
    network_mode: host
    env_file:
      - .env
    restart: unless-stopped
    depends_on:
      - redis

volumes:
  redis-data:
  g3proxy-cache:

networks: {}
```

**CI/CD:** Per deployment guidelines:
1. Push to main
2. GHA builds g3proxy + health-checker images, tags with `main-<sha>`
3. Pushes to GHCR
4. Updates `IMAGE_TAG` in Dokploy env via `compose.update` API
5. Triggers Dokploy redeploy
6. Required GitHub secrets: `DOKPLOY_AUTH_TOKEN`, `DOKPLOY_COMPOSE_ID`, `DOKPLOY_URL`
7. Redis uses official image — no build needed

## Workspace Structure

```
~/Workspaces/proxy-hub/
├── g3proxy/
│   ├── Dockerfile
│   ├── entrypoint.sh           # envsubst + exec g3proxy
│   └── config/
│       └── g3proxy.yaml.tmpl
├── health-checker/
│   ├── Dockerfile              # Alpine + redis-cli + nc
│   └── health-check.sh
├── laptop/
│   └── setup.sh                # microsocks Docker (no auth)
├── docker-compose.prod.yml     # Dokploy production
├── docker-compose.yml          # Local dev/testing
├── .github/
│   └── workflows/
│       └── deploy.yml
├── docs/
│   └── guidelines/
│       └── deployment.md       # Copy of deployment guidelines
│   └── superpowers/
│       └── specs/
│           └── 2026-03-14-proxy-hub-mvp-design.md
└── README.md
```

## Verification

1. **Build:** `docker compose build` succeeds for g3proxy and health-checker
2. **Start:** `docker compose up` — all 3 services start, g3proxy listens on :1080/:8080
3. **Health check:** Redis contains entries for healthy laptops: `redis-cli SMEMBERS pool:residential`
4. **SOCKS5 test:** `curl --proxy socks5h://shen.shrimp-boa.ts.net:1080 https://api.ipify.org` → laptop IP
5. **HTTP test:** `curl --proxy http://shen.shrimp-boa.ts.net:8080 https://api.ipify.org` → laptop IP
6. **Distribution:** 10 requests → IPs alternate between zep and mac
7. **Offline test:** Stop microsocks on zep → wait 2 min → all requests use mac
8. **Full offline:** Stop both → returns VPS IP (direct fallback)
9. **Recovery:** Restart microsocks → laptop re-appears in pool after ~30s
10. **Access:** From non-Tailscale → connection refused

## Future iterations

1. **YouTube routing:** Destination-based rule — YouTube traffic must use residential proxy, never direct fallback
2. **Per-user routing:** Credential-based (user=TR → zep, user=RU → mac)
3. **Public proxy pool:** Feed proxy_float with monosans/Zmap-ProxyScanner output via same Redis
4. **Session stickiness:** route_query + UDP session sidecar
5. **Smarter health checks:** Replace TCP probe with end-to-end HTTP check (httpbin.org) for public proxies
