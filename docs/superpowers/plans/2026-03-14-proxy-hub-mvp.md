# Proxy Hub MVP Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy a proxy hub on VPS that distributes traffic across residential laptops via Tailscale with health-checked round-robin and direct VPS fallback.

**Architecture:** g3proxy (SOCKS5+HTTP frontend) → proxy_float (Redis-backed round-robin) → residential laptops. Health checker container probes laptops via TCP, pushes to Redis with 2-min expiry. route_failover to direct VPS connection when pool is empty. All Tailscale-only, no auth.

**Tech Stack:** g3proxy (Rust, built from source), Redis 7, bash health checker, Docker Compose, Dokploy, GitHub Actions, Tailscale

**Spec:** `docs/superpowers/specs/2026-03-14-proxy-hub-mvp-design.md`

**Deployment guidelines:** `docs/guidelines/deployment.md` (copy from Knowledge OS)

---

## File Structure

```
~/Workspaces/proxy-hub/
├── g3proxy/
│   ├── Dockerfile              # Multi-stage Rust build of g3proxy
│   ├── entrypoint.sh           # envsubst config template → exec g3proxy
│   └── config/
│       └── g3proxy.yaml.tmpl   # g3proxy config with ${VAR} placeholders
├── health-checker/
│   ├── Dockerfile              # Alpine + redis-cli + netcat
│   └── health-check.sh         # TCP probe loop → Redis SADD
├── laptop/
│   └── setup.sh                # microsocks Docker setup for laptops
├── docker-compose.prod.yml     # Dokploy production (GHCR images, host networking)
├── docker-compose.yml          # Local dev/testing
├── .github/
│   └── workflows/
│       └── deploy.yml          # Build → GHCR → Dokploy trigger
├── .gitignore
├── .env.example                # Template for env vars (no secrets)
├── docs/
│   ├── guidelines/
│   │   └── deployment.md
│   └── superpowers/
│       ├── specs/
│       │   └── 2026-03-14-proxy-hub-mvp-design.md
│       └── plans/
│           └── 2026-03-14-proxy-hub-mvp.md
└── README.md
```

---

## Chunk 1: Repository Setup + Health Checker

### Task 1: Initialize git repo and project scaffolding

**Files:**
- Create: `~/Workspaces/proxy-hub/.gitignore`
- Create: `~/Workspaces/proxy-hub/.env.example`
- Create: `~/Workspaces/proxy-hub/README.md`
- Create: `~/Workspaces/proxy-hub/docs/guidelines/deployment.md`

- [ ] **Step 1: Initialize git repo**

```bash
cd ~/Workspaces/proxy-hub
git init
git branch -m main
```

- [ ] **Step 2: Create .gitignore**

```gitignore
.env
*.log
```

- [ ] **Step 3: Create .env.example**

```bash
# VPS Tailscale IPv4 (run: tailscale ip -4)
TAILSCALE_IP=100.X.X.X

# Laptop Tailscale FQDNs (run: tailscale status)
ZEP_FQDN=zep.shrimp-boa.ts.net
MAC_FQDN=mac.shrimp-boa.ts.net

# Redis
REDIS_PASSWORD=change-me-to-random-string

# Dokploy (set via CI secrets, not here)
# IMAGE_TAG=main-<sha>
```

- [ ] **Step 4: Copy deployment guidelines**

```bash
cp ~/Documents/Knowledge/Researches/036-deployment-platform/guidelines/deployment.md \
   ~/Workspaces/proxy-hub/docs/guidelines/deployment.md
```

- [ ] **Step 5: Create README.md**

```markdown
# Proxy Hub

Self-hosted proxy hub. Routes traffic through residential laptops via Tailscale.

## Architecture

g3proxy (SOCKS5+HTTP) → Redis-backed proxy_float (round-robin) → microsocks on laptops

## Quick Start

1. Copy `.env.example` to `.env` and fill in values
2. Deploy microsocks on laptops: `laptop/setup.sh`
3. Push to GitHub → CI builds and deploys to Dokploy

## Usage

```bash
# SOCKS5
curl --proxy socks5h://shen.shrimp-boa.ts.net:1080 https://api.ipify.org

# HTTP
curl --proxy http://shen.shrimp-boa.ts.net:8080 https://api.ipify.org
```

## Local Dev

```bash
docker compose up --build
```
```

- [ ] **Step 6: Commit**

```bash
git add .gitignore .env.example README.md docs/
git commit -m "init: project scaffolding with deployment guidelines"
```

---

### Task 2: Health checker container

**Files:**
- Create: `health-checker/health-check.sh`
- Create: `health-checker/Dockerfile`

- [ ] **Step 1: Create health-check.sh**

```bash
#!/bin/sh
set -e

BACKENDS="${ZEP_FQDN}:1080 ${MAC_FQDN}:1080"
EXPIRE_SECONDS="${EXPIRE_SECONDS:-120}"
INTERVAL="${INTERVAL:-30}"
REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
REDIS_PORT="${REDIS_PORT:-6379}"
POOL_KEY="${POOL_KEY:-pool:residential}"

echo "Health checker starting"
echo "  Backends: $BACKENDS"
echo "  Check interval: ${INTERVAL}s"
echo "  Expire TTL: ${EXPIRE_SECONDS}s"

while true; do
  for backend in $BACKENDS; do
    host=$(echo "$backend" | cut -d: -f1)
    port=$(echo "$backend" | cut -d: -f2)
    if nc -z -w3 "$host" "$port" 2>/dev/null; then
      expire=$(date -u -d "+${EXPIRE_SECONDS} seconds" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || \
               date -u -v "+${EXPIRE_SECONDS}S" +%Y-%m-%dT%H:%M:%SZ)
      redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" -a "$REDIS_PASSWORD" --no-auth-warning \
        SADD "$POOL_KEY" "{\"type\":\"socks5\",\"addr\":\"${backend}\",\"expire\":\"${expire}\"}" \
        > /dev/null
      echo "[$(date -u +%H:%M:%S)] $backend UP (expire: $expire)"
    else
      echo "[$(date -u +%H:%M:%S)] $backend DOWN"
    fi
  done
  sleep "$INTERVAL"
done
```

Note: The `date` command differs between GNU (Linux) and BSD (macOS). The script tries GNU format first, falls back to BSD. In the Alpine container, GNU `date` is used.

- [ ] **Step 2: Create health-checker Dockerfile**

```dockerfile
FROM alpine:3.21

RUN apk add --no-cache redis netcat-openbsd

COPY health-check.sh /usr/local/bin/health-check.sh
RUN chmod +x /usr/local/bin/health-check.sh

CMD ["/usr/local/bin/health-check.sh"]
```

- [ ] **Step 3: Verify health-check.sh is executable and has correct shebang**

```bash
head -1 health-checker/health-check.sh
# Expected: #!/bin/sh
```

- [ ] **Step 4: Commit**

```bash
git add health-checker/
git commit -m "feat: health checker container with TCP probe and Redis push"
```

---

## Chunk 2: g3proxy Container

### Task 3: g3proxy config template

**Files:**
- Create: `g3proxy/config/g3proxy.yaml.tmpl`

- [ ] **Step 1: Create g3proxy config template**

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
  - name: residential-pool
    type: proxy_float
    source: "redis://:${REDIS_PASSWORD}@127.0.0.1:6379/0?sets_key=pool:residential"
    cache: /var/cache/g3proxy/residential.json
    refresh_interval: 1s
    expire_guard_duration: 10s

  - name: direct
    type: direct_fixed
    resolver: default

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

- [ ] **Step 2: Commit**

```bash
git add g3proxy/config/
git commit -m "feat: g3proxy config template with proxy_float and route_failover"
```

---

### Task 4: g3proxy Dockerfile and entrypoint

**Files:**
- Create: `g3proxy/Dockerfile`
- Create: `g3proxy/entrypoint.sh`

- [ ] **Step 1: Create entrypoint.sh**

```bash
#!/bin/sh
set -e

# Template the config — substitute env vars
envsubst < /etc/g3proxy/g3proxy.yaml.tmpl > /etc/g3proxy/g3proxy.yaml

echo "g3proxy config rendered:"
cat /etc/g3proxy/g3proxy.yaml

# Replace shell with g3proxy for proper signal handling
exec g3proxy -c /etc/g3proxy/g3proxy.yaml -Vvv
```

- [ ] **Step 2: Create Dockerfile**

Reference: `github.com/bytedance/g3` uses `g3proxy/docker/debian.Dockerfile`. We follow the same pattern but with our entrypoint.

```dockerfile
# Stage 1: Build g3proxy from source
FROM rust:bookworm AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    libclang-dev cmake capnproto \
    && rm -rf /var/lib/apt/lists/*

# Clone and build g3proxy
RUN git clone --depth 1 https://github.com/bytedance/g3.git /build
WORKDIR /build

RUN cargo build --profile release-lto -p g3proxy \
    --no-default-features \
    --features vendored-openssl,vendored-c-ares

# Stage 2: Runtime
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    gettext-base ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /build/target/release-lto/g3proxy /usr/bin/g3proxy

RUN mkdir -p /etc/g3proxy /var/cache/g3proxy

COPY config/g3proxy.yaml.tmpl /etc/g3proxy/g3proxy.yaml.tmpl
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
```

Note: `gettext-base` provides `envsubst`. Build will take 10-20 minutes due to Rust compilation. This happens in CI (GitHub Actions), not on the VPS.

- [ ] **Step 3: Commit**

```bash
git add g3proxy/Dockerfile g3proxy/entrypoint.sh
git commit -m "feat: g3proxy Dockerfile with multi-stage Rust build and envsubst entrypoint"
```

---

## Chunk 3: Docker Compose + Laptop Setup

### Task 5: Production and dev Compose files

**Files:**
- Create: `docker-compose.prod.yml`
- Create: `docker-compose.yml`

- [ ] **Step 1: Create docker-compose.prod.yml**

Per deployment guidelines: image from GHCR, `${VAR}` interpolation for secrets, named volumes.

```yaml
services:
  g3proxy:
    image: ghcr.io/${GITHUB_OWNER}/proxy-hub-g3proxy:${IMAGE_TAG:-latest}
    network_mode: host
    environment:
      - TAILSCALE_IP=${TAILSCALE_IP}
      - REDIS_PASSWORD=${REDIS_PASSWORD}
    volumes:
      - g3proxy-cache:/var/cache/g3proxy
    restart: unless-stopped
    depends_on:
      - redis

  redis:
    image: redis:7-alpine
    command: redis-server --requirepass ${REDIS_PASSWORD} --bind 127.0.0.1
    network_mode: host
    volumes:
      - redis-data:/data
    restart: unless-stopped

  health-checker:
    image: ghcr.io/${GITHUB_OWNER}/proxy-hub-health:${IMAGE_TAG:-latest}
    network_mode: host
    environment:
      - ZEP_FQDN=${ZEP_FQDN}
      - MAC_FQDN=${MAC_FQDN}
      - REDIS_PASSWORD=${REDIS_PASSWORD}
    restart: unless-stopped
    depends_on:
      - redis

volumes:
  redis-data:
  g3proxy-cache:
```

Note: `--bind 127.0.0.1` ensures Redis is localhost-only even with host networking. No `build:` in prod — images come from GHCR.

- [ ] **Step 2: Create docker-compose.yml for local dev**

```yaml
services:
  g3proxy:
    build:
      context: ./g3proxy
      dockerfile: Dockerfile
    network_mode: host
    env_file:
      - .env
    volumes:
      - g3proxy-cache:/var/cache/g3proxy
    depends_on:
      - redis

  redis:
    image: redis:7-alpine
    command: redis-server --requirepass ${REDIS_PASSWORD:-devpass} --bind 127.0.0.1
    network_mode: host
    volumes:
      - redis-data:/data

  health-checker:
    build:
      context: ./health-checker
      dockerfile: Dockerfile
    network_mode: host
    env_file:
      - .env
    depends_on:
      - redis

volumes:
  redis-data:
  g3proxy-cache:
```

- [ ] **Step 3: Commit**

```bash
git add docker-compose.prod.yml docker-compose.yml
git commit -m "feat: Docker Compose for production (Dokploy) and local dev"
```

---

### Task 6: Laptop setup script

**Files:**
- Create: `laptop/setup.sh`

- [ ] **Step 1: Create setup.sh**

```bash
#!/bin/bash
set -e

echo "=== Proxy Hub — Laptop Setup ==="
echo "Deploys microsocks as a SOCKS5 proxy on port 1080"
echo "No authentication (Tailscale-only access)"
echo ""

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "ERROR: Docker is not installed."
    echo "  Windows: Install Docker Desktop"
    echo "  macOS: Install OrbStack (recommended) or Docker Desktop"
    exit 1
fi

# Check if already running
if docker ps --format '{{.Names}}' | grep -q '^microsocks$'; then
    echo "microsocks is already running. Stopping..."
    docker stop microsocks && docker rm microsocks
fi

# Run microsocks
docker run -d \
    --restart=unless-stopped \
    --name microsocks \
    --network host \
    rofl0r/microsocks -p 1080

echo ""
echo "microsocks started on port 1080"
echo ""
echo "Verify:"
echo "  curl --proxy socks5h://localhost:1080 https://api.ipify.org"
echo ""
echo "Your Tailscale FQDN (use this in VPS config):"
tailscale status --self --json 2>/dev/null | grep -o '"DNSName":"[^"]*"' || echo "  Run: tailscale status"
```

- [ ] **Step 2: Make executable**

```bash
chmod +x laptop/setup.sh
```

- [ ] **Step 3: Commit**

```bash
git add laptop/
git commit -m "feat: laptop setup script for microsocks deployment"
```

---

## Chunk 4: CI/CD + GitHub Setup

### Task 7: GitHub Actions deploy workflow

**Files:**
- Create: `.github/workflows/deploy.yml`

- [ ] **Step 1: Create workflow directory and deploy workflow**

```bash
mkdir -p .github/workflows
```

Create `.github/workflows/deploy.yml`:

```yaml
name: Build and Deploy

on:
  push:
    branches: [main]

env:
  REGISTRY: ghcr.io
  G3PROXY_IMAGE: ghcr.io/${{ github.repository_owner }}/proxy-hub-g3proxy
  HEALTH_IMAGE: ghcr.io/${{ github.repository_owner }}/proxy-hub-health

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
      - uses: actions/checkout@v4

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Set image tag
        id: tag
        run: echo "tag=main-$(git rev-parse --short HEAD)" >> $GITHUB_OUTPUT

      - name: Build and push g3proxy
        uses: docker/build-push-action@v6
        with:
          context: ./g3proxy
          push: true
          tags: |
            ${{ env.G3PROXY_IMAGE }}:${{ steps.tag.outputs.tag }}
            ${{ env.G3PROXY_IMAGE }}:latest

      - name: Build and push health-checker
        uses: docker/build-push-action@v6
        with:
          context: ./health-checker
          push: true
          tags: |
            ${{ env.HEALTH_IMAGE }}:${{ steps.tag.outputs.tag }}
            ${{ env.HEALTH_IMAGE }}:latest

      - name: Update IMAGE_TAG in Dokploy and redeploy
        env:
          DOKPLOY_URL: ${{ secrets.DOKPLOY_URL }}
          DOKPLOY_TOKEN: ${{ secrets.DOKPLOY_AUTH_TOKEN }}
          COMPOSE_ID: ${{ secrets.DOKPLOY_COMPOSE_ID }}
          IMAGE_TAG: ${{ steps.tag.outputs.tag }}
          # All env vars must be re-sent (Dokploy replaces entire env)
          TAILSCALE_IP: ${{ secrets.TAILSCALE_IP }}
          REDIS_PASSWORD: ${{ secrets.REDIS_PASSWORD }}
          ZEP_FQDN: ${{ secrets.ZEP_FQDN }}
          MAC_FQDN: ${{ secrets.MAC_FQDN }}
          GITHUB_OWNER: ${{ github.repository_owner }}
        run: |
          # Build full env string (Dokploy replaces entire env on update)
          ENV_STRING="IMAGE_TAG=${IMAGE_TAG}
          TAILSCALE_IP=${TAILSCALE_IP}
          REDIS_PASSWORD=${REDIS_PASSWORD}
          ZEP_FQDN=${ZEP_FQDN}
          MAC_FQDN=${MAC_FQDN}
          GITHUB_OWNER=${GITHUB_OWNER}"

          # Update env vars
          curl -sf -X POST "${DOKPLOY_URL}/api/compose.update" \
            -H "Authorization: Bearer ${DOKPLOY_TOKEN}" \
            -H "Content-Type: application/json" \
            -d "{\"composeId\": \"${COMPOSE_ID}\", \"env\": $(echo "$ENV_STRING" | jq -Rs .)}"

          # Trigger redeploy
          curl -sf -X POST "${DOKPLOY_URL}/api/deployment.redeploy" \
            -H "Authorization: Bearer ${DOKPLOY_TOKEN}" \
            -H "Content-Type: application/json" \
            -d "{\"composeId\": \"${COMPOSE_ID}\"}"

          echo "Deploy triggered with IMAGE_TAG=${IMAGE_TAG}"
```

- [ ] **Step 2: Commit**

```bash
git add .github/
git commit -m "feat: GitHub Actions CI/CD — build, push GHCR, deploy via Dokploy"
```

---

### Task 8: Create GitHub repo and push

- [ ] **Step 1: Create GitHub repo**

```bash
cd ~/Workspaces/proxy-hub
gh repo create proxy-hub --private --source=. --push
```

This creates the repo, sets origin, and pushes all commits.

- [ ] **Step 2: Verify repo and first CI run**

```bash
gh run list --limit 1
```

The first run will fail (no Dokploy secrets yet). This is expected.

---

## Chunk 5: Knowledge OS Project Entry + Human Gates

### Task 9: Create Knowledge OS project entry

**Files:**
- Create: `~/Documents/Knowledge/Projects/076-proxy-hub/README.md`

- [ ] **Step 1: Create project entry**

```markdown
---
type: project
id: '076'
name: Proxy Hub
aliases: [proxy hub, proxy infrastructure]
status: active
created: 2026-03-14
updated: 2026-03-14
workspace: ~/Workspaces/proxy-hub
research: R050
tags:
- infrastructure
- proxy
- networking
decay_score: 1.0
---
# Proxy Hub

Self-hosted proxy infrastructure. Routes traffic through residential laptops via Tailscale.

## Architecture

g3proxy (SOCKS5+HTTP) → Redis-backed proxy_float (round-robin) → microsocks on laptops

## Links

- Workspace: `~/Workspaces/proxy-hub`
- Research: [R050 — Self-Hosted Proxy Aggregation](../../Researches/050-self-hosted-proxy-aggregation/README.md)
- GitHub: (set after `gh repo create`)
- Deployment: Dokploy Compose on shen

## Status

- [x] Research complete (R050)
- [x] Design spec
- [ ] First deploy
- [ ] Laptop setup (zep + mac)
- [ ] End-to-end verification
```

- [ ] **Step 2: Commit in Knowledge OS**

```bash
cd ~/Documents/Knowledge
git add Projects/076-proxy-hub/
git commit -m "Add P076 Proxy Hub project entry"
```

---

### Task 10: Human gates — secrets and Dokploy setup

This task requires human action. The agent should present the checklist and wait.

- [ ] **Step 1: ASK HUMAN — Create Dokploy Compose app**

> Create a Compose app named "proxy-hub" in Dokploy UI (https://shen.iorlas.net).
> Note the Compose ID from the URL after creation.

- [ ] **Step 2: ASK HUMAN — Set GitHub secrets**

> Add these secrets to the `proxy-hub` GitHub repo (Settings → Secrets → Actions):
>
> | Secret | Value |
> |--------|-------|
> | `DOKPLOY_URL` | `https://shen.iorlas.net` |
> | `DOKPLOY_AUTH_TOKEN` | (generate in Dokploy: Settings → API Tokens) |
> | `DOKPLOY_COMPOSE_ID` | (from step 1) |
> | `TAILSCALE_IP` | Run `ssh shen "tailscale ip -4"` |
> | `REDIS_PASSWORD` | Generate: `openssl rand -hex 16` |
> | `ZEP_FQDN` | Zep's Tailscale FQDN (e.g., `zep.shrimp-boa.ts.net`) |
> | `MAC_FQDN` | Mac's Tailscale FQDN (e.g., `mac.shrimp-boa.ts.net`) |

- [ ] **Step 3: ASK HUMAN — Set Dokploy env vars**

> Set these env vars in Dokploy Compose app environment (same values as GitHub secrets):
>
> ```
> IMAGE_TAG=latest
> TAILSCALE_IP=<value>
> REDIS_PASSWORD=<value>
> ZEP_FQDN=<value>
> MAC_FQDN=<value>
> GITHUB_OWNER=<your-github-username>
> ```

- [ ] **Step 4: ASK HUMAN — Deploy microsocks on laptops**

> On each laptop, run:
> ```bash
> bash <(curl -s https://raw.githubusercontent.com/<owner>/proxy-hub/main/laptop/setup.sh)
> ```
> Or clone the repo and run `laptop/setup.sh`.

- [ ] **Step 5: Trigger first deploy**

Push an empty commit to trigger CI:
```bash
cd ~/Workspaces/proxy-hub
git commit --allow-empty -m "chore: trigger first deploy"
git push
```

- [ ] **Step 6: Verify deployment**

```bash
# Check CI passed
gh run list --limit 1

# Check containers are running on VPS
ssh shen "docker ps | grep proxy-hub"

# Test SOCKS5
curl --proxy socks5h://shen.shrimp-boa.ts.net:1080 https://api.ipify.org

# Test HTTP
curl --proxy http://shen.shrimp-boa.ts.net:8080 https://api.ipify.org

# Check Redis pool
ssh shen "docker exec \$(docker ps -q -f name=redis) redis-cli -a \$REDIS_PASSWORD --no-auth-warning SMEMBERS pool:residential"
```

- [ ] **Step 7: Distribution test**

```bash
# Run 10 requests, expect IPs to alternate between zep and mac
for i in $(seq 1 10); do
  curl -s --proxy socks5h://shen.shrimp-boa.ts.net:1080 https://api.ipify.org
  echo ""
done
```

Expected: Two different IPs appearing in roughly alternating pattern.

- [ ] **Step 8: Offline/failover test**

```bash
# On zep: stop microsocks
# ssh zep "docker stop microsocks"

# Wait 2 minutes for health check entry to expire, then test:
curl --proxy socks5h://shen.shrimp-boa.ts.net:1080 https://api.ipify.org
# Expected: mac's IP only

# On zep: stop microsocks on mac too
# ssh mac "docker stop microsocks"

# Wait 2 minutes, then test:
curl --proxy socks5h://shen.shrimp-boa.ts.net:1080 https://api.ipify.org
# Expected: VPS public IP (direct fallback)
```

- [ ] **Step 9: Recovery test**

```bash
# On zep: restart microsocks
# ssh zep "docker start microsocks"

# Wait 30s for health check to re-add, then test:
curl --proxy socks5h://shen.shrimp-boa.ts.net:1080 https://api.ipify.org
# Expected: zep's IP is back in rotation
```
