# 14. Shipping and deployment

- Status: Accepted
- Date: 2026-09-02

## Context

Phases 0–7 shipped the full application. The Docker images, the nginx `/api`
proxy, and the two-service compose have existed since Phase 0 but predate SSE
streaming and the full dependency set. Phase 8 makes the deployment production-
grade and reproducible: streaming that works through nginx, security headers, a
hardened compose with healthcheck timing for the cold model cache, connection-
pool tuning, KB ingestion as an explicit deploy step, and Codespaces parity — so
a fresh clone boots the whole stack with one command.

## Decision

**nginx must not buffer the stream.** nginx buffers proxied responses by default,
which holds SSE tokens and delivers them in one lump at the end — the chat
appears frozen, then dumps everything. This never showed in the Vite dev preview
because that path does not traverse nginx. The fix is a dedicated exact-match
`location = /api/chat/stream` with `proxy_buffering off`, `proxy_cache off`,
`proxy_http_version 1.1`, `proxy_set_header Connection ""` (keep the upstream
connection open for chunked streaming), `proxy_read_timeout`/`proxy_send_timeout
1h`, and `chunked_transfer_encoding on`. The backend also sets
`X-Accel-Buffering: no` and `Cache-Control: no-cache` on the stream response,
which nginx honours. The rest of `/api/` keeps normal buffering. An `upstream`
block with `keepalive` warms the backend connection.

**Security headers and CSP.** Every response carries `X-Content-Type-Options:
nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, a
`Permissions-Policy` disabling unused features, and a Content-Security-Policy.
The CSP is `default-src 'self'` with `script-src 'self'` (the SPA serves its own
hashed bundles, no inline/CDN scripts), `connect-src 'self'` (fetch and the
streaming fetch are same-origin under `/api`), `style-src 'self' 'unsafe-inline'`
(bundled CSS delivery), `img-src 'self' data:`, `frame-ancestors 'none'`,
`object-src 'none'`, and `base-uri`/`form-action 'self'`. It permits the app's
own assets and API while refusing external origins, inline scripts, and framing —
strict enough to matter, loose enough not to break the SPA or the stream. The
headers live in a snippet re-`include`d in every location that sets its own
`add_header` (nginx drops inherited `add_header` from such blocks). `robots.txt`
keeps `Disallow: /`. HSTS is deliberately not set here: TLS is terminated
upstream in real deployments, so `Strict-Transport-Security` belongs at that edge.

**Non-root web image.** The web runtime moves to
`nginxinc/nginx-unprivileged:1.27-alpine`, which runs as uid 101 and listens on
8080 — matching the api's existing non-root user, with no build tooling in either
final image.

**Compose hardening.** The api healthcheck stays on `/health/live` (a missing
external dependency must not flap the container) with a generous
`start_period: 120s` so the one-time MiniLM/tiktoken download into `hf_cache` on
first boot cannot mark it unhealthy, while `interval`/`timeout`/`retries` stay
tight for steady state. Both services get `restart: unless-stopped` and memory
limits/reservations (api 2g/512m for the ONNX embedder; web 256m/64m). `web`
still waits on `api` via `depends_on: service_healthy`; the private network and
`hf_cache` volume remain. Both services read the whole `.env` via `env_file`; the
fastembed cache dir is fixed to the volume path in `environment` so it cannot be
misconfigured.

**Connection-pool tuning.** A chat request peaks at three concurrent
connections: the main request session plus the two context-fan-out nodes
(`patient_lookup`, `memory_recall`), each opening its own session. Defaults are
`db_pool_size=5`, `db_max_overflow=10` — a ceiling of 15 that sustains ~5
concurrent chat requests at their simultaneous fan-out instant and matches the
Supabase free-tier transaction-pooler default pool. Migrations use the separate
direct connection and do not draw from this pool. Scaling higher means raising
both values and the Supabase pooler pool size together.

**KB ingestion in the deploy flow.** RAG returns nothing until the corpus is in
Qdrant, so ingestion is an explicit step, not an assumption. A one-shot `ingest`
service (compose `tools` profile) runs `python -m sahana_api.kb.ingest` against
the configured Qdrant on the shared network and volume:
`docker compose --profile tools run --rm ingest` (or `make ingest-docker`).
Ingestion is idempotent (Phase 2), so re-running on deploy is safe.

**Codespaces parity.** A `.devcontainer/` (docker-in-docker, Node 20, Python
3.13, uv) opens the project consistently on a laptop, a server, or Codespaces,
forwards ports 8080/8000, and seeds `.env` from `.env.docker.example`.

## Consequences

- Streaming is visibly incremental through port 8080, verifiable with `curl -N`.
- The web app ships sensible security headers and a CSP that does not break the
  SPA or the stream; both images are slim, multi-stage, and non-root.
- A fresh clone boots with `cp .env.docker.example .env && docker compose up
  --build -d`; the cold model download does not flap the container; RAG works
  after the documented one-shot ingest.
- Pool defaults are matched to the per-request fan-out and the Supabase pooler,
  with a clear path to scale.
