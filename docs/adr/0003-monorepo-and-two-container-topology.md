# 3. Monorepo and two-container topology

- Status: Accepted
- Date: 2026-08-26

## Context

Sahana comprises a FastAPI backend and a React frontend that are developed
together and deployed as a unit. We need to decide how to organise the source
(one repository or several) and how to run the system (how many containers, and
how the browser reaches the API).

## Decision

**One repository, two apps.** The backend and frontend live in a single
repository under `apps/api` and `apps/web`, each self-contained with its own
tooling, dependencies, and Dockerfile. Shared concerns — the environment
contract, compose topology, docs, and the task runner — live at the root.

**Two containers.** The system runs as two images:

- `web`: nginx serving the built SPA on port 8080. It reverse-proxies `/api/*` to
  the api container, stripping the `/api` prefix, so the browser uses a single
  origin and there is no CORS in the production path.
- `api`: FastAPI on port 8000, reachable only inside the compose network.

Startup is health-gated: `web` depends on `api` with `condition:
service_healthy`, and both services define healthchecks. A named `hf_cache`
volume is reserved on `api` for a later-phase local embedder.

## Consequences

- Atomic changes that span backend and frontend are a single, coherent unit of
  work, and the two apps evolve in lockstep with shared CI and docs.
- The reverse proxy keeps the browser on one origin, avoiding CORS in production
  and matching the Vite dev proxy used locally.
- Separating the two into their own images keeps each runtime minimal (no Node in
  the API image, no Python in the web image) and lets them scale independently.
- A monorepo requires path-scoped tooling (lint, type-check, and pre-commit hooks
  target the correct app), which we configure explicitly.
