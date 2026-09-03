<p align="center">
  <img src="Sahana%20Logo.png" alt="Sahana" width="180">
</p>

# Sahana

Sahana is a hospital health assistant. A client sends a question in a single HTTP
request; the backend classifies it and routes it down exactly one of five paths
(CRM lookup, RAG over an internal knowledge base, a direct concierge reply, a web
search, or a templated refusal), with a cache short-circuiting repeat FAQs. The
architecture principle is *outside sync, inside async*: the client sees one clean
round-trip while the handler fans out concurrent work internally.

This repository is built in ten phases. Phases 0–5 delivered the foundation, the
Supabase data layer with phone-based identity, the vector layer (Qdrant, dual
embedders, KB ingestion, retriever, route-gated CAG cache), the LLM provider layer
(`ChatModel` roles, structured output, streaming, fake mode), the decision graph,
and the four real tool paths plus the synthesizer. **Phase 6 makes it a chat
system**: five chat endpoints, SSE streaming of the synthesizer, the five-way
async fan-out, short-term memory (rolling summary plus recent turns), message
persistence, and a closed CAG cache loop — the realization of *outside sync,
inside async*. All 16 endpoints are live. **Phase 7 ships the frontend**: the
full chat experience — phone identity, session management, streaming chat over
fetch-based SSE, the CRM table, RAG/web citations, and the refusal/cache/tool
states — typed end to end from the backend's OpenAPI schema, accessible, and
tested. **Phase 8 makes it shippable**: nginx streams SSE incrementally, security
headers and a CSP are in place, the compose is hardened (healthcheck timing for
the cold model cache, resource limits, restart policies), connection-pool defaults
are tuned to the per-request fan-out, KB ingestion is an explicit deploy step, and
a devcontainer gives Codespaces parity. See
[`docs/architecture.md`](docs/architecture.md) for the full design,
[`docs/adr/0013-frontend-architecture.md`](docs/adr/0013-frontend-architecture.md)
for the frontend decisions,
[`docs/adr/0014-shipping-and-deployment.md`](docs/adr/0014-shipping-and-deployment.md)
for the deployment posture, and
[`docs/data-handling.md`](docs/data-handling.md) for the PII posture.

**Phase 9 closes the project out** with the operational layer: CI (lint, types,
tests on real Postgres/Qdrant, an OpenAPI-drift guard, an image-smoke test that
proves incremental streaming through nginx, and gitleaks), observability
(correlation ids, a Prometheus `/metrics` endpoint), rate limiting and input
bounds, and server-side auto-summarization of long threads. See
[`docs/adr/0015-operational-hardening.md`](docs/adr/0015-operational-hardening.md),
the [operations runbook](docs/runbook.md), and the [demo script](docs/demo.md).

## Architecture in brief

A question arrives in one HTTP request. `START` fans out to five concurrent nodes
— three classifiers (guardrail, router, cache probe) and two context nodes
(patient lookup, memory recall) — that fan into a pure-logic `decide` node
choosing exactly one of five routes: **CRM** (identity-gated record lookup),
**RAG** (retrieval + CRAG grading over the Qdrant knowledge base), **direct**
(concierge reply), **web** (Tavily), or **refusal**. A route-gated CAG cache
short-circuits repeat FAQs. The synthesizer answers synchronously (`POST /chat`)
or streamed over SSE (`POST /chat/stream`) from the same result. The guiding
principle is *outside sync, inside async*: one clean round-trip, concurrent work
inside. The [architecture doc](docs/architecture.md) has the full picture and a
pipeline diagram.

## Topology

The system runs as two containers on a private network:

- **web** — nginx serving the built React SPA on port 8080, reverse-proxying
  `/api/*` to the api container.
- **api** — FastAPI on port 8000, reachable only inside the compose network.

```
browser ──> web (nginx :8080) ──/api/*──> api (FastAPI :8000)
```

## Prerequisites

- [Docker](https://docs.docker.com/) with Compose v2 (for the container quickstart)
- [uv](https://docs.astral.sh/uv/) and Node.js 20+ (for local development without Docker)

## Quickstart (Docker) — the one-command boot

A fresh clone boots the whole stack with:

```bash
cp .env.docker.example .env      # then fill in keys (see below)
docker compose up --build -d
docker compose ps                # wait until both report healthy
```

Then open <http://localhost:8080> to use the app: identify with a phone number,
create a conversation, and chat with streaming replies. The operational status
page (live readiness through nginx) is reachable from the header's **Status** tab.
Stop the stack with `docker compose down`.

> On first boot the api downloads the local MiniLM embedder and tokenizer into
> the `hf_cache` volume. The healthcheck `start_period` absorbs this, so the
> container is not marked unhealthy during the one-time download.

### Minimum to boot vs full functionality

**Minimum to boot** — nothing in `.env` is required for the stack to *start* and
serve health: the api comes up with liveness green (readiness reports
dependencies as not-ready) and the SPA loads. Set `SAHANA_LLM_MODE=fake` and
`SAHANA_TAVILY_MODE=fake` to exercise the pipeline deterministically with no keys.

**Full functionality** — each capability is unlocked by its keys:

| Capability                       | Requires                                                             |
| -------------------------------- | ------------------------------------------------------------------- |
| Sessions, history, memory        | `SAHANA_DATABASE_URL` (+ `SAHANA_DATABASE_MIGRATION_URL` for migrations) |
| RAG knowledge base + CAG cache   | `SAHANA_QDRANT_URL`, `SAHANA_QDRANT_API_KEY`, `SAHANA_OPENAI_API_KEY`    |
| Guardrail + router classifiers   | `SAHANA_GROQ_API_KEY`                                                |
| Streamed synthesis reply         | `SAHANA_OPENROUTER_API_KEY`                                          |
| Web-search route                 | `SAHANA_TAVILY_API_KEY`                                              |

Every variable, with required/optional and runtime/migration notes, is documented
in [`.env.docker.example`](.env.docker.example).

### Database and knowledge base

With a database configured, apply migrations, then ingest the knowledge base
(RAG returns nothing until the corpus is in Qdrant; ingestion is idempotent):

```bash
make migrate                                   # Alembic upgrade head (direct connection)
docker compose --profile tools run --rm ingest # one-shot KB ingest (or: make ingest-docker)
```

### Verify the proxy and incremental streaming

```bash
curl http://localhost:8080/api/health/live
curl http://localhost:8080/api/config

# Streamed SSE must arrive frame-by-frame (not one lump). Create a session first,
# then watch routing/delta/final print progressively as they are produced:
curl -N http://localhost:8080/api/chat/stream \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"<session-uuid>","message":"What are your visiting hours?"}'
```

## Local development (without Docker)

Run the two apps in separate terminals. The Vite dev server proxies `/api/*` to
the backend, mirroring the nginx routing.

Backend:

```bash
cd apps/api
uv sync --extra dev
uv run uvicorn sahana_api.main:app --host 0.0.0.0 --port 8000 --reload
```

Frontend:

```bash
cd apps/web
npm install
npm run dev
```

Then open <http://localhost:3000> (the Vite dev server; it proxies `/api` to the
backend on 8000). Note this differs from the container topology, where nginx
serves the SPA at <http://localhost:8080>.

## GitHub Codespaces

The repository ships a [`.devcontainer/`](.devcontainer/devcontainer.json) with
docker-in-docker, Node 20, Python 3.13, and uv, so it opens consistently on a
laptop, a server, or in Codespaces. Open the repo in a Codespace, then:

```bash
# .env is seeded from .env.docker.example on create; fill in keys, then:
docker compose up --build -d
```

Ports 8080 (web) and 8000 (api) are forwarded; the web preview opens
automatically. The same one-command boot as the Docker quickstart applies.

## Make targets

Run `make help` to list them.

| Target       | Description                                              |
| ------------ | ------------------------------------------------------- |
| `install`    | Install backend (uv) and frontend (npm) dependencies.   |
| `lint`       | Lint backend (ruff) and frontend (eslint + prettier).   |
| `format`     | Auto-format backend and frontend.                       |
| `typecheck`  | `mypy --strict` (api) and `tsc` type-check (web).       |
| `test`       | Run the backend test suite (pytest).                    |
| `migrate`    | Apply database migrations to head (Alembic).            |
| `seed`       | Populate idempotent demo data.                          |
| `ingest`     | Ingest the knowledge base into Qdrant (local uv).       |
| `ingest-docker` | Ingest the KB via the one-shot compose service.      |
| `up`         | Build and start the container stack in the background.  |
| `down`       | Stop and remove the container stack.                    |
| `logs`       | Follow container logs.                                  |
| `ps`         | Show container status.                                  |
| `clean`      | Remove build artefacts and caches.                      |

## Project layout

```
.
├── apps/
│   ├── api/                 # FastAPI backend (uv, ruff, mypy, pytest)
│   │   └── src/sahana_api/  # application package
│   └── web/                 # React + Vite + TypeScript client (nginx in prod)
├── .devcontainer/           # Codespaces / devcontainer parity
├── .github/workflows/       # CI: lint, types, tests, openapi-drift, image-smoke, gitleaks
├── docs/
│   ├── architecture.md      # as-built architecture + pipeline diagram
│   ├── runbook.md           # operating, metrics, key rotation, troubleshooting
│   ├── demo.md              # five-route demo script
│   └── adr/                 # architecture decision records (0001–0015, + index)
├── docker-compose.yml       # hardened two-service topology + one-shot ingest
├── docker-compose.ci.yml    # CI overlay: ephemeral pg + qdrant, fake providers
├── Makefile                 # developer task runner
└── .env.docker.example      # full environment contract (copy to .env)
```

## Testing

The backend suite is tiered by pytest marker so the fast tier needs no Docker and
no keys:

```bash
cd apps/api
uv run pytest -m "not pg and not qdrant and not llm_live"   # fast: lint-speed, hermetic
uv run pytest -m "pg or qdrant"                              # real Postgres + Qdrant (testcontainers)
uv run pytest -m llm_live                                    # opt-in live-provider latency smoke
```

The frontend runs Vitest + React Testing Library + MSW (including a mocked SSE
stream): `cd apps/web && npm run test`. CI runs all of these plus an OpenAPI-drift
check and an image-smoke test (see [`.github/workflows/ci.yml`](.github/workflows/ci.yml)).

## Observability and ops

- **`GET /metrics`** — Prometheus text (an operational endpoint, not one of the 16
  business endpoints): route/verdict latency and counts, CAG cache hit rate, LLM
  token and estimated-cost counters by role and model, and error counts.
- **Correlation ids** — every request is assigned one, bound into every structlog
  line, and returned as `X-Request-ID`; no PII is logged.
- **Health** — `GET /health/live` (liveness) and `GET /health/ready` (per-
  dependency readiness, `503` when a dependency is down while liveness stays up).

See the [runbook](docs/runbook.md) for reading the metrics, rotating keys, rate-
limit tuning, and troubleshooting.

## Configuration

All backend configuration is read from the environment (prefix `SAHANA_`) into a
single typed `Settings` object. Every variable — grouped, with required/optional
and runtime/migration notes — is documented in
[`.env.docker.example`](.env.docker.example); copy it to `.env` (gitignored) and
fill in real keys. Secrets are never committed and never returned by `/config`,
and gitleaks enforces this in CI.

## License

[MIT](LICENSE) © Pawan Prabhashana
