"""Application configuration.

All runtime configuration is loaded exactly once into a single typed
:class:`Settings` object via :func:`get_settings`. This is the only place in the
codebase permitted to read the environment; every other module receives settings
through dependency injection or by calling :func:`get_settings`.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

AppEnv = Literal["development", "staging", "production"]


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
    cors_allow_origins: list[str] = Field(default_factory=lambda: ["http://localhost:8080"])

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
