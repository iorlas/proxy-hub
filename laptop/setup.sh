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
if docker ps -a --format '{{.Names}}' | grep -q '^microsocks$'; then
    echo "microsocks container exists. Removing..."
    docker stop microsocks 2>/dev/null || true
    docker rm microsocks 2>/dev/null || true
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
