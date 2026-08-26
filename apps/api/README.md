# Sahana API

FastAPI backend for the Sahana hospital health assistant. This package contains
the Phase 0 foundation: typed configuration, structured logging, and the
health/config endpoints. Chat, routing, persistence, vector search, and LLM
providers are added in later phases.

## Requirements

- Python 3.13 (managed automatically by [uv](https://docs.astral.sh/uv/))
- [uv](https://docs.astral.sh/uv/) for dependency and environment management

## Setup

```bash
uv sync --extra dev
```

## Endpoints

| Method | Path            | Description                                             |
| ------ | --------------- | ------------------------------------------------------- |
| GET    | `/`             | Service name and version (courtesy landing route).      |
| GET    | `/health/live`  | Liveness probe. Always cheap; backs the Docker probe.   |
| GET    | `/health/ready` | Readiness probe. Aggregates the dependency registry.    |
| GET    | `/config`       | Non-secret runtime configuration for the UI.            |

`/health/ready` returns `503` when any registered dependency check fails. In
Phase 0 no checks are registered, so it returns `200` with an empty `checks`
list.

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
  main.py           # app factory, lifespan, CORS, router registration
  config.py         # pydantic-settings Settings + cached get_settings()
  logging.py        # structlog configuration
  readiness.py      # readiness-check registry (extension point)
  version.py        # single source of truth for the app version
  routers/health.py # the three health/config endpoints
  schemas/health.py # response models
tests/
  conftest.py       # ASGI transport client fixtures
  test_health.py    # endpoint tests, including the no-secrets assertion
```

## Configuration

All configuration is read from the environment (prefix `SAHANA_`) into a single
`Settings` object. See the repository root [`.env.example`](../../.env.example)
for the full set of variables. Provider keys are declared but unused in Phase 0.
