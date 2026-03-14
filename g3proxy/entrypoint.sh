#!/bin/sh
set -e

# Template the config — substitute env vars
envsubst '${REDIS_PASSWORD}' < /etc/g3proxy/g3proxy.yaml.tmpl > /etc/g3proxy/g3proxy.yaml

echo "g3proxy config rendered:"
cat /etc/g3proxy/g3proxy.yaml

# Replace shell with g3proxy for proper signal handling
exec g3proxy -c /etc/g3proxy/g3proxy.yaml -vvv
