#!/usr/bin/env python3
"""Health checker: probes SOCKS5 backends and updates a Redis set for g3proxy."""

import json
import os
import socket
import time
from datetime import datetime, timezone

import redis

BACKENDS = os.environ.get("BACKENDS", f"{os.environ['ZEP_FQDN']}:1080 {os.environ['MAC_FQDN']}:1080")
EXPIRE_SECONDS = int(os.environ.get("EXPIRE_SECONDS", "120"))
INTERVAL = int(os.environ.get("INTERVAL", "30"))
POOL_KEY = os.environ.get("POOL_KEY", "proxy_pool")
TEMP_KEY = f"{POOL_KEY}:tmp"


def connect_redis() -> redis.Redis:
    return redis.Redis(
        host=os.environ.get("REDIS_HOST", "redis"),
        port=int(os.environ.get("REDIS_PORT", "6379")),
        password=os.environ["REDIS_PASSWORD"],
        decode_responses=True,
    )


def tcp_probe(host: str, port: int, timeout: float = 3.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def resolve_ip(host: str) -> str | None:
    try:
        return socket.getaddrinfo(host, None, socket.AF_INET)[0][4][0]
    except socket.gaierror:
        return None


def now_tag() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def run_cycle(r: redis.Redis, backends: list[tuple[str, int]]) -> None:
    r.delete(TEMP_KEY)

    for host, port in backends:
        if not tcp_probe(host, port):
            print(f"[{now_tag()}] {host}:{port} DOWN")
            continue

        ip = resolve_ip(host)
        if ip is None:
            print(f"[{now_tag()}] {host}:{port} UP but DNS resolve failed, skipping")
            continue

        expire = datetime.fromtimestamp(
            time.time() + EXPIRE_SECONDS, tz=timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

        entry = json.dumps({"type": "socks5", "addr": f"{ip}:{port}", "expire": expire})
        r.sadd(TEMP_KEY, entry)
        print(f"[{now_tag()}] {host}:{port} ({ip}) UP (expire: {expire})")

    # Atomically swap temp → live; if no backends are up, clear pool
    try:
        r.rename(TEMP_KEY, POOL_KEY)
    except redis.exceptions.ResponseError:
        r.delete(POOL_KEY)

    members = r.smembers(POOL_KEY)
    print(f"[{now_tag()}] Pool contents: {members}")


def main() -> None:
    backends = []
    for entry in BACKENDS.split():
        host, port = entry.rsplit(":", 1)
        backends.append((host, int(port)))

    print("Health checker starting")
    print(f"  Backends: {BACKENDS}")
    print(f"  Check interval: {INTERVAL}s")
    print(f"  Expire TTL: {EXPIRE_SECONDS}s")

    r = connect_redis()

    while True:
        try:
            run_cycle(r, backends)
        except redis.exceptions.ConnectionError as e:
            print(f"[{now_tag()}] Redis connection error: {e}")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
