"""Local embedder backed by fastembed (ONNX MiniLM).

fastembed runs the MiniLM model through ONNX Runtime with no torch dependency,
which keeps the api image slim and cold starts fast, and it is Qdrant-native (see
ADR 0007). The model is created lazily on first embed so that merely reading the
dimension (to provision a collection) does not trigger a download. The model
cache is pointed at the ``hf_cache`` volume via ``cache_dir``.
"""

from __future__ import annotations

import asyncio

from fastembed import TextEmbedding

from sahana_api.embeddings.base import Embedder, EmbeddingError
from sahana_api.embeddings.retry import run_with_retries


def _dimension_for(model_name: str) -> int:
    """Return the output dimension of ``model_name`` from fastembed's registry."""
    for description in TextEmbedding.list_supported_models():
        if description.get("model") == model_name:
            return int(description["dim"])
    raise EmbeddingError(f"unknown local embedding model: {model_name}")


class LocalEmbedder(Embedder):
    """Embeds text with a local fastembed model (no network at query time)."""

    def __init__(
        self,
        *,
        model: str = "sentence-transformers/all-MiniLM-L6-v2",
        cache_dir: str | None = None,
        timeout: float = 30.0,
        attempts: int = 2,
    ) -> None:
        self._model_name = model
        self._dimension = _dimension_for(model)
        self._cache_dir = cache_dir
        self._timeout = timeout
        self._attempts = attempts
        self._model: TextEmbedding | None = None

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    def _ensure_model(self) -> TextEmbedding:
        """Instantiate the fastembed model on first use (downloads once, cached)."""
        if self._model is None:
            self._model = TextEmbedding(model_name=self._model_name, cache_dir=self._cache_dir)
        return self._model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        def _run() -> list[list[float]]:
            model = self._ensure_model()
            return [vector.tolist() for vector in model.embed(texts)]

        return await run_with_retries(
            lambda: asyncio.to_thread(_run),
            event="embed.local",
            attempts=self._attempts,
            timeout=self._timeout,
        )
