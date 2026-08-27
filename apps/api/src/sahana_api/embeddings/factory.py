"""Embedder selection from configuration."""

from __future__ import annotations

from sahana_api.config import Settings
from sahana_api.embeddings.base import Embedder, EmbeddingError
from sahana_api.embeddings.local import LocalEmbedder
from sahana_api.embeddings.openai import OpenAIEmbedder


def build_local_embedder(settings: Settings) -> LocalEmbedder:
    """Build the local fastembed embedder (used by the CAG cache and local KB)."""
    return LocalEmbedder(
        model=settings.local_embedding_model,
        cache_dir=settings.fastembed_cache_dir,
    )


def build_openai_embedder(settings: Settings) -> OpenAIEmbedder:
    """Build the OpenAI embedder.

    :raises EmbeddingError: if no OpenAI API key is configured.
    """
    if settings.openai_api_key is None:
        raise EmbeddingError("SAHANA_OPENAI_API_KEY is required for the OpenAI embedder")
    return OpenAIEmbedder(api_key=settings.openai_api_key, model=settings.openai_embedding_model)


def build_kb_embedder(settings: Settings) -> Embedder:
    """Return the embedder for the KB corpus, selected by ``kb_embedder``."""
    if settings.kb_embedder == "local":
        return build_local_embedder(settings)
    return build_openai_embedder(settings)
