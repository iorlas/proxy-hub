# Proxy Hub — Residential proxy hub via Tailscale

Routes SOCKS5/HTTP traffic through free proxies with failover to residential laptops. Redis-backed proxy pools, 3-stage validation, bandwidth-tiered routing.

## Before Making Code Decisions

- **Before changing proxy-scanner Python code:** read `proxy-scanner/pyproject.toml` for tool config
- **Before changing g3proxy config:** read `g3proxy/config/g3proxy.yaml.tmpl` for escaper/listener architecture
- **Before changing deployment:** read `docs/guidelines/deployment.md`

## Dev Commands

- Lint: `make lint` (check only, never modifies files — safe to run anytime)
- Fix: `make fix` (auto-fix, then runs lint to verify)
- Full gate: `make check` (lint + test)
- Test: `make test` (runs proxy-scanner tests)
- Bootstrap: `make bootstrap` (install tools + pre-commit hooks)
- Never truncate these commands with `| tail` or `| head` — output is already optimized

## Never

- Never push directly to main without CI passing
- Never hardcode Redis passwords or Tailscale IPs in config files
- Never modify `g3proxy/config/g3proxy.yaml.tmpl` port bindings without updating docker-compose.yml, docker-compose.prod.yml, INTEGRATION.md, and README.md

## Ask First

- Before changing port numbers (affects multiple files and deployed clients)
- Before modifying the failover chain order in g3proxy config
- Before adding new proxy sources to proxy-scanner
