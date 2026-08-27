"""Embedder abstraction.

An :class:`Embedder` turns text into fixed-dimension vectors. Two
implementations exist: :class:`~sahana_api.embeddings.openai.OpenAIEmbedder` for
high-quality KB retrieval and
:class:`~sahana_api.embeddings.local.LocalEmbedder` (fastembed/ONNX) for the
cheap, API-free CAG cache. Each exposes its model name and vector dimension so a
collection is always provisioned at the dimension of its active embedder and the
two can never drift.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingError(RuntimeError):
    """Raised when embedding fails after retries, or is misconfigured."""


class Embedder(ABC):
    """Turns text into vectors of a fixed dimension."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """The underlying model identifier."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """The dimension of the vectors this embedder produces."""

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed ``texts`` into vectors, preserving order.

        :raises EmbeddingError: on failure after the configured retries.
        """
