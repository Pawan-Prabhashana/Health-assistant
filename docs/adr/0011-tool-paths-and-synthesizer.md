# 11. Tool paths, CRAG, Tavily, and the completing synthesizer

- Status: Accepted
- Date: 2026-08-27

## Context

Phase 4 shipped the decision graph with a `ToolPath` / `ToolResult` /
`Synthesizer` seam and deterministic stubs. Phase 5 has to put real answers on
the four proceed routes — CRM, RAG, direct, web search — without changing the
graph shape or `decide()`. The answers must be safe for a hospital concierge:
CRM data is own-data-only and never fabricated; RAG and web citations must be
real retrieved sources; every synth path must refuse to play clinician.

## Decision

**Registration swap, not a graph change.** The four real tools and
`CompletingSynthesizer` (which calls `get_model("synth").complete`) are wired
through `build_tool_registry` / `build_real_deps`. Stubs remain for graph-shape
tests. Phase 6 swaps `complete` for `stream` on the same `Synthesizer`
protocol, wires `run_pipeline` into chat endpoints, persists messages, stores
to CAG, and places the served-hit counter.

**CRM is identity-gated and structurally own-data-only.** The tool reads
`context.patient_id` (resolved upstream from the caller's phone). No id →
identify-first, no rows. Lookups go through
`PatientRepository.get_by_id` and `AppointmentRepository.next_upcoming_for_patient`
keyed only by that id, so another patient's rows cannot appear. The structured
table (`Patient ID` / `Name` / `Status` / `Next Appt`) and the plain-text
rendering are built from repository fields; the LLM never supplies a figure.
The synthesizer may frame; if any table cell is missing from the framed text,
the authoritative payload is restored.

**RAG uses CRAG relevance grading, not a raw similarity cutoff.** `rag_top_k`
chunks are retrieved, then an optional per-embedder score gate
(`rag_score_gate_openai`, `rag_score_gate_local`; `0` disables) drops obvious
neighbours because MiniLM and OpenAI embeddings score on different scales. A
cheap model (`crag_grader_role`, default `guardrail`) grades the survivors in
one batched structured call. If at least `crag_min_relevant` chunks grade
relevant, those are the only sources cited. Otherwise the corrective action
(when `crag_corrective_fallback` is on) is the web-search tool; if that is also
empty, the honest not-found message is returned. Citations are labels taken
from retrieved chunk `title`/`source` or Tavily URLs — never from the LLM.

**Tavily is a thin typed httpx wrapper, not the official SDK.** httpx is
already a dependency; the search request/response is small; pinning
`tavily-python` would add a second HTTP stack for no gain. The client has a
per-attempt timeout, bounded retries on transient errors (timeout, transport,
429, 5xx), and a `tavily_mode` of `live | fake` mirroring `llm_mode`. Fake
mode is what the test suite uses (no key, no network). Readiness is
config-only, same posture as the LLM check.

**Prompts live in a dedicated module.** `CONCIERGE_SYSTEM`, `GROUNDED_SYSTEM`,
and `CRM_FRAMING_SYSTEM` each append `MEDICAL_SAFETY_POSTURE`: Sahana is an
informational concierge, not a clinician; it does not diagnose or give
individual medical advice beyond the knowledge base; genuine emergencies are
directed to local emergency services or the hospital. Identify-first and
not-found paths skip the LLM so honesty is not left to generation.

### Config (not duplicated from CAG / embedder / model settings)

- CRAG: `rag_top_k`, `crag_grader_role`, `crag_min_relevant`,
  `crag_corrective_fallback`, `rag_score_gate_openai`, `rag_score_gate_local`.
- Tavily: `tavily_mode`, `tavily_base_url`, `tavily_max_results`,
  `tavily_timeout_seconds`, `tavily_max_retries`, `tavily_api_key`.

Default score gates (advisory floors before the grader, not relevance
deciders): OpenAI `0.2`, local MiniLM `0.3`. They are Settings fields so a
re-tune is a config change.

## Consequences

- Each proceed route returns a real, correctly shaped `PipelineResult`.
- CRM cannot leak another patient's data and cannot invent figures.
- RAG answers either cite retrieved KB sources, cite real web URLs after
  corrective fallback, or admit not-found.
- No new runtime dependency: Tavily rides on the existing `httpx` pin
  (`>=0.28.1,<0.29`).
- Phase 6 is additive: stream the synth, wrap `run_pipeline` in chat
  endpoints, persist, CAG store, served-hit counter.
