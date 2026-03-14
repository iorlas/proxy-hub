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
      expire=$(date -u -d "@$(($(date +%s) + EXPIRE_SECONDS))" +%Y-%m-%dT%H:%M:%SZ)
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
