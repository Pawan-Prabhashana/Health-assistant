# Sahana API

FastAPI backend for the Sahana hospital health assistant. It provides typed
configuration, structured logging, the health/config endpoints (Phase 0), and
the persistence layer with patient and session endpoints (Phase 1). Chat,
routing, vector search, and LLM providers are added in later phases.

## Requirements

- Python 3.13 (managed automatically by [uv](https://docs.astral.sh/uv/))
- [uv](https://docs.astral.sh/uv/) for dependency and environment management

## Setup

```bash
uv sync --extra dev
```

## Endpoints

| Method | Path                       | Description                                          |
| ------ | -------------------------- | ---------------------------------------------------- |
| GET    | `/`                        | Service name and version (courtesy landing route).   |
| GET    | `/health/live`             | Liveness probe. Always cheap; backs the Docker probe.|
| GET    | `/health/ready`            | Readiness probe, including a `postgres` check.        |
| GET    | `/config`                  | Non-secret runtime configuration for the UI.          |
| POST   | `/patients`                | Upsert a patient by phone (`201` created / `200` updated). |
| GET    | `/patients/{id}`           | Fetch a patient by id.                                |
| GET    | `/patients/by-phone/{phone}` | Resolve a patient by phone (E.164-normalized).      |
| DELETE | `/patients/{id}`           | Erase a patient and cascade (PDPA right to erasure).  |
| POST   | `/sessions`                | Create a conversation thread.                         |
| GET    | `/sessions`                | List threads for a patient (`phone` or `patient_id`). |
| GET    | `/sessions/{id}`           | Fetch a thread (`?include=messages`).                 |
| DELETE | `/sessions/{id}`           | Delete a thread and cascade its messages.             |

`/health/ready` returns `503` when any registered dependency check fails (e.g.
Postgres unreachable), while `/health/live` stays `200` so the container is still
considered live.

## Database

Migrations are managed with Alembic and run against the direct connection
(`SAHANA_DATABASE_MIGRATION_URL`). The application runtime uses the pooled
connection (`SAHANA_DATABASE_URL`).

```bash
uv run alembic upgrade head        # apply migrations
uv run alembic downgrade base      # reverse them
uv run python -m sahana_api.seed   # idempotent demo data (make seed)
```

## Knowledge base and vector store

The KB corpus lives as Markdown under [`data/kb/`](../../data/kb). Ingest it into
Qdrant (idempotent; `--recreate` rebuilds the collection, required when the KB
embedder — and therefore the vector dimension — changes):

```bash
uv run python -m sahana_api.kb.ingest             # make ingest
uv run python -m sahana_api.kb.ingest --recreate
```

`SAHANA_KB_EMBEDDER=local` ingests and queries with the local fastembed MiniLM
(384-d) and needs no OpenAI key; the default `openai` (1536-d) is for production
retrieval quality. The CAG answer cache always uses the local embedder.

## Running locally

```bash
uv run uvicorn sahana_api.main:app --host 0.0.0.0 --port 8000 --reload
```

## Quality gates

```bash
uv run ruff check
uv run ruff format --check
uv run mypy --strict src
uv run pytest
```

## Layout

```
src/sahana_api/
  main.py            # app factory, lifespan (db + readiness), router registration
  config.py          # pydantic-settings Settings + cached get_settings()
  logging.py         # structlog configuration + PII redaction processor
  readiness.py       # readiness-check registry (extension point)
  errors.py          # error-envelope exception handlers
  phone.py           # E.164 normalization
  seed.py            # idempotent demo-data seed
  version.py         # single source of truth for the app version
  db/                # engine, request-scoped session, postgres readiness check
  models/            # SQLAlchemy ORM models + enums
  repositories/      # typed async repositories per aggregate
  embeddings/        # Embedder abstraction: OpenAI + local (fastembed) + factory
  vector/            # Qdrant client, collection provisioning, qdrant readiness
  kb/                # KB documents, token chunking, ingestion, KnowledgeRetriever
  cag/               # route-gated KNN-1 answer cache
  llm/               # ChatModel abstraction, provider client, retry, fake, registry
  graph/             # LangGraph decision graph: state, nodes, decide, tools, pipeline
  tools/             # CRM, RAG/CRAG, direct, Tavily/web, synthesizer, prompt module
  routers/           # health, patients, sessions
  schemas/           # Pydantic request/response models
alembic/             # migration environment and versions
tests/
  conftest.py        # ASGI + testcontainers (postgres, qdrant) fixtures
  test_*.py          # health, phone, redaction, embeddings, kb, cag, endpoints, ...
```

Tests marked `pg` (Postgres) and `qdrant` run against real containers via
testcontainers and skip automatically when Docker is unavailable. Run only the
fast tier with `uv run pytest -m "not pg and not qdrant"`.

## Configuration

All configuration is read from the environment (prefix `SAHANA_`) into a single
`Settings` object. See the repository root [`.env.example`](../../.env.example)
for the full set of variables. Provider keys for later phases are declared but
unused.
