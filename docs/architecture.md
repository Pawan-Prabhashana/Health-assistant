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

## Endpoint surface

The backend exposes all 16 endpoints: 3 health/config, 4 patients, 4 sessions, and
5 chat (`POST /chat`, `POST /chat/stream`, `GET /chat/history`,
`POST /chat/summarize`, `DELETE /chat/memory`). A courtesy `GET /` landing route
sits outside that count.

## What exists as of Phase 6

Phase 6 makes Sahana a chat system, realizing "outside sync, inside async":

- **Five chat endpoints**: a synchronous `POST /chat` (one round-trip), an SSE
  `POST /chat/stream` sharing one pipeline, plus history, summarize, and
  clear-memory. See [ADR 0012](adr/0012-chat-pipeline-and-memory.md).
- **Five-way fan-out**: two context nodes (`patient_lookup`, `memory_recall`) join
  the three classifiers on the fan-out, writing distinct keys; `decide` is
  unchanged.
- **SSE protocol**: `routing` → `delta*` → `final` for tool-backed answers;
  `routing` → `final` for refusals and cache hits; `error` for failures. Disconnect
  persists what was generated (marked incomplete) with no dangling record.
- **Short-term memory**: recall is a bounded rolling summary plus the last N turns;
  the summary lives in `sessions` columns added by migration `0002`.
- **Closed CAG loop**: cacheable answers are stored non-blocking; identical FAQs
  hit the cache; CRM is never stored; the served-hit counter increments post-gate.
- **Synth usage on the stream** is captured from the terminal chunk
  (`include_usage`); total per-request latency is instrumented and returned.

## What exists as of Phase 5

Phase 5 replaces the Phase 4 stub tools and stub synthesizer with the four real
proceed paths and a non-streaming synthesizer (still behind the same interfaces):

- **CRM**: identity-gated, own-data-only lookup of status and next appointment;
  structured table payload for the frontend; figures rendered from repository
  rows, never from the LLM.
- **RAG + CRAG**: retrieve top-k, optional per-embedder score gate, batched
  relevance grading on a cheap role, corrective Tavily fallback, honest
  not-found. Citations are retrieved chunk `title`/`source` or Tavily URLs.
- **Direct**: concierge `complete` with no external tool.
- **Web search**: typed Tavily client (httpx wrapper) with timeout, retries, and
  a fake mode. Readiness is config-only (`tavily` check).
- **Synthesizer**: route-specific prompts in `tools/prompts.py`, each carrying
  the medical-safety posture. CRM framing that drops a figure is reverted to the
  authoritative payload.

Streaming, chat endpoints, message persistence, CAG store, and the served-hit
counter are Phase 6.

## What exists as of Phase 4

Phase 4 adds the routing decision graph on top of the LLM layer, with stubbed
tools (replaced in Phase 5) and no chat pipeline yet:

- **The graph** (LangGraph): `START` fans out to three parallel classifiers —
  `guardrail_node`, `router_node`, `cag_node` — that fan into a pure-logic
  `decide_node`, which dispatches to one of three terminals (`refusal_node`,
  `cached_answer_node`, `tool_then_synth_node`). See
  [ADR 0010](adr/0010-decision-graph.md).
- **State without conflict**: the classifiers write distinct keys; the shared
  `trace` uses an additive reducer.
- **`decide_node` precedence** (no LLM, no I/O): out-of-scope wins first, then a
  gated cache hit (threshold + unexpired + allowlisted route), otherwise proceed
  on the router's route with a low-confidence fallback to `direct`. Cache gating
  happens once, at the fan-in, via an ungated `CagCache.peek`.
- **The `ToolPath` seam**: `tool_then_synth_node` dispatches through a
  `ToolRegistry` and a `Synthesizer`; later phases swap registrations, not the
  graph.
- **Invocation**: `build_graph()` compiles once (reused per request);
  `run_pipeline(question, context)` returns a typed `PipelineResult` with a
  PII-free reasoning trace.

## What exists as of Phase 3

Phase 3 adds the LLM transport the decision graph and synth path sit on:

- **`ChatModel` abstraction + role registry**: `complete`, `complete_structured`
  (JSON-schema-validated with a bounded repair retry), and `stream`; a registry
  maps `guardrail | router | synth` to a configured model via `get_model(role)`.
- **One OpenAI-compatible transport**: a single `AsyncOpenAI` client configured
  per provider (Groq for guardrail/router, OpenRouter for synth) by `base_url`,
  key, and attribution headers. See [ADR 0009](adr/0009-llm-provider-layer.md).
- **Resilience**: per-attempt timeout, bounded exponential backoff with jitter,
  retrying only transient failures (timeout, connection, 429, 5xx) and respecting
  `Retry-After`; streams are not retried.
- **Accounting**: every call emits a structured `llm.usage` log (role, model,
  tokens, estimated cost from a config price table, latency) with no message
  content.
- **Config-driven models**: no model ID, base URL, or price is hardcoded; all are
  `Settings` fields, so swaps (including the documented deprecation forward paths)
  are config changes.
- **Fake mode**: a deterministic `FakeChatModel` and `llm_mode` (`live | fake`)
  make the whole system testable without network or keys.
- **Readiness**: a config-only `llm` check joins `postgres` and `qdrant`;
  `/health/ready` reports all three and is `503` when LLM config is missing, while
  `/health/live` stays `200`.

## What exists as of Phase 2

Phase 2 adds the two vector-backed capabilities the RAG and CAG paths depend on:

- **Vector store**: a Qdrant client and idempotent collection provisioning at the
  active embedder's dimension. Two collections — `sahana_kb` (RAG corpus, OpenAI
  1536-d) and `sahana_cag` (answer cache, local MiniLM 384-d). See
  [ADR 0007](adr/0007-vector-store-and-embedders.md).
- **Embedders**: an `Embedder` abstraction with `OpenAIEmbedder` and a local
  `LocalEmbedder` (fastembed/ONNX, no torch), selected by config. The local model
  caches into the `hf_cache` volume and runs offline after first download.
- **KB ingestion**: `python -m sahana_api.kb.ingest` loads `data/kb/` Markdown,
  chunks it token-aware (tiktoken) with overlap, embeds it, and upserts into
  `sahana_kb` with deterministic point IDs (idempotent; `--recreate` rebuilds).
- **KnowledgeRetriever**: `search(query, top_k) -> list[ScoredChunk]`, scored and
  payload-bearing, consumed by the RAG tool and CRAG grading in Phase 5.
- **CAG cache**: a route-gated KNN-1 cache with threshold, TTL, `hit_count`, and a
  no-PII invariant (CRM never cached). See
  [ADR 0008](adr/0008-cag-cache-design.md).
- **Readiness**: a `qdrant` check joins `postgres`, so `/health/ready` reports
  both and returns `503` when either is down while `/health/live` stays `200`.

## What exists as of Phase 1

Phase 1 adds the persistence foundation and identity surface on top of Phase 0:

- **Database**: SQLAlchemy 2.0 async + asyncpg against Supabase Postgres, with a
  request-scoped `get_session` dependency and an engine configured for the
  Supabase transaction pooler (`statement_cache_size=0`). See
  [ADR 0004](adr/0004-persistence-stack.md).
- **Schema** (initial Alembic migration): `patients`, `appointments`, `sessions`,
  `messages`; the `vector` extension is enabled to reserve the RAG capability
  (no vector columns yet). See [ADR 0005](adr/0005-data-model-and-identity.md).
- **Identity**: patients are keyed by E.164 phone; MRNs (`P-10023`) come from a
  sequence. Four patient endpoints (upsert-by-phone, get-by-id, resolve-by-phone,
  erase) and four session endpoints (create, list-by-patient, get, delete).
- **Typed async repositories** per aggregate; SQLAlchemy types never cross the
  route boundary.
- **Readiness**: a `postgres` `SELECT 1` check is registered, so `/health/ready`
  returns `503` when the database is unreachable while `/health/live` stays `200`.
- **PDPA posture**: log redaction of PII, PII-free list/error responses, and a
  genuine cascading erasure endpoint. See
  [ADR 0006](adr/0006-pii-pdpa-handling.md) and
  [data-handling.md](data-handling.md).

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
