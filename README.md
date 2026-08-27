# Sahana

Sahana is a hospital health assistant. A client sends a question in a single HTTP
request; the backend classifies it and routes it down exactly one of five paths
(CRM lookup, RAG over an internal knowledge base, a direct concierge reply, a web
search, or a templated refusal), with a cache short-circuiting repeat FAQs. The
architecture principle is *outside sync, inside async*: the client sees one clean
round-trip while the handler fans out concurrent work internally.

This repository is built in ten phases. Phase 0 delivered the foundation (app,
client, config, logging, tooling, containers); Phase 1 added the Supabase data
layer, phone-based identity, and the patient/session endpoints. **Phase 2 adds
the vector-backed knowledge and cache layer**: a Qdrant client and collections, a
dual-embedder abstraction (OpenAI for the KB corpus, local fastembed MiniLM for
the CAG cache), an idempotent KB ingestion pipeline, a `KnowledgeRetriever`, and
route-gated CAG cache primitives, with a `qdrant` readiness check. The decision
graph, tool paths, LLM providers, and the chat pipeline arrive in later phases.
See [`docs/architecture.md`](docs/architecture.md) for the full target design and
what exists today, and [`docs/data-handling.md`](docs/data-handling.md) for the
PII posture.

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

## Quickstart (Docker)

```bash
cp .env.example .env
docker compose up --build -d
docker compose ps
```

Both services should report `healthy`. Open <http://localhost:8080> to see the
health-status page reading live readiness data from the API through nginx.

Verify the proxied API directly:

```bash
curl http://localhost:8080/api/health/live
curl http://localhost:8080/api/health/ready
curl http://localhost:8080/api/config
```

Stop the stack with `docker compose down`.

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

Then open <http://localhost:8080>.

## Make targets

Run `make help` to list them.

| Target       | Description                                              |
| ------------ | ------------------------------------------------------- |
| `install`    | Install backend (uv) and frontend (npm) dependencies.   |
| `lint`       | Lint backend (ruff) and frontend (eslint + prettier).   |
| `format`     | Auto-format backend and frontend.                       |
| `typecheck`  | `mypy --strict` (api) and `tsc` type-check (web).       |
| `test`       | Run the backend test suite (pytest).                    |
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
│   └── web/                 # React + Vite + TypeScript client
├── docs/
│   ├── architecture.md      # target architecture and Phase 0 status
│   └── adr/                 # architecture decision records
├── docker-compose.yml       # two-service topology, health-gated startup
├── Makefile                 # developer task runner
└── .env.example             # environment contract
```

## Configuration

All backend configuration is read from the environment (prefix `SAHANA_`) into a
single typed `Settings` object. Provider keys are declared in
[`.env.example`](.env.example) as documented placeholders and are not read by any
code in Phase 0. Secrets are never returned by `/config`.

## License

[MIT](LICENSE) © Pawan Prabhashana
