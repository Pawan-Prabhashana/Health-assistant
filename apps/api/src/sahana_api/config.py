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

    # -- Provider configuration (declared now, consumed in later phases) ---
    # Supabase (Postgres + pgvector) — persistence layer.
    supabase_url: str | None = None
    supabase_service_role_key: str | None = None
    database_url: str | None = None
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
