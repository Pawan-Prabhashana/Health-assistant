# 10. The LangGraph decision graph

- Status: Accepted
- Date: 2026-08-27

## Context

The core routing decision fans a question out to three classifiers, folds them
into a single verdict, and dispatches to exactly one terminal. It must be
concurrent (the slow router sets the latency floor while the guardrail and cache
run for free), deterministic at the fan-in, and observable. The tool paths and
the real synthesizer arrive in later phases, so Phase 4 must land the graph with
a stable seam for them.

## Decision

**LangGraph, this exact shape.** `START` fans out to three classifier nodes —
`guardrail_node`, `router_node`, `cag_node` — that run concurrently; all three
edge into `decide_node`; a conditional edge from `decide_node` dispatches to one
of three terminals (`refusal_node`, `cached_answer_node`, `tool_then_synth_node`),
each edging to `END`.

**State without write conflicts.** The three classifier nodes write to distinct
keys (`guardrail`, `route`, `cag`), so their concurrent writes never collide. The
one shared key, `trace`, uses an explicit additive reducer
(`Annotated[list[TraceEntry], operator.add]`) so each node's contribution merges
rather than overwrites.

**`decide_node` is pure.** It makes no LLM call and no I/O; it delegates to a
total `decide()` function that is unit-tested in isolation. Precedence:

1. **Out-of-scope wins first.** If the guardrail says out of scope (or is absent —
   fail closed), the verdict is `OUT_OF_SCOPE`, regardless of any cache candidate
   or router route. An out-of-scope question never serves a cached answer or fires
   a tool.
2. **Then a gated cache hit.** Otherwise, a `cag` candidate that is at/above
   `cag_similarity_threshold`, not expired, and whose stored route is in the
   cacheable allowlist yields `CACHE_HIT`.
3. **Otherwise proceed.** `PROCEED` on `route.route`; if the router is absent or
   its confidence is below `router_min_confidence`, fall back to the documented
   safe default route (`router_fallback_route`, default `direct`) rather than
   acting on a low-confidence guess.

**Route-gating happens at the fan-in, not in `cag_node`.** `cag_node` performs a
route-agnostic, ungated KNN-1 peek (a new `CagCache.peek` that applies no
threshold/TTL/route filter and does not mutate the cache), because the router's
route is being decided in parallel and is not yet known. This is the correct
realization of "cache hits are route-gated": the gate is applied once, at
`decide_node`, with full information.

**Route-match policy.** `cag_route_match_policy` selects how a candidate's stored
route must relate to the request. The default, `any_allowlisted`, serves any
candidate whose stored route is allowlisted (cached answers are non-personalized
FAQ answers, so an allowlisted match is safe and maximizes hit rate). The
alternative, `match_router`, additionally requires the stored route to equal the
router's route. CRM is never allowlisted, so a patient-specific candidate is never
served under either policy.

**The `ToolPath` seam.** `tool_then_synth_node` looks the chosen route up in a
`ToolRegistry` and invokes the handler, then synthesizes. In Phase 4 the registry
holds deterministic, typed stub handlers (one per route) and the synthesizer is a
stub. Phase 5 swaps the handlers for the real CRM/RAG/direct/web-search tools and
Phase 6 swaps the stub synth for the streamed model — by changing registrations,
not the graph. The `ToolPath`/`ToolResult`/`Synthesizer` types are defined now so
Phase 5 is a drop-in.

**Invocation surface.** `build_graph(deps)` compiles the graph once (reused for
every request, never rebuilt per call); `run_pipeline(graph, question, context)`
returns a typed `PipelineResult` (verdict, route, answer, trace). The compiled
graph is attached to app state at startup.

**Trace.** Each node contributes one PII-free `TraceEntry`: the guardrail verdict,
the router route/confidence, the cache score and gate outcome, and the decide
branch taken. No question text, patient id, or raw answer is placed in the trace.

## Consequences

- The routing decision is concurrent and its latency floor is the router alone.
- Correctness lives in one pure, tested function; the graph is wiring.
- The cache is gated exactly once, with full information, at the fan-in.
- Phase 5 (real tools) and Phase 6 (streamed synth + chat endpoints) are additive:
  they swap registrations behind the `ToolPath`/`Synthesizer` seam and wrap
  `run_pipeline`, without touching the graph shape or `decide()`.
