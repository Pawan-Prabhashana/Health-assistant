# 2. Technology stack selection

- Status: Accepted
- Date: 2026-08-26

## Context

Sahana needs an asynchronous HTTP backend that fans out concurrent work per
request, a typed frontend, managed data and vector stores, and pluggable LLM
providers. The stack must be maintainable by a small team, strictly typed on
both ends, and reproducible in CI and containers.

## Decision

We adopt the following stack.

**Backend.** FastAPI on Python 3.13, served by uvicorn. FastAPI's native async
model fits the "outside sync, inside async" principle, and its Pydantic
integration gives typed request/response models for free. Dependencies and the
environment are managed by **uv** with a committed `uv.lock` for reproducible
resolution. Quality is enforced by **ruff** (lint + format), **mypy --strict**,
and **pytest** with **pytest-asyncio**; the ASGI app is tested in-process via
**httpx**. Configuration is a single typed `Settings` object from
**pydantic-settings**; logging is structured via **structlog**.

**Frontend.** React with **Vite** and **TypeScript** in `strict` mode, linted by
**ESLint** (flat config) with type-checked rules and formatted by **Prettier**.
Vite gives fast builds and a dev proxy that mirrors the production nginx routing.

**Data and providers (wired in later phases).** Supabase (Postgres + pgvector)
for persistence, Qdrant Cloud for vector search, Groq for routing LLMs,
OpenRouter for synthesis, OpenAI plus a local MiniLM for embeddings, and Tavily
for web search. These are declared in configuration from Phase 0 so the
deployment surface is stable, but no code reads them until their phase.

## Consequences

- Both ends are strictly typed, and the type checks are part of the quality gate.
- uv and a committed lockfile make backend builds reproducible across machines
  and containers.
- The provider choices commit us to managed external services; local development
  depends on network access and keys once those phases land. Phase 0 has no such
  dependency, which keeps the foundation testable offline.
- Pinning specific major versions incurs periodic upgrade work, accepted in
  exchange for reproducibility.
