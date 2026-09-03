# 15. Operational hardening and close-out

- Status: Accepted
- Date: 2026-09-03

## Context

Phases 0–8 shipped the complete application and a hardened one-command
deployment. Phase 9 adds the operational layer that makes it credibly
production-grade — CI, observability, rate limiting, abuse controls, secrets
hygiene — and closes the parked openapi-drift gap, the incremental-streaming
proof that needed a Docker host, and the short-term-memory auto-summarization
question. It is the final phase and closes out the project.

## Decision

**CI topology (GitHub Actions), six parallel jobs.** `backend-fast` (ruff, ruff
format, `mypy --strict`, the no-Docker fast test tier). `backend-full` (the `pg`
and `qdrant` testcontainers tiers on the runner). `frontend` (`npm ci`, lint,
`tsc`/build, vitest). `openapi-drift` generates the OpenAPI document from the app
and fails on any diff against the committed `apps/web/openapi.json`, so the
frontend's generated types can never silently drift from the Pydantic models;
refreshing is a documented regenerate-and-commit. `image-smoke` builds both
images, brings the stack up with compose in fake provider modes plus ephemeral
Postgres and Qdrant, waits for both containers healthy, and asserts a streamed
answer arrives through nginx in multiple SSE frames — automating the
incremental-streaming proof and making the nginx-buffering guarantee a permanent
regression test. `secret-scan` runs gitleaks and fails on any finding. Action
versions are pinned; uv and npm caches are enabled.

**Observability.** A `CorrelationIdMiddleware` assigns each request a correlation
id (honouring an inbound `X-Request-ID`), binds it into the structlog contextvars
so every log line for the request — including the pipeline's node logs — is
correlated, and echoes it in the `X-Request-ID` response header; the bind is
cleared per request and PII redaction is untouched (only the opaque id is bound).
A Prometheus `/metrics` endpoint (an operational endpoint, explicitly not one of
the sixteen business endpoints) exposes per-turn count and latency labelled by
route and verdict, the CAG cache hit/miss counter, chat error counts, and LLM
token and estimated-cost counters labelled by role and model — recorded at the
single `log_usage` choke point every model call already passes through. The
existing PII-free reasoning trace continues to land in structured logs; a
documented seam (record functions in `metrics.py`, the per-node trace) is left
for OpenTelemetry spans without pulling in a heavy OTel stack now.

**Rate limiting and input bounds.** The expensive chat routes are rate limited
via the `limits` library, keyed by hashed patient identity when a phone is
present and by client IP otherwise (the phone is hashed, never stored or logged in
the clear), returning `429` with `Retry-After` over the limit and configurable
through `Settings` (`rate_limit_chat`, `rate_limit_enabled`). The store is
in-memory, so limits are per-process: multiple api replicas need a shared store
(Redis) — documented in the runbook. Input bounds: a `BodySizeLimitMiddleware`
rejects oversized bodies (`413`) before parsing, the message length is capped in
the `ChatRequest` schema, the per-patient session count is capped (`409`), and
list pagination stays bounded — the first line against oversized input reaching
the model.

**Auto-summarization (the memory close-out).** Recall is `rolling summary + last
N turns`, so a long thread must refresh the summary server-side as turns arrive;
otherwise turns older than N but newer than the last summary fall out of context
— a silent mid-conversation gap. After each persisted turn the pipeline runs
`maybe_refresh_summary` (non-blocking: a background task on the sync path, part of
the shielded finalize on the stream path); once a thread exceeds
`memory_summary_threshold` it refreshes the rolling summary with the cheap summary
role, with no manual `POST /chat/summarize`. A test asserts a thread past the
threshold summarizes automatically and that recall still reflects a dropped middle
turn via the summary.

**Secrets posture.** `.env` and local secret files are gitignored;
`.env.docker.example` carries only placeholders; gitleaks proves it in CI rather
than by assertion. Secrets are injected at deploy time, never committed; rotation
is a runbook procedure.

## Consequences

- Every gate is enforced in CI on push and PR: types, tests (including real
  Postgres/Qdrant), streaming through nginx, type-drift, and secret scanning.
- The system is observable (correlated logs, Prometheus metrics) and defended
  (rate limits, input bounds) without heavy new infrastructure.
- Short-term memory no longer loses the middle of a long conversation.
- The project is complete: one-command boot, incremental streaming through nginx,
  five routes with the safety gates intact, tested, observable, and documented.
