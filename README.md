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
curl --proxy socks5h://shen.shrimp-boa.ts.net:2080 https://api.ipify.org

# HTTP
curl --proxy http://shen.shrimp-boa.ts.net:2880 https://api.ipify.org
```

## Local Dev

```bash
docker compose up --build
```
