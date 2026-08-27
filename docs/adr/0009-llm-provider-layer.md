# 9. LLM provider layer

- Status: Accepted
- Date: 2026-08-27

## Context

The decision graph (Phase 4) runs a guardrail classifier, a router classifier,
and a CAG lookup in parallel, then synthesizes a reply on the tool-backed paths.
Those steps need typed LLM transport for three model roles — guardrail, router,
synth — with timeouts, bounded retries, structured (JSON) outputs, streaming, and
per-call cost/latency accounting, plus a way to run the whole system in tests
without network or API keys. Model IDs and prices drift and must not be baked
into code.

## Decision

**One OpenAI-compatible transport.** Both Groq and OpenRouter expose
OpenAI-compatible APIs, so a single async transport (the `openai` `AsyncOpenAI`
client, already a dependency) serves all roles, configured per provider with a
different `base_url`, API key, and — for OpenRouter — `HTTP-Referer`/`X-Title`
attribution headers. One code path, three configured roles. Base URLs: Groq
`https://api.groq.com/openai/v1`, OpenRouter `https://openrouter.ai/api/v1`.

**`ChatModel` abstraction + role registry.** A typed `ChatModel` exposes
`complete`, `complete_structured` (JSON-schema-constrained, validated into a
Pydantic model, with a bounded repair retry that re-prompts with the validation
error), and `stream` (provider-agnostic text deltas). A `ModelRegistry` maps
`guardrail | router | synth` to a configured model, so callers ask for a role via
`get_model(role)`, not a vendor.

**Everything config-driven.** Every model ID, base URL, and price is a `Settings`
field with a default; swaps are config changes, not code changes. A `model_prices`
table (input/output per-1M-token rates keyed by model id) drives cost estimation.

**Resilience.** A per-attempt timeout plus bounded exponential backoff with full
jitter. Only transient failures retry: timeouts, connection errors, HTTP 429, and
5xx; other 4xx fail fast; `Retry-After` is respected on 429. Streaming is never
retried (a partial stream is unsafe to replay). The retry policy is an isolated,
tested unit.

**Accounting.** Every completion emits a structured `llm.usage` log (role, model,
prompt/completion tokens, estimated cost, latency ms) — the record Phase 6 writes
into `messages.metadata` and Phase 9 aggregates. Message content is never logged,
so no PII reaches the logs.

**Fake mode.** A deterministic `FakeChatModel` implements the same contract with
canned completions, schema-valid structured objects, and a canned stream, plus
injectable failures. `llm_mode` (`live | fake`) selects real vs fake via the
factory; the test configuration hard-defaults to `fake`, so the suite needs no
network or keys.

**Readiness.** The LLM readiness check is config-only (no live inference, so no
token burn or latency): it reports ready when the needed roles have a key and a
model, and lists the missing pieces otherwise. `/health/ready` now reports
`postgres`, `qdrant`, and `llm`.

### Model-ID defaults and the deprecation timeline

- Guardrail (fast classifier): Groq **`openai/gpt-oss-20b`**.
- Router (higher-quality classifier): Groq **`openai/gpt-oss-120b`**.
- Synth (streamed reply): OpenRouter **`google/gemini-2.5-flash`**.

The original design named Groq `llama-3.1-8b-instant` (guardrail) and
`llama-3.3-70b-versatile` (router). Both were announced for deprecation on Groq
on **2026-06-17**, with `openai/gpt-oss-20b` / `openai/gpt-oss-120b` as the
recommended replacements. We default to the replacements and keep the Llama IDs
documented as still-live-but-deprecated alternates (with prices in the table).

`google/gemini-2.5-flash` is scheduled for discontinuation on **2026-10-16**. We
default to it to match the design and document `google/gemini-3.7-flash` as the
pre-staged forward default; switching is a one-line config change because both
providers are OpenAI-compatible.

## Consequences

- Phase 4 depends on `get_model("guardrail"|"router"|"synth")`, structured
  outputs for the classifiers, and streaming for synth — all vendor-agnostic.
- Model swaps and price updates are configuration, tracked in one place.
- The fake keeps the default test gate hermetic; live behavior is covered by
  opt-in `llm_live` contract tests, skipped unless a key is present.
- Prices in the table are estimates for observability, not billing, and will
  drift; they live in config precisely so updating them needs no code change.
