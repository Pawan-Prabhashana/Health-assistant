# Sahana Operations Runbook

How to deploy, configure, and operate Sahana, and how to diagnose the failure
modes seen during the build. See [architecture.md](architecture.md) for the
design and the [ADR index](adr/README.md) for the decisions behind each choice.

## Topology

Two containers on a private network: **web** (nginx serving the built SPA on
8080, reverse-proxying `/api/*` to the api) and **api** (FastAPI on 8000, network
-internal). Postgres (Supabase) and Qdrant are external managed services.

## Deploy and configure

1. `cp .env.docker.example .env` and fill in keys. `.env` is gitignored; secrets
   are injected at deploy time and never committed.
2. `docker compose up --build -d`
3. `docker compose ps` — wait until both containers report `healthy`.
4. Browse to <http://localhost:8080>.

**Minimum to boot vs full functionality.** The stack starts and serves health
with no keys (liveness green, readiness reports dependencies not-ready). Keys
unlock capabilities: database → sessions/history/memory; Qdrant + OpenAI →
RAG/CAG; Groq → classifiers; OpenRouter → synth; Tavily → web search. Set
`SAHANA_LLM_MODE=fake` and `SAHANA_TAVILY_MODE=fake` to run keyless.

## Migrations and knowledge-base ingestion

```bash
make migrate                                   # Alembic upgrade head (direct connection)
docker compose --profile tools run --rm ingest # one-shot KB ingest into Qdrant (idempotent)
```

RAG returns nothing until the KB is ingested. Re-running ingest is safe; re-run
with `--recreate` (via `make ingest`) when the KB embedder — and therefore the
vector dimension — changes.

## Reading the metrics

`GET /metrics` (an operational endpoint, not one of the sixteen business
endpoints) exposes Prometheus text. Scrape it with Prometheus/Grafana or read it
directly:

```bash
curl -s http://localhost:8080/api/metrics | grep sahana_
```

Key series:

| Metric | Use |
| ------ | --- |
| `sahana_chat_turn_latency_seconds{route,verdict}` | Latency budgets by path (buckets at 0.29s / 1.7s / 2.5s). |
| `sahana_chat_turns_total{route,verdict}` | Route/verdict distribution — spend on refused vs answered. |
| `sahana_chat_cache_total{result}` | CAG cache hit rate = hit / (hit + miss). |
| `sahana_llm_tokens_total{role,model,kind}` | Token consumption by role and model. |
| `sahana_llm_cost_usd_total{role,model}` | Estimated spend — including on refused queries. |
| `sahana_chat_errors_total{code}` | Pipeline error rate. |

Every log line carries the request's `request_id` (also returned in the
`X-Request-ID` response header), so a user-reported issue can be traced end to end
by that id. No message content or PII is logged.

## Rotating keys

Keys live only in the deploy environment's `.env` (or the platform's secret
store). To rotate: update the value, then `docker compose up -d` (recreates the
api with the new environment). Provider keys — `SAHANA_GROQ_API_KEY`,
`SAHANA_OPENROUTER_API_KEY`, `SAHANA_OPENAI_API_KEY`, `SAHANA_TAVILY_API_KEY`,
`SAHANA_QDRANT_API_KEY` — and the database URLs are all env-injected; no code or
image rebuild is needed. Never commit a real key; gitleaks runs in CI to enforce
this.

## Rate limiting

Chat routes are rate limited (`SAHANA_RATE_LIMIT_CHAT`, default `30/minute`),
keyed by hashed identity then client IP, returning `429` with `Retry-After`.
Tune `SAHANA_RATE_LIMIT_CHAT` up or down per capacity. The store is in-memory, so
limits are **per api process**: running multiple api replicas requires a shared
store (Redis) or the limit is effectively multiplied by the replica count. Set
`SAHANA_RATE_LIMIT_ENABLED=false` only for local development.

## Troubleshooting

**Database or Qdrant unreachable.** `/health/ready` returns `503` and names the
failing check; `/health/live` stays `200`, so the container is not restarted.
Fix the dependency; readiness recovers on the next check. Chat calls that need the
dependency return a `503` error envelope meanwhile.

**Provider outage or model deprecation.** Model ids are configuration, not code
(ADR 0009). Swap `SAHANA_GUARDRAIL_MODEL` / `SAHANA_ROUTER_MODEL` /
`SAHANA_SYNTH_MODEL` (the price table has pre-staged alternates) and
`docker compose up -d`. No rebuild.

**Cold-cache first boot.** On first start the api downloads the local MiniLM
embedder and tokenizer into the `hf_cache` volume. The api healthcheck
`start_period` (120s) absorbs this; the volume persists them across restarts.

**Streaming not incremental (arrives in one lump).** Check nginx buffering: the
`= /api/chat/stream` location must keep `proxy_buffering off` and the backend
must send `X-Accel-Buffering: no` (ADR 0014). Verify with
`curl -N http://localhost:8080/api/chat/stream …` — frames must print
progressively. The `image-smoke` CI job guards this permanently.

**Pool exhaustion under load.** Each chat request peaks at three DB connections
(main + two context nodes); the pool ceiling is `db_pool_size + db_max_overflow`
(default 15). Under sustained concurrency raise both **and** the Supabase pooler
pool size together (ADR 0014); a symptom is `pool_timeout` waits in logs.

**CAG never hits / RAG empty.** Confirm the KB was ingested and the CAG embedder
matches the collection dimension (local MiniLM 384-d). Re-run ingest with
`--recreate` after an embedder change (ADR 0008).

## Backup and restore

- **Database:** Postgres is the system of record (patients, sessions, messages,
  rolling summaries). Use the managed provider's PITR/snapshots; a logical dump is
  `pg_dump` against the direct connection. Restore, then `make migrate` to ensure
  the schema is at head.
- **Qdrant:** derived data — the KB collection is rebuildable from `data/kb/` via
  ingest, and the CAG cache is a disposable accelerator. Prefer re-ingest over
  restore; use Qdrant snapshots if a warm cache must be preserved.
- **`hf_cache` volume:** a rebuildable model cache; it re-downloads if lost.

## Scaling notes

- The api is stateless apart from the in-memory rate-limit store; scale
  horizontally behind a load balancer, adding a shared limit store (Redis) so
  limits are global rather than per-replica.
- Size `db_pool_size`/`db_max_overflow` to `peak-connections-per-request (3) ×
  expected concurrent requests`, bounded by the Supabase pooler.
- The synth (streamed) call dominates latency; the router sets the fan-out floor.
  Watch `sahana_chat_turn_latency_seconds` by route against the budgets.
- TLS terminates upstream (a load balancer or ingress); set HSTS there, not in
  the app (ADR 0014).
