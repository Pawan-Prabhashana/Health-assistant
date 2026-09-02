"""Application configuration.

All runtime configuration is loaded exactly once into a single typed
:class:`Settings` object via :func:`get_settings`. This is the only place in the
codebase permitted to read the environment; every other module receives settings
through dependency injection or by calling :func:`get_settings`.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

AppEnv = Literal["development", "staging", "production"]
LLMMode = Literal["live", "fake"]


class ModelPrice(BaseModel):
    """Per-1M-token input/output price for a model, in USD.

    Prices drift, so they live in configuration rather than code and are used only
    to estimate (not bill) cost for observability.
    """

    input_per_1m: float
    output_per_1m: float


def _default_model_prices() -> dict[str, ModelPrice]:
    """Current per-1M-token prices for the default and documented-alternate models."""
    return {
        # Active defaults.
        "openai/gpt-oss-20b": ModelPrice(input_per_1m=0.10, output_per_1m=0.50),
        "openai/gpt-oss-120b": ModelPrice(input_per_1m=0.15, output_per_1m=0.75),
        "google/gemini-2.5-flash": ModelPrice(input_per_1m=0.30, output_per_1m=2.50),
        # Documented alternates (see ADR 0009): deprecated Groq Llama classifiers
        # and the pre-staged forward Gemini default.
        "llama-3.1-8b-instant": ModelPrice(input_per_1m=0.05, output_per_1m=0.08),
        "llama-3.3-70b-versatile": ModelPrice(input_per_1m=0.59, output_per_1m=0.79),
        "google/gemini-3.7-flash": ModelPrice(input_per_1m=0.30, output_per_1m=2.50),
    }


class Settings(BaseSettings):
    """Typed application settings loaded from the environment.

    Fields grouped under "provider configuration" are declared here so the
    deployment surface (``.env`` files, container environment) is stable from
    Phase 0 onward. They are not read anywhere in Phase 0; later phases wire them
    into the database, vector store, and LLM provider clients.
    """

    model_config = SettingsConfigDict(
        env_prefix="SAHANA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # -- Core application --------------------------------------------------
    app_name: str = "Sahana"
    app_env: AppEnv = "development"

    # -- Logging -----------------------------------------------------------
    log_level: str = "INFO"
    log_json: bool = False

    # -- HTTP server -------------------------------------------------------
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_allow_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # -- Database (Supabase Postgres via SQLAlchemy async + asyncpg) -------
    # ``database_url`` is the pooled runtime connection (Supabase transaction
    # pooler / pgbouncer) used by the application; it MUST use the
    # ``postgresql+asyncpg`` scheme. Because the transaction pooler is
    # incompatible with server-side prepared statements, the engine is built
    # with ``statement_cache_size=0`` (see ``db.engine``).
    #
    # ``database_migration_url`` is the direct (non-pooled) connection used by
    # Alembic, because DDL needs a stable session the transaction pooler does not
    # provide. Both are required in staging/production; when unset the app still
    # boots (liveness stays up) and readiness reports Postgres as not-ready.
    database_url: str | None = None
    database_migration_url: str | None = None
    # Pool sizing (see ADR 0014). A chat request peaks at three concurrent
    # connections: the main request session plus the two context-fan-out nodes
    # (patient_lookup, memory_recall), each opening its own session from the
    # sessionmaker. The ceiling is ``db_pool_size + db_max_overflow`` = 15, which
    # sustains ~5 chat requests at their simultaneous fan-out instant and matches
    # the Supabase free-tier transaction-pooler default pool. Migrations use the
    # separate direct connection, so they do not draw from this pool. Raise both
    # (and the Supabase pooler pool size) together for higher concurrency.
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout: float = 30.0
    db_echo: bool = False

    # -- Vector store (Qdrant Cloud) --------------------------------------
    # ``qdrant_url``/``qdrant_api_key`` (below) are the credentials; these are the
    # collection names. The two collections are sized to two different embedders
    # (see ADR 0007) and must not be pointed at the same name.
    qdrant_kb_collection: str = "sahana_kb"
    qdrant_cag_collection: str = "sahana_cag"

    # -- Embeddings -------------------------------------------------------
    # OpenAI powers high-quality KB retrieval; the local fastembed MiniLM powers
    # the cheap, API-free CAG cache. ``fastembed_cache_dir`` should point under the
    # ``hf_cache`` volume mount in production so the model downloads once.
    openai_embedding_model: str = "text-embedding-3-small"
    local_embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    fastembed_cache_dir: str | None = None

    # -- Knowledge base ---------------------------------------------------
    # ``kb_embedder`` selects the embedder for the KB corpus. Switching it changes
    # the vector dimension, so ``sahana_kb`` must be recreated (ingest --recreate).
    kb_embedder: Literal["openai", "local"] = "openai"
    kb_chunk_tokens: int = 512
    kb_chunk_overlap: int = 64

    # -- CAG cache --------------------------------------------------------
    # Only answers from allowlisted routes may be cached; CRM (patient-specific)
    # is deliberately excluded so no personalized/PII answer is ever cached.
    cag_similarity_threshold: float = 0.92
    cag_ttl_seconds: int = 86400
    cag_cacheable_routes: list[str] = Field(
        default_factory=lambda: ["rag", "concierge", "web_search"]
    )

    # -- LLM providers (single OpenAI-compatible transport; see ADR 0009) --
    # ``llm_mode`` selects the real transport or the deterministic fake. Model IDs,
    # base URLs, and prices are all config so swaps are config changes, not code.
    # Guardrail/router run on Groq; synth runs on OpenRouter. Keys are read from
    # ``groq_api_key``/``openrouter_api_key`` in the provider block below.
    llm_mode: LLMMode = "live"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    guardrail_model: str = "openai/gpt-oss-20b"
    router_model: str = "openai/gpt-oss-120b"
    synth_model: str = "google/gemini-2.5-flash"
    llm_timeout_seconds: float = 30.0
    llm_max_retries: int = 3
    llm_structured_repair_attempts: int = 1
    # OpenRouter attribution headers (HTTP-Referer / X-Title).
    openrouter_referer: str = "https://github.com/Pawan-Prabhashana/Health-assistant"
    openrouter_title: str = "Sahana"
    model_prices: dict[str, ModelPrice] = Field(default_factory=_default_model_prices)

    # -- Decision graph (Phase 4) -----------------------------------------
    # ``router_min_confidence`` gates the router's route: below it, the graph
    # falls back to ``router_fallback_route`` (a documented safe default) rather
    # than acting on a low-confidence guess. ``cag_route_match_policy`` chooses how
    # a cache candidate's stored route must relate to the request at the decision
    # fan-in (see ADR 0010). The CAG threshold and cacheable-routes settings above
    # are reused, not duplicated.
    router_min_confidence: float = 0.5
    router_fallback_route: Literal["crm", "rag", "direct", "web_search"] = "direct"
    cag_route_match_policy: Literal["any_allowlisted", "match_router"] = "any_allowlisted"
    refusal_message: str = (
        "I'm sorry, but I can only answer questions related to hospital services."
    )

    # -- Tool paths: CRAG (RAG grading) and Tavily (web search); see ADR 0011 --
    # RAG retrieves ``rag_top_k`` chunks, then a cheap grader model
    # (``crag_grader_role``) grades relevance in one batched call. Relevance — not
    # a raw similarity score — decides usefulness; the optional per-embedder score
    # gates are advisory (0.0 disables) and exist because the two embedders score
    # on different scales. On zero relevant chunks the corrective fallback (when
    # enabled) queries the web tool, then honestly reports not-found.
    rag_top_k: int = 4
    crag_grader_role: Literal["guardrail", "router", "synth"] = "guardrail"
    crag_min_relevant: int = 1
    crag_corrective_fallback: bool = True
    rag_score_gate_openai: float = 0.2
    rag_score_gate_local: float = 0.3
    # Tavily web search. ``tavily_mode`` selects the real client or the fake, like
    # ``llm_mode``. The key is read from ``tavily_api_key`` in the provider block.
    tavily_mode: LLMMode = "live"
    tavily_base_url: str = "https://api.tavily.com"
    tavily_max_results: int = 5
    tavily_timeout_seconds: float = 10.0
    tavily_max_retries: int = 2

    # -- Chat pipeline and short-term memory (Phase 6); see ADR 0012 ------
    # Recall builds the synth context as a rolling summary plus the last
    # ``memory_recall_turns`` raw turns, so context stays bounded on long threads.
    # ``memory_summary_threshold`` is the turn count past which /chat/summarize is
    # advised; ``summary_model_role`` is the cheap model that compresses turns.
    # After a successful synth on a cacheable route the answer is stored to the CAG
    # cache non-blocking (``cache_store_enabled``). ``sse_keepalive_seconds`` bounds
    # SSE idle time with heartbeat comments.
    memory_recall_turns: int = 6
    memory_summary_threshold: int = 12
    summary_model_role: Literal["guardrail", "router", "synth"] = "guardrail"
    cache_store_enabled: bool = True
    sse_keepalive_seconds: float = 15.0

    # -- Provider configuration (declared now, consumed in later phases) ---
    # Supabase project references (used by later phases; not read here).
    supabase_url: str | None = None
    supabase_service_role_key: str | None = None
    # Qdrant Cloud — vector store.
    qdrant_url: str | None = None
    qdrant_api_key: str | None = None
    # Groq — routing/classification LLMs (Llama family).
    groq_api_key: str | None = None
    # OpenRouter — synthesis LLM (Gemini 2.5 Flash).
    openrouter_api_key: str | None = None
    # OpenAI — hosted embeddings.
    openai_api_key: str | None = None
    # Tavily — web search route.
    tavily_api_key: str | None = None

    @property
    def is_production(self) -> bool:
        """Return ``True`` when running under the production environment."""
        return self.app_env == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide :class:`Settings` singleton.

    The result is cached so configuration is parsed once per process. Tests that
    need to override configuration can call ``get_settings.cache_clear()``.
    """
    return Settings()
