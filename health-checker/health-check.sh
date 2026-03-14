#!/bin/sh
set -e

BACKENDS="${ZEP_FQDN}:1080 ${MAC_FQDN}:1080"
EXPIRE_SECONDS="${EXPIRE_SECONDS:-120}"
INTERVAL="${INTERVAL:-30}"
REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
REDIS_PORT="${REDIS_PORT:-6379}"
POOL_KEY="${POOL_KEY:-proxy_pool}"

echo "Health checker starting"
echo "  Backends: $BACKENDS"
echo "  Check interval: ${INTERVAL}s"
echo "  Expire TTL: ${EXPIRE_SECONDS}s"

RCLI="redis-cli -h $REDIS_HOST -p $REDIS_PORT -a $REDIS_PASSWORD --no-auth-warning"
TEMP_KEY="${POOL_KEY}:tmp"

while true; do
  # Build fresh set each cycle — avoids stale entries
  $RCLI DEL "$TEMP_KEY" > /dev/null 2>&1

  for backend in $BACKENDS; do
    host=$(echo "$backend" | cut -d: -f1)
    port=$(echo "$backend" | cut -d: -f2)
    if nc -z -w3 "$host" "$port" 2>/dev/null; then
      # Resolve FQDN to IP — g3proxy proxy_float requires numeric addr
      ip=$(ping -c1 -W1 "$host" 2>/dev/null | head -1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+')
      if [ -z "$ip" ]; then
        echo "[$(date -u +%H:%M:%S)] $backend UP but DNS resolve failed, skipping"
        continue
      fi
      expire=$(date -u -d "@$(($(date +%s) + EXPIRE_SECONDS))" +%Y-%m-%dT%H:%M:%SZ)
      $RCLI SADD "$TEMP_KEY" "{\"type\":\"socks5\",\"addr\":\"${ip}:${port}\",\"expire\":\"${expire}\"}" > /dev/null
      echo "[$(date -u +%H:%M:%S)] $backend ($ip) UP (expire: $expire)"
    else
      echo "[$(date -u +%H:%M:%S)] $backend DOWN"
    fi
  done

  # Atomically swap temp → live (clears any stale entries)
  $RCLI RENAME "$TEMP_KEY" "$POOL_KEY" > /dev/null 2>&1 || \
    $RCLI DEL "$POOL_KEY" > /dev/null 2>&1  # no backends up → clear pool

  sleep "$INTERVAL"
done
