# 12. Chat pipeline, streaming, and memory

- Status: Accepted
- Date: 2026-08-29

## Context

Phase 6 turns the decision pipeline into a chat system: five endpoints, SSE
streaming of the synthesizer, the "outside sync, inside async" fan-out, short-term
memory, message persistence, and closing the CAG cache loop. The caller must get
one clean HTTP contract while the handler runs multiple tasks concurrently.

## Decision

**Five-way fan-out, additively.** Two context nodes join the three classifiers on
the fan-out from `START`: `patient_lookup_node` (resolves the caller's phone to a
patient id, own-identity only) and `memory_recall_node` (loads the rolling summary
plus the last N turns). They write distinct state keys (`resolved_patient_id`,
`memory`), so the concurrent writes never conflict; the shared `trace` uses the
existing additive reducer. `decide_node` is unchanged — it still reads only the
three classifiers, so all Phase 4/5 decision tests hold. The context nodes are
added only when a `session_provider` is present, so graph-shape tests without one
keep the three-way fan-out. In production each concurrent node gets its own session
from the sessionmaker; the slowest task (the router) sets the floor.

**Tool/synth split.** The graph's `tool_then_synth` node now runs only the tool
and leaves a `ToolResult` in state; synthesis moves to the pipeline layer so the
same result is answered synchronously (`complete`) or streamed (`stream`) without
double work. `build_graph` returns a `CompiledPipeline` (graph + synthesizer),
compiled once and reused.

**SSE event protocol.** `routing` (verdict/route, once known), `delta`
(incremental synth tokens), `final` (answer, citations, structured CRM table,
route, usage, latency, PII-free trace), and `error` (typed). Non-streaming
terminals emit `routing` then a single `final`: refusals and cache hits have
nothing to stream, and the CRM table ships its structured payload in `final`. The
sync `ChatResponse` and the `final` payload share one schema, so Phase 7 consumes
one shape for both paths. A keepalive comment is injected on idle
(`sse_keepalive_seconds`).

**Synth usage on the stream.** The stream requests `stream_options.include_usage`
and captures usage from the terminal chunk, so the synth — the most expensive call
— is no longer cost-blind. The stream API is `stream_events` (typed
`TextDelta`/`StreamCompleted`); the old text-only `stream` delegates to it.

**Disconnect handling.** The streaming handler persists after the stream via its
own session provider, and the finalize is `asyncio.shield`-ed, so a client
disconnect persists what was generated (marked `incomplete`) and never leaves a
dangling half-written record.

**Short-term memory.** Recall assembles `rolling summary + last N raw turns`
(`memory_recall_turns`), bounding context regardless of thread length. Every turn
persists a user and an assistant message via `MessageRepository`, with per-turn
metadata in the existing `messages.metadata` JSONB — route, verdict, latency,
usage/cost, and citations — never PII. The rolling summary lives in new
`sessions.summary` / `sessions.summary_updated_at` columns (migration `0002`);
`/chat/summarize` refreshes it with a cheap model role, and recall reads it.

**Closed CAG loop.** After a successful synth on a cacheable route (`rag`,
`concierge`, `web_search`) the question→answer mapping is stored via
`CagCache.store`, non-blocking (a FastAPI background task on the sync path, a
shielded post-stream step on the SSE path), so it never adds response latency. CRM
is never stored — `store` is route-gated and the allowlist excludes it. The served
-hit counter increments `hit_count` at the `cached_answer` terminal (post-gate,
only for hits actually served) via a new non-mutating-`peek`-preserving
`record_hit`; `peek` stays side-effect-free.

**Latency budgets.** Total per-request latency is instrumented and returned
(`latency_ms`). In fake mode the numbers are effectively instant, so the default
suite asserts the shape (cache-hit and refusal do no tool/synth work; the tool
path does) and an opt-in `llm_live` smoke test measures real wall-clock against the
budgets (~290ms cached, ~1.7s refusals, 2–2.5s tool-backed) when keys are present.

## Consequences

- One pipeline backs both `/chat` and `/chat/stream`; the graph and `decide` are
  untouched, and Phase 0–5 tests pass unchanged.
- Memory stays bounded on long threads; per-turn observability lands in
  `messages.metadata` for Phase 9 to aggregate.
- Repeat FAQs are served from cache without a dangling write on disconnect, and
  patient-specific answers are structurally excluded from the cache.
