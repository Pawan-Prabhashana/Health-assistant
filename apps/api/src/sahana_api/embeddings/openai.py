"""OpenAI embedder for high-quality KB retrieval."""

from __future__ import annotations

from openai import AsyncOpenAI

from sahana_api.embeddings.base import Embedder, EmbeddingError
from sahana_api.embeddings.retry import run_with_retries

# Output dimension per supported model. text-embedding-3-small is the default.
_MODEL_DIMENSIONS: dict[str, int] = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


class OpenAIEmbedder(Embedder):
    """Embeds text via the OpenAI embeddings API."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "text-embedding-3-small",
        timeout: float = 20.0,
        attempts: int = 3,
    ) -> None:
        if model not in _MODEL_DIMENSIONS:
            raise EmbeddingError(f"unknown OpenAI embedding model: {model}")
        self._model = model
        self._dimension = _MODEL_DIMENSIONS[model]
        self._timeout = timeout
        self._attempts = attempts
        self._client = AsyncOpenAI(api_key=api_key, timeout=timeout)

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        async def _call() -> list[list[float]]:
            response = await self._client.embeddings.create(model=self._model, input=texts)
            return [item.embedding for item in response.data]

        return await run_with_retries(
            _call,
            event="embed.openai",
            attempts=self._attempts,
            timeout=self._timeout,
        )
