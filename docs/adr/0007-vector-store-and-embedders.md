# 7. Vector store and embedder strategy

- Status: Accepted
- Date: 2026-08-27

## Context

Phase 2 introduces two vector-backed capabilities: a RAG knowledge corpus that
needs high-quality retrieval, and a CAG answer cache that needs cheap, fast,
API-free lookups to short-circuit repeat FAQs. These have different cost and
quality profiles and therefore different embedders and vector dimensions.

## Decision

**Qdrant Cloud** is the vector store, with two collections:

- `sahana_kb` — the RAG corpus, embedded with **OpenAI `text-embedding-3-small`**
  (1536 dims, cosine). Payload carries `doc_id`, `title`, `source`, `section`,
  `chunk_index`, `text`, and `content_hash` so CRAG grading and citation (Phase 5)
  have what they need.
- `sahana_cag` — the answer cache, embedded with a **local MiniLM**
  (`all-MiniLM-L6-v2`, 384 dims, cosine).

**Local embedder = fastembed (ONNX), not sentence-transformers + torch.**
fastembed runs MiniLM through ONNX Runtime with no torch dependency, which keeps
the api image slim (≈690MB with onnxruntime; a torch stack would be several GB)
and cold starts fast, and it is Qdrant-native. The model cache is pointed at the
existing `hf_cache` volume (`fastembed_cache_dir`) so the model downloads once and
persists across restarts; the container works offline after the first download.

**`Embedder` abstraction.** A small ABC exposes `model_name`, `dimension`, and an
async `embed(texts) -> list[list[float]]`, with per-attempt timeouts, bounded
retries, and latency logging shared via a helper. `OpenAIEmbedder` and
`LocalEmbedder` implement it; a factory selects the KB embedder from
`kb_embedder`. Collections are always created at `embedder.dimension`, so the
stored vectors and the active embedder can never drift.

**Dev-without-keys.** `kb_embedder` may be `openai` (default, production quality)
or `local`, which lets the KB be ingested and queried before an OpenAI key
exists. Switching it changes the vector dimension, so `sahana_kb` must be dropped
and recreated; the ingest command exposes `--recreate` for exactly this.

## Consequences

- The two workloads use the embedder each deserves: quality for retrieval, cost
  and latency for the cache.
- No torch in the runtime image; the local embedder is self-contained and
  offline-capable after first download.
- Dimension is owned by the embedder, so a collection can never be provisioned at
  the wrong size; changing the KB embedder is a deliberate `--recreate`.
- OpenAI is required for production-quality KB retrieval; the `local` option keeps
  development unblocked without a key.
