# Architecture

This document describes the target architecture of Sahana and marks what exists
as of Phase 0 versus what is planned for later phases.

## Overview

Sahana is a hospital health assistant. A client sends a question over a single
HTTP request; the backend classifies the question and routes it down exactly one
of five paths, then returns one clean response. The guiding principle is
**outside sync, inside async**: the client observes one ordinary request/response
round-trip, while the handler fans out concurrent work internally.

## Two-container topology

The system ships as two Docker containers behind a user-defined network:

- **web** — nginx serving the built React (Vite + TypeScript) SPA on port 8080.
  It reverse-proxies `/api/*` to the api container, stripping the `/api` prefix,
  so the browser talks to a single origin.
- **api** — FastAPI on port 8000. It owns classification, routing, persistence,
  vector search, and provider calls.

```
browser ──> web (nginx :8080) ──/api/*──> api (FastAPI :8000)
                 static SPA                 application logic
```

A named volume, `hf_cache`, is reserved on the api container for the local
MiniLM embedder used by a later phase. It is declared from Phase 0 so the
topology is stable across phases.

## Request routing (planned)

Every incoming question is classified in parallel and routed down exactly one of
five paths:

1. **CRM lookup** — structured patient/record queries against Supabase.
2. **RAG** — retrieval-augmented answers over an internal knowledge base held in
   Qdrant, synthesised by an LLM.
3. **Concierge** — a direct conversational reply for general assistance.
4. **Web search** — a Tavily-backed search for open-web questions.
5. **Refusal** — a templated response for out-of-scope or unsafe requests.

A **CAG cache** short-circuits repeated FAQs so common questions bypass the full
decision graph. The classifier evaluates candidate routes concurrently and the
decision graph selects exactly one path; the response is assembled and returned
in a single outward round-trip.

## Provider stack (planned)

| Concern          | Provider                                        |
| ---------------- | ----------------------------------------------- |
| Database         | Supabase (Postgres + pgvector)                  |
| Vector store     | Qdrant Cloud                                    |
| Routing LLMs     | Groq (Llama family)                             |
| Synthesis LLM    | OpenRouter (Gemini 2.5 Flash)                   |
| Embeddings       | OpenAI (hosted) and a local MiniLM              |
| Web search       | Tavily                                          |

## Endpoint surface (planned)

The finished backend exposes 16 endpoints: 3 health/config, 5 chat, 4 sessions,
and 4 patients. A courtesy `GET /` landing route sits outside that count.

## What exists as of Phase 0

Phase 0 delivers the foundation only:

- FastAPI application factory with a lifespan that configures structured logging.
- Typed configuration via a single `Settings` object (pydantic-settings). All
  provider fields are declared and defaulted; none are read yet.
- Structured logging via structlog (JSON in production, console in development).
- The three health/config endpoints:
  - `GET /health/live` — liveness.
  - `GET /health/ready` — readiness, backed by a check registry that later
    phases extend by appending checks rather than rewriting the handler. The
    registry is empty in Phase 0, so readiness is `true` with no checks.
  - `GET /config` — non-secret runtime configuration.
- The React client with a single view that renders live readiness, proving the
  browser → nginx → api path end to end.
- Docker images for both services, a compose file with health-gated startup, and
  the reserved `hf_cache` volume.

Everything under "planned" above — chat, the parallel classifier, the decision
graph, persistence, vector search, and provider clients — is intentionally not
implemented in Phase 0. The readiness registry, the typed provider settings, and
the reserved volume are the extension points those phases build on.
