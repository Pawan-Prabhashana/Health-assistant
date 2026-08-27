# 8. CAG cache design

- Status: Accepted
- Date: 2026-08-27

## Context

Many questions to a hospital assistant are repeat FAQs ("what are the visiting
hours?"). Re-running the full classify-and-route pipeline for each is wasteful.
A cache that recognizes a semantically equivalent question and returns a prior
answer can short-circuit these in roughly 300ms. The cache must be fast, cheap,
and — critically — must never serve a personalized or PII-bearing answer.

## Decision

The CAG cache is a **KNN-1 vector lookup** over `sahana_cag`, embedded with the
local fastembed MiniLM (no per-lookup API cost). It has two operations with the
following invariants.

**`lookup(question, route=None)`** embeds the question, retrieves the single
nearest entry, and returns it only when all hold:

- the similarity score is at or above `cag_similarity_threshold` (default 0.92);
- the entry has not expired (TTL, `cag_ttl_seconds`); expired entries are pruned
  on read;
- the entry's stored route is in the cacheable allowlist and, when a `route` is
  supplied, matches it.

A hit increments the entry's `hit_count`.

**`store(question, answer, route)`** embeds the question and upserts an entry
carrying `question`, `answer`, `route`, `created_at`, `expires_at`, and
`hit_count`, keyed by a deterministic id per normalized question (so repeats
overwrite in place). It **refuses** to store any route not in
`cag_cacheable_routes`.

**No-PII invariant and route-gating.** The cache holds only non-personalized,
non-PII answers. The reason route-gating exists is that some routes (CRM) produce
answers specific to one patient; caching such an answer could serve one patient's
data to another. `cag_cacheable_routes` therefore **excludes CRM by default**
(default `["rag", "concierge", "web_search"]`), and both `store` and `lookup`
enforce the allowlist. A personalized answer is never written, so it can never be
served.

## Consequences

- Repeat FAQs are answered from a cheap local-embedding lookup instead of the
  full pipeline.
- Patient-specific answers are structurally excluded from the cache; the gate is
  enforced on write and re-checked on read.
- Threshold and TTL are configuration, so the freshness/precision trade-off is
  tunable per environment without code changes.
- KNN-1 means a paraphrase just below the threshold is a miss (falls through to
  the pipeline) rather than a wrong hit — a deliberate bias toward correctness.
