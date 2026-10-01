# Deployment: the homelab

proxy-hub runs on shen as the homelab stack `proxy-hub` (iorlas/homelab,
`apps/private/proxy-hub/`). The homelab's onboarding runbook,
`docs/runbooks/onboard-app-repo.md` in iorlas/homelab, is the canonical version
of everything below.

## What lives where

| Here (public) | In the homelab (private) |
|---|---|
| `compose.yml`: services, images pinned to `${IMAGE_TAG:?}`, healthchecks, volumes | `stack.toml`: host, lane, endpoints, `[stack.source]` |
| `.github/workflows/deploy.yml`: build, publish compose, deploy | `compose.homelab.yml`: tailnet binds, laptop FQDNs |
| | `secrets.env.sops`: `PROXY_HUB_REDIS_PASSWORD` |

`docker-compose.yml` is local dev only.

## On every push to main

1. Build and push the three images as `main-<sha7>`.
2. `docker compose publish` `compose.yml` to `ghcr.io/iorlas/proxy-hub-compose:main-<sha7>`.
3. Start the homelab's `deploy.yml` with that tag (GitHub App token, secrets
   `HOMELAB_DEPLOY_APP_ID` / `HOMELAB_DEPLOY_APP_KEY`), wait for it, and print its
   log here only if it fails.

## Rules

- Every image in `compose.yml` uses `${IMAGE_TAG:?}`, so compose and images always
  come from one commit.
- A new secret: add `${NAME:?<what breaks>}` here, then add the value to the
  homelab's `secrets.env.sops`, before pushing.
- A new named volume: the homelab refuses the deploy until it has a backup class
  in its `platform/_registry/backup.toml`; the failed run says exactly what to add.
- No `build:` in `compose.yml` (publish refuses it) and no bind-mounted files
  (they are not published): bake config into the image.
