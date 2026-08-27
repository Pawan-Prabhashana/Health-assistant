"""Embedder abstraction and implementations."""

from __future__ import annotations

from sahana_api.embeddings.base import Embedder, EmbeddingError
from sahana_api.embeddings.factory import (
    build_kb_embedder,
    build_local_embedder,
    build_openai_embedder,
)
from sahana_api.embeddings.local import LocalEmbedder
from sahana_api.embeddings.openai import OpenAIEmbedder

__all__ = [
    "Embedder",
    "EmbeddingError",
    "LocalEmbedder",
    "OpenAIEmbedder",
    "build_kb_embedder",
    "build_local_embedder",
    "build_openai_embedder",
]
