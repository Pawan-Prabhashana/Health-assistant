# Sahana Demo Script

A five-minute walkthrough that exercises all five routes with the design's own
example questions. It shows the architecture — *outside sync, inside async*, the
parallel-classifier decision graph, the safety gates — through the UI.

## Setup

Bring the stack up (see the [runbook](runbook.md)) and open
<http://localhost:8080>. For a keyless demo set `SAHANA_LLM_MODE=fake` and
`SAHANA_TAVILY_MODE=fake`; for real latencies and grounded answers, supply the
provider keys and run `make migrate` + the KB ingest first.

**Identify.** Enter a phone number on the identify screen and continue. Point out
that only the phone is persisted in the browser; the patient record is
re-resolved from the backend. Create a conversation from the sidebar.

Throughout, point at the **route badge**, the **latency**, and — while the answer
streams — the **tokens appearing incrementally** (this is the nginx-buffering fix
working end to end).

## 1. Cached FAQ — the cache short-circuit

> "What are the opening hours?"

- **Route:** cache hit → the badge reads **Answered instantly**.
- **Point at:** the ~290 ms latency. Ask it once (it takes the RAG path and is
  stored), then ask the same thing again to show the second call served from the
  CAG cache, bypassing the full graph and the model.
- **Say:** repeat FAQs never pay for the model; the cache is route-gated so it
  never caches patient-specific answers.

## 2. CRM question — the identity gate

> "Do I have an appointment today?"

- **Route:** CRM → renders an accessible **table** (Patient ID, Name, Status,
  Next Appt), not prose.
- **Point at:** the table is built from database rows, never fabricated by the
  model; the reply is for the identified caller only (own-data-only). If you sign
  out and ask the same thing, it asks you to identify first.
- **Say:** this is the identity-gated safety posture — the model frames the
  answer but never invents the figures.

## 3. RAG question — grounded retrieval with citations

> "What is the procedure for a skin inspection?"

- **Route:** RAG → a grounded answer with **Sources** listed beneath it.
- **Point at:** the citations (knowledge-base document titles); the answer streams
  token by token. Behind it: retrieve top-k → grade relevance (CRAG) → synthesize
  only from what survived, with an honest "not found" when nothing is relevant.
- **Say:** every claim is traceable to an ingested document; no ungrounded
  citations.

## 4. Web question — the Tavily route

> "Is there traffic to the hospital?"

- **Route:** web search → an answer synthesized from live web results, with the
  result URLs as citations.
- **Point at:** the route badge switches to **Web search**; this is the open-web
  path for things outside the knowledge base.

## 5. Out-of-scope — the calm refusal

> "Who is the president of the USA?"

- **Route:** refusal → a calm boundary ("Outside what I can help with"), not an
  answer.
- **Point at:** ~1.7 s latency and that the guardrail classified it out-of-scope
  before any tool ran. The refusal reads as a boundary, not an error.
- **Say:** the assistant stays inside hospital scope by design.

## Show the architecture directly

- **The trace.** Each answer carries a PII-free reasoning trace. Point out the
  parallel classifiers (guardrail, router, cache) and the two context nodes
  (patient lookup, memory recall) that fan out concurrently — *outside sync,
  inside async*.
- **Memory.** Ask several follow-ups; the thread keeps a rolling summary plus the
  last few turns, and the summary auto-refreshes past the threshold so the middle
  of a long conversation is never lost.
- **Ops.** `curl -s http://localhost:8080/api/metrics | grep sahana_` shows the
  route/verdict latencies, cache hit rate, and LLM token/cost counters live —
  the numbers behind the latency budgets. `GET /health/ready` shows each
  dependency check.
