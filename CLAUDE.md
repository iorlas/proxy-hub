# Proxy Hub — Residential proxy hub via Tailscale

Routes SOCKS5/HTTP traffic through free proxies with failover to residential laptops. Redis-backed proxy pools, 3-stage validation, bandwidth-tiered routing.

## Before Making Code Decisions

- **Before changing proxy-scanner Python code:** read `proxy-scanner/pyproject.toml` for tool config
- **Before changing g3proxy config:** read `g3proxy/config/g3proxy.yaml.tmpl` for escaper/listener architecture
- **Before changing deployment:** read `docs/guidelines/deployment.md`

## Dev Commands (proxy-scanner)

- Run tests: `make -C proxy-scanner test` (with coverage — check for uncovered lines in files you changed)
- Lint: `make -C proxy-scanner lint` (check only, never modifies files — safe for AI to run anytime)
- Fix: `make -C proxy-scanner fix` (auto-fix, then runs lint to verify)
- After fixing: `make -C proxy-scanner fix && make -C proxy-scanner test` (fix already includes lint)
- Full gate: `make -C proxy-scanner check` (lint + test)
- Never truncate these commands with `| tail` or `| head` — output is already optimized for minimal noise, truncation hides errors

## Never

- Never push directly to main without CI passing
- Never hardcode Redis passwords or Tailscale IPs in config files
- Never modify `g3proxy/config/g3proxy.yaml.tmpl` port bindings without updating docker-compose.yml, docker-compose.prod.yml, INTEGRATION.md, and README.md

## Ask First

- Before changing port numbers (affects multiple files and deployed clients)
- Before modifying the failover chain order in g3proxy config
- Before adding new proxy sources to proxy-scanner
